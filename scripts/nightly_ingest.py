#!/usr/bin/env python3
"""
Nightly pipeline: fetch today's CrossFit Havoc WOD, parse it with Claude,
and load it into Supabase.

Requires environment variables:
    ANTHROPIC_API_KEY
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY   (service role — bypasses RLS, needed for shared writes)

Usage:
    python3 nightly_ingest.py
    python3 nightly_ingest.py --date 2026-09-22   # backfill a specific day (if still on the page)
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from dateutil import parser as dateparser

import anthropic
import requests
from supabase import create_client

WOD_URL = "https://crossfithavoc.com/wod/"

PARSE_PROMPT = """You are parsing a CrossFit gym's daily workout post into structured JSON.
The post text is informal and varies in format day to day. Extract every distinct
segment (warmup, strength/weightlifting work, WOD, accessory work, skill work).

Return ONLY valid JSON (no markdown fences, no preamble), matching this shape exactly:

{
  "segments": [
    {
      "segment_order": 1,
      "segment_type": "warmup | strength | wod | accessory | skill | other",
      "title": "short label, e.g. 'Push Press' or 'AMRAP 16'",
      "structure_type": "sets_reps | emom | amrap | for_time | tabata | max_effort | none",
      "score_type": "load | reps | time | rounds_reps | distance | calories | none",
      "movements": [
        {
          "name": "normalized movement name, e.g. 'Push Press', 'Pull-up', 'Clean and Jerk'",
          "movement_order": 1,
          "prescribed_reps": "free text as written, e.g. '3', '8-10', '50 cal'",
          "prescribed_sets": 5,
          "prescribed_scheme": "free text description of the scheme for this movement"
        }
      ],
      "notes": "anything relevant not captured above, or null"
    }
  ]
}

Rules:
- The warmup is always its own segment, segment_type "warmup", score_type "none".
- If a block says "increase weight as you go" or similar, capture that in prescribed_scheme.
- A strength/weightlifting block should be segment_type "strength" and score_type "load" if
  it's a loaded barbell/dumbbell/kettlebell movement, or "reps" if it's bodyweight-for-reps
  like GHD sit-ups, pull-ups, or handstand push-ups done as a standalone block.
- The main conditioning piece is segment_type "wod". score_type is "time" for "for time",
  "rounds_reps" for AMRAPs, "reps" for fixed-time max-reps efforts, "calories"/"distance" only
  if the whole piece is scored purely in calories or distance.
- prescribed_sets should be an integer when explicit (e.g. "Every 1:30 for 10 Sets" -> 10).
- Keep movement names in consistent Title Case, singular where natural (e.g. "Pull-up").
- Do not invent information not present in the text.

Here is the workout text to parse:

