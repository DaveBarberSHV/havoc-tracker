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
import time
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
      "wod_name": "ONLY if the post explicitly names a benchmark workout (e.g. Fran, Cindy, Murph, Helen, Grace, Diane) give just that name; otherwise null",
      "description": "the segment's workout exactly as a coach would write it on a whiteboard: the format/time cap, every movement with its reps, loads, and rep scheme (e.g. '10 Minute AMRAP: 5 Pull-ups, 10 Push-ups, 15 Air Squats'). Use line breaks between parts. null for the warmup.",
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
- "description" must only restate what the post says. Never add movements, loads, or times that are not in the text. Keep the post's own wording for scores/formats (e.g. "For Time", "AMRAP 16").
- "wod_name" is for named benchmark workouts only. A descriptive title like "AMRAP 16" or "50 Cal Bike" is NOT a name — use null.
- A COMPLEX is several lifts done back to back as one unit without putting the bar down (for example
  "Power Snatch + Overhead Squat", or "Hang Snatch Pull + Snatch"). Record a complex as ONE movement,
  never as separate movements, because it is scored as a single weight. Put the components in
  prescribed_scheme (for example "1 Hang Power Snatch + 1 Overhead Squat + 1 Snatch Balance"). For a
  complex that has no name of its own, name the movement with its components joined by " + ".
- CrossFit Havoc has two complexes of its own: "Havocomplex Snatch" and "Havocomplex Clean" (spelled exactly that way).
  Each is ONE movement named exactly that. Its score is the heaviest weight lifted for the whole
  complex without dropping the bar. Never split either one into its component lifts.
- The gym tracks these lifts and tests. When a movement is one of them, use exactly this name:
  {known_movements}
- The gym also keeps records for these named workouts. When the post names one, set wod_name to exactly
  this spelling: {known_benchmarks}

Here is the workout text to parse:

---
{raw_text}
---
"""



# ---------------------------------------------------------------------------
# Movement and benchmark recognition
#
# These are the lifts, skills and tests on the gym's record board, so the app recognizes them
# whenever they come up. Names are matched by SPELLING-INSENSITIVE identity ("Pull-ups", "pull ups"
# and "Pull-up" are the same movement), so a variant reuses the existing record instead of creating
# a duplicate.
# ---------------------------------------------------------------------------
KNOWN_MOVEMENTS = [
    # barbell lifts
    "Back Squat", "Front Squat", "Overhead Squat", "Strict Press", "Push Press", "Bench Press",
    "Deadlift", "Thruster", "Power Clean", "Clean", "Clean and Jerk", "Power Clean and Jerk",
    "Power Snatch", "Snatch", "Snatch Balance", "Turkish Get-up", "Weighted Pull-up",
    # the gym's own complexes (each is ONE movement)
    "Havocomplex Clean", "Havocomplex Snatch",
    # gymnastics and skills
    "Strict Pull-up", "Kipping Pull-up", "Bar Muscle-up", "Ring Muscle-up",
    "Strict Handstand Push-up", "Handstand Walk", "Box Jump", "Long Jump", "Double Under",
    # timed distance tests
    "100 Meter Row", "500 Meter Row", "1000 Meter Row", "2000 Meter Row", "5000 Meter Row", "400 Meter Run",
]
KNOWN_BENCHMARKS = [
    "Amanda", "Angie", "Annie", "Cindy", "Diane", "Elizabeth", "Fran", "Grace", "Helen", "Isabel",
    "Jackie", "Karen", "Kelly", "Linda", "Lynne", "Mary", "Nancy", "Murph",
    "Fight Gone Bad", "Filthy Fifty", "King Kong", "Yo Mama So Crazy", "30 Ring Muscle-ups",
]


def movement_key(name: str) -> str:
    """Spelling-insensitive identity: 'Pull-ups', 'pull ups' and 'Pull-up' all give 'pullup'."""
    text = (name or "").lower().replace("&", " and ")
    parts = []
    for tok in re.findall(r"[a-z0-9]+", text):
        if len(tok) > 2 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        parts.append(tok)
    return "".join(parts)


_CANON_MOVEMENT = {movement_key(n): n for n in KNOWN_MOVEMENTS}
_CANON_MOVEMENT.update({
    "havoccomplexsnatch": "Havocomplex Snatch", "havcomplexsnatch": "Havocomplex Snatch",
    "havoccomplexclean": "Havocomplex Clean", "havcomplexclean": "Havocomplex Clean",
    "tgu": "Turkish Get-up", "turkishgetup": "Turkish Get-up",
})
_CANON_BENCHMARK = {movement_key(n): n for n in KNOWN_BENCHMARKS}


def canonical_movement_name(name: str) -> str:
    """The gym's spelling for a movement it tracks; anything else is left exactly as given."""
    clean = (name or "").strip()
    return _CANON_MOVEMENT.get(movement_key(clean), clean)


