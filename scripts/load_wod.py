#!/usr/bin/env python3
"""
Load parsed WOD JSON (output of parse_wod.py) into the SQLite database.

Usage:
    python3 load_wod.py havoc.db samples/parsed_sample.json
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone


def get_or_create_movement(cur, name: str) -> int:
    cur.execute("SELECT id FROM movements WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO movements (name) VALUES (?)", (name,))
    return cur.lastrowid


def load_wod(cur, wod: dict):
    cur.execute(
        """INSERT OR REPLACE INTO workouts
           (id, workout_date, source_title, raw_text, parsed_at, parse_version)
           VALUES (
             (SELECT id FROM workouts WHERE workout_date = ?),
             ?, ?, ?, ?, ?)""",
        (
            wod["workout_date"], wod["workout_date"], wod["source_title"],
            wod["raw_text"], datetime.now(timezone.utc).isoformat(), "v1",
        ),
    )
    cur.execute("SELECT id FROM workouts WHERE workout_date = ?", (wod["workout_date"],))
    workout_id = cur.fetchone()[0]

    # Clear old segments for this workout in case of re-parse/reload
    cur.execute("DELETE FROM segments WHERE workout_id = ?", (workout_id,))

    for seg in wod["parsed"]["segments"]:
        cur.execute(
            """INSERT INTO segments
               (workout_id, segment_order, segment_type, title, structure_type,
                raw_text, score_type, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workout_id, seg["segment_order"], seg["segment_type"], seg["title"],
                seg["structure_type"], seg.get("title", ""), seg["score_type"],
                seg.get("notes"),
            ),
        )
        segment_id = cur.lastrowid

        for mv in seg.get("movements", []):
            movement_id = get_or_create_movement(cur, mv["name"])
            cur.execute(
                """INSERT INTO segment_movements
                   (segment_id, movement_id, movement_order, prescribed_reps,
                    prescribed_sets, prescribed_scheme)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    segment_id, movement_id, mv["movement_order"],
                    mv.get("prescribed_reps"), mv.get("prescribed_sets"),
                    mv.get("prescribed_scheme"),
                ),
            )

    return workout_id


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "havoc.db"
    json_path = sys.argv[2] if len(sys.argv) > 2 else "samples/parsed_sample.json"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    with open(json_path) as f:
        wods = json.load(f)

    for wod in wods:
        wid = load_wod(cur, wod)
        print(f"Loaded {wod['workout_date']} as workout_id={wid}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
