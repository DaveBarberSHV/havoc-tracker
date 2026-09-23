#!/usr/bin/env python3
"""
Parse a raw CrossFit Havoc WOD text blob into structured JSON using the
Claude API. This is the core of the nightly ingestion pipeline.

Usage:
    python3 parse_wod.py samples/sample_wods.json
"""
import json
import os
import sys
import urllib.request

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
          "prescribed_scheme": "free text description of the scheme for this movement, e.g. 'EMOM x10 @ 1:30, increase weight as you go'"
        }
      ],
      "notes": "anything relevant not captured above, or null"
    }
  ]
}

Rules:
- The warmup is always its own segment, segment_type "warmup", score_type "none".
- If a block says "increase weight as you go" or similar, capture that in prescribed_scheme -
  it means the person logging results should expect multiple different weights across sets.
- A strength/weightlifting block (barbell lifts done for sets x reps, EMOM, etc. that isn't the
  main conditioning piece) should be segment_type "strength" and score_type "load" if it's a
  loaded barbell/dumbbell/kettlebell movement, or "reps" if it's bodyweight-for-reps like
  GHD sit-ups, pull-ups, or handstand push-ups done as a standalone strength/skill block.
- The main conditioning piece (usually last, often labeled "For Time", "AMRAP", "EMOM", etc.)
  is segment_type "wod". Its score_type should be:
    - "time" if it's "for time"
    - "rounds_reps" if it's an AMRAP
    - "reps" if it's a fixed-time max-reps effort
    - "calories" or "distance" if the entire piece is a single monostructural effort (e.g. "50 cal bike for time" - actually this would be score_type "time" since it's FOR TIME; use "calories"/"distance" only if the piece is scored purely in calories or distance/meters, e.g. "Max Calorie Bike in 5 minutes").
- prescribed_sets should be an integer when a number of sets/rounds is explicit (e.g. "Every 1:30 for 10 Sets" -> 10). Use null if not applicable/unclear.
- Keep movement names consistent in casing (Title Case) and singular where natural (e.g. "Pull-up" not "Pull-ups") so repeats match across days.
- Do not invent information not present in the text.

Here is the workout text to parse:

---
{raw_text}
---
"""


def call_claude(raw_text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY in your environment")

    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "messages": [
            {"role": "user", "content": PARSE_PROMPT.replace("{raw_text}", raw_text)}
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    text = "".join(block.get("text", "") for block in data.get("content", []))
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_wods.json"
    with open(path) as f:
        wods = json.load(f)

    results = []
    for wod in wods:
        print(f"Parsing {wod['workout_date']} — {wod['source_title']}...", file=sys.stderr)
        parsed = call_claude(wod["raw_text"])
        results.append({**wod, "parsed": parsed})

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