def canonical_benchmark(name):
    """'fran' -> 'Fran', 'Grace 185' -> 'Grace'. Names the gym doesn't track are left as given."""
    if not name:
        return name
    clean = str(name).strip()
    hit = _CANON_BENCHMARK.get(movement_key(clean))
    if hit:
        return hit
    # drop a trailing weight such as "Grace - 185" or "Isabel 175 lb"
    stripped = re.sub(r"[\s\-\u2013:]*\d+\s*(?:lbs?|#|kg)?\s*$", "", clean, flags=re.I)
    return _CANON_BENCHMARK.get(movement_key(stripped), clean)


# "Havocomplex" blends "Havoc" and "Complex" (they share the C), so match it as one word and also
# the spaced/hyphenated spellings: Havocomplex, Havoc Complex, Havoc-Complex, Havoccomplex, Havcomplex.
_HAVOCOMPLEX = re.compile(r"hav(?:oc)?\s*-?\s*c?omplex\s*[:\-]?\s*(snatch|clean)?", re.I)


def collapse_complexes(parsed: dict) -> dict:
    """Safety net: a Havocomplex is ONE movement. If the parser split one into its component
    lifts, merge them back, keeping the components in the scheme text."""
    for seg in parsed.get("segments", []):
        if seg.get("segment_type") not in ("strength", "other", "accessory", "skill"):
            continue
        movs = seg.get("movements") or []
        if not movs:
            continue
        text = " ".join(str(x) for x in [seg.get("title"), seg.get("description"), seg.get("notes")] if x)
        text += " " + " ".join(str(m.get("name", "")) + " " + str(m.get("prescribed_scheme") or "") for m in movs)
        found = _HAVOCOMPLEX.search(text)
        if not found:
            continue
        kind = (found.group(1) or "").title()
        if not kind:
            names = " ".join(str(m.get("name", "")).lower() for m in movs)
            kind = "Snatch" if "snatch" in names else "Clean" if "clean" in names else ""
        if not kind:
            continue
        target = f"Havocomplex {kind}"
        if len(movs) == 1 and movement_key(movs[0].get("name", "")) == movement_key(target):
            continue   # already a single, correctly named movement
        parts = []
        for m in movs:
            if movement_key(m.get("name", "")) == movement_key(target):
                continue
            reps = str(m.get("prescribed_reps") or "").strip()
            parts.append(f"{reps} {m.get('name', '')}".strip())
        schemes = []
        for m in movs:
            sc = (m.get("prescribed_scheme") or "").strip()
            if sc and sc not in schemes and sc not in parts:
                schemes.append(sc)
        scheme = " + ".join(parts)
        if schemes:
            scheme = (scheme + " — " if scheme else "") + schemes[0]
        sets = [m.get("prescribed_sets") for m in movs if isinstance(m.get("prescribed_sets"), int)]
        seg["movements"] = [{
            "name": target, "movement_order": 1, "prescribed_reps": "1",
            "prescribed_sets": max(sets) if sets else None,
            "prescribed_scheme": scheme or None,
        }]
        seg["segment_type"] = "strength"
        seg["score_type"] = "load"
    return parsed


def normalize_parsed(parsed: dict) -> dict:
    """Applied to every parse: Havocomplex stays whole, benchmark and movement names use the gym's spelling."""
    for seg in parsed.get("segments", []):
        if seg.get("wod_name"):
            seg["wod_name"] = canonical_benchmark(seg["wod_name"])
    collapse_complexes(parsed)
    for seg in parsed.get("segments", []):
        for mv in seg.get("movements") or []:
            mv["name"] = canonical_movement_name(mv.get("name", ""))
    return parsed