---
{raw_text}
---
"""


def fetch_wod_page() -> str:
    resp = requests.get(WOD_URL, timeout=20, headers={"User-Agent": "havoc-tracker/1.0"})
    resp.raise_for_status()
    return resp.text


def extract_latest_post(page_html: str):
    """
    Extract the most recent WOD post's title, date, and body text from the
    page HTML. WordPress.com renders each post as an <article>-like block
    with an h2 title link and body paragraphs. This is intentionally
    conservative: if the page structure changes, it should fail loudly
    rather than silently return garbage.

    Note: the post's URL date (e.g. /2026/09/16/wod-thursday-september-17th-4/)
    is the PUBLISH date, which is the night before the workout — CF Havoc posts
    the next day's WOD by ~9:10pm. The actual workout date always comes from the
    title text itself (e.g. "WOD Friday September 18th"), never the URL.
    """
    title_match = re.search(
        r'<h2[^>]*>\s*<a[^>]+href="(https://crossfithavoc\.com/\d{4}/\d{2}/\d{2}/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
        page_html,
    )
    if not title_match:
        raise RuntimeError("Could not find a WOD post title on the page — site layout may have changed.")

    url, raw_title = title_match.groups()
    title = html.unescape(raw_title).replace("\xa0", " ").strip()

    # Parse the actual workout date out of the title text, e.g.
    # "WOD Friday September 18th" -> 2026-09-18. Strip ordinal suffixes (st/nd/rd/th)
    # first since dateutil doesn't handle "18th" reliably on its own.
    title_for_date = re.sub(r'\b(\d{1,2})(st|nd|rd|th)\b', r'\1', title, flags=re.IGNORECASE)
    date_match = re.search(r'([A-Za-z]+ \d{1,2})', title_for_date)
    if not date_match:
        raise RuntimeError(f"Could not find a date in post title: {title!r}")

    # The title has no year, so infer it: assume the current year, but if that
    # would put the date more than ~30 days in the future, it must be last year's
    # post lingering, or a year boundary — roll back a year in that edge case.
    now = datetime.now()
    parsed_date = dateparser.parse(f"{date_match.group(1)} {now.year}")
    if (parsed_date.date() - now.date()).days > 30:
        parsed_date = dateparser.parse(f"{date_match.group(1)} {now.year - 1}")
    post_date = parsed_date.strftime("%Y-%m-%d")

    # Body: everything between this title match and the next <h2 (or the "Why CrossFit Havoc?" section)
    start = title_match.end()
    next_section = re.search(r'<h2', page_html[start:])
    body_html = page_html[start:start + next_section.start()] if next_section else page_html[start:start + 3000]

    # Strip tags to get readable text, decode HTML entities, collapse whitespace
    body_text = re.sub(r'<[^>]+>', '\n', body_html)
    body_text = html.unescape(body_text).replace("\xa0", " ")
    body_text = re.sub(r'\n\s*\n+', '\n\n', body_text).strip()

    return {"workout_date": post_date, "source_title": title, "source_url": url, "raw_text": body_text}


def parse_with_claude(raw_text: str) -> dict:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": PARSE_PROMPT.replace("{raw_text}", raw_text)}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def load_into_supabase(sb, wod: dict, parsed: dict):
    # Upsert the workout row
    existing = sb.table("workouts").select("id").eq("workout_date", wod["workout_date"]).execute()
    payload = {
        "workout_date": wod["workout_date"],
        "source_title": wod["source_title"],
        "source_url": wod["source_url"],
        "raw_text": wod["raw_text"],
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "parse_version": "v1",
    }
    if existing.data:
        workout_id = existing.data[0]["id"]
        sb.table("workouts").update(payload).eq("id", workout_id).execute()
        # clear old segments before reloading (handles re-parse / re-run same night)
        sb.table("segments").delete().eq("workout_id", workout_id).eq("source", "havoc").execute()
    else:
        result = sb.table("workouts").insert(payload).execute()
        workout_id = result.data[0]["id"]

    for seg in parsed["segments"]:
        seg_row = {
            "workout_id": workout_id,
            "segment_order": seg["segment_order"],
            "segment_type": seg["segment_type"],
            "title": seg["title"],
            "structure_type": seg["structure_type"],
            "raw_text": seg.get("title", ""),
            "score_type": seg["score_type"],
            "source": "havoc",
            "notes": seg.get("notes"),
        }
        seg_result = sb.table("segments").insert(seg_row).execute()
        segment_id = seg_result.data[0]["id"]

        for mv in seg.get("movements", []):
            existing_mv = sb.table("movements").select("id").eq("name", mv["name"]).execute()
            if existing_mv.data:
                movement_id = existing_mv.data[0]["id"]
            else:
                mv_result = sb.table("movements").insert({"name": mv["name"]}).execute()
                movement_id = mv_result.data[0]["id"]

            sb.table("segment_movements").insert({
                "segment_id": segment_id,
                "movement_id": movement_id,
                "movement_order": mv["movement_order"],
                "prescribed_reps": mv.get("prescribed_reps"),
                "prescribed_sets": mv.get("prescribed_sets"),
                "prescribed_scheme": mv.get("prescribed_scheme"),
            }).execute()

    return workout_id


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()

    for var in ("ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Missing required environment variable: {var}")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    page_html = fetch_wod_page()
    wod = extract_latest_post(page_html)
    print(f"Latest post found: {wod['workout_date']} — {wod['source_title']}")

    parsed = parse_with_claude(wod["raw_text"])
    workout_id = load_into_supabase(sb, wod, parsed)
    print(f"Loaded workout_id={workout_id} with {len(parsed['segments'])} segments.")


if __name__ == "__main__":
    main()