def load_movement_cache(sb) -> dict:
    """Existing movements, looked up two ways: by exact name, and by spelling-insensitive identity
    (the oldest record wins if the same movement was ever created twice)."""
    rows = sb.table("movements").select("id, name").execute().data or []
    cache = {"exact": {}, "key": {}}
    for row in sorted(rows, key=lambda r: r["id"]):
        cache["exact"][row["name"]] = row["id"]
        cache["key"].setdefault(movement_key(row["name"]), row["id"])
    return cache


def find_or_create_movement(sb, name: str, cache: dict) -> int:
    """Reuse an existing movement whatever its spelling; otherwise create it under the gym's spelling."""
    if name in cache["exact"]:
        return cache["exact"][name]
    key = movement_key(name)
    if key in cache["key"]:
        return cache["key"][key]
    display = canonical_movement_name(name)
    created = sb.table("movements").insert({"name": display}).execute()
    cache["exact"][display] = created.data[0]["id"]
    cache["key"][key] = created.data[0]["id"]
    return created.data[0]["id"]


def fetch_wod_page() -> str:
    # A cache-busting query param + no-cache headers, in case a CDN or caching
    # layer in front of the site serves stale content to non-browser requests
    # (observed: a fresh private-browser load shows the newest post correctly,
    # but a plain requests.get() without these was returning a stale version).
    cache_buster = str(int(time.time()))
    url = f"{WOD_URL}?_cb={cache_buster}"
    resp = requests.get(
        url, timeout=20,
        headers={
            "User-Agent": "havoc-tracker/1.0",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )
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
        messages=[{"role": "user", "content": (
            PARSE_PROMPT
            .replace("{known_movements}", ", ".join(KNOWN_MOVEMENTS))
            .replace("{known_benchmarks}", ", ".join(KNOWN_BENCHMARKS))
            .replace("{raw_text}", raw_text))}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return normalize_parsed(json.loads(text))


def workout_already_ingested(sb, workout_date: str) -> bool:
    """True if this date already has a workout with its Havoc segments loaded."""
    existing = sb.table("workouts").select("id").eq("workout_date", workout_date).execute()
    if not existing.data:
        return False
    segs = (
        sb.table("segments").select("id")
        .eq("workout_id", existing.data[0]["id"]).eq("source", "havoc").limit(1).execute()
    )
    return bool(segs.data)


def load_into_supabase(sb, wod: dict, parsed: dict, force: bool = False):
    # SAFETY: strength_results and wod_results are set to delete automatically along with
    # their segment. Deleting and rebuilding a day's segments therefore ERASES every
    # user's logged results for that day. So a day that is already loaded is never
    # rebuilt unless a human explicitly passes force=True.
    if not force and workout_already_ingested(sb, wod["workout_date"]):
        existing = sb.table("workouts").select("id").eq("workout_date", wod["workout_date"]).execute()
        return existing.data[0]["id"]

    movement_cache = load_movement_cache(sb)

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
        # Reached only when the day has no segments yet, or force=True was requested.
        # (With force=True this WILL erase logged results for that day — by design.)
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
            "description": seg.get("description"),
            "wod_name": seg.get("wod_name"),
        }
        seg_result = sb.table("segments").insert(seg_row).execute()
        segment_id = seg_result.data[0]["id"]

        for mv in seg.get("movements", []):
            movement_id = find_or_create_movement(sb, mv["name"], movement_cache)

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
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild a day that is already loaded. WARNING: this erases every user's "
             "logged results for that day.",
    )
    args = parser.parse_args()

    for var in ("ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Missing required environment variable: {var}")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    page_html = fetch_wod_page()
    wod = extract_latest_post(page_html)
    print(f"Latest post found: {wod['workout_date']} — {wod['source_title']}")

    if not args.force and workout_already_ingested(sb, wod["workout_date"]):
        print("Already loaded — leaving it untouched (no re-parse, no changes).")
        return

    parsed = parse_with_claude(wod["raw_text"])
    workout_id = load_into_supabase(sb, wod, parsed, force=args.force)
    print(f"Loaded workout_id={workout_id} with {len(parsed['segments'])} segments.")


if __name__ == "__main__":
    main()
