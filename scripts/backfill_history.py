#!/usr/bin/env python3
"""
Backfill CrossFit Havoc WOD history by crawling backward through each post's
"Previous post" link, parsing with Claude, and loading into Supabase.

Stops when it either:
  - runs out of "Previous post" links (reached the start of the blog)
  - hits --max-posts (safety cap, default 60)
  - hits --stop-date (don't load anything older than this date)

By default, a date already in the database is SKIPPED (no Claude call, no write)
but the crawl keeps walking backward past it — this matters if your database has
gaps rather than one unbroken streak from today. Pass --force to re-parse and
overwrite dates that are already loaded too.

Requires the same env vars as nightly_ingest.py:
    ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

Usage:
    python3 backfill_history.py --dry-run                 # crawl + parse, don't write
    python3 backfill_history.py                            # crawl + parse + write
    python3 backfill_history.py --start-url https://crossfithavoc.com/2026/09/16/wod-thursday-september-17th-4/
    python3 backfill_history.py --stop-date 2026-08-01
    python3 backfill_history.py --max-posts 90
"""
import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from dateutil import parser as dateparser

from nightly_ingest import parse_with_claude, load_into_supabase  # reuse the same logic

WOD_URL = "https://crossfithavoc.com/wod/"


def fetch(url: str) -> str:
    resp = requests.get(url, timeout=20, headers={"User-Agent": "havoc-tracker/1.0"})
    resp.raise_for_status()
    return resp.text


def find_latest_post_url() -> str:
    page_html = fetch(WOD_URL)
    match = re.search(
        r'<h2[^>]*>\s*<a[^>]+href="(https://crossfithavoc\.com/\d{4}/\d{2}/\d{2}/[^"]+)"',
        page_html,
    )
    if not match:
        raise RuntimeError("Could not find the latest post link on /wod/.")
    return match.group(1)


def parse_title_date(title: str, now=None) -> str:
    """Same logic as nightly_ingest.extract_latest_post: the workout date lives
    in the title text, not the URL (which is the publish date, one day earlier)."""
    now = now or datetime.now()
    title = html.unescape(title).replace("\xa0", " ").strip()
    title_for_date = re.sub(r'\b(\d{1,2})(st|nd|rd|th)\b', r'\1', title, flags=re.IGNORECASE)
    date_match = re.search(r'([A-Za-z]+ \d{1,2})', title_for_date)
    if not date_match:
        raise RuntimeError(f"Could not find a date in post title: {title!r}")
    parsed_date = dateparser.parse(f"{date_match.group(1)} {now.year}")
    if (parsed_date.date() - now.date()).days > 30:
        parsed_date = dateparser.parse(f"{date_match.group(1)} {now.year - 1}")
    return parsed_date.strftime("%Y-%m-%d")


def extract_single_post(page_html: str, url: str):
    title_match = re.search(r'<h1[^>]*>\s*([^<]+?)\s*</h1>', page_html)
    if not title_match:
        raise RuntimeError(f"Could not find post title (h1) on {url}")
    title = html.unescape(title_match.group(1)).replace("\xa0", " ").strip()
    workout_date = parse_title_date(title)

    # Body: from end of h1 to "Share this" section (or next h2/h3 as fallback)
    start = title_match.end()
    share_match = re.search(r'Share this', page_html[start:], re.IGNORECASE)
    if share_match:
        body_html = page_html[start:start + share_match.start()]
    else:
        next_heading = re.search(r'<h[23][^>]*>', page_html[start:])
        body_html = page_html[start:start + next_heading.start()] if next_heading else page_html[start:start + 3000]

    body_text = re.sub(r'<[^>]+>', '\n', body_html)
    body_text = html.unescape(body_text).replace("\xa0", " ")
    body_text = re.sub(r'\n\s*\n+', '\n\n', body_text).strip()

    # Previous post link: find the <a ...rel="prev"...> tag regardless of attribute order
    prev_url = None
    prev_tag_match = re.search(r'<a\s+([^>]*rel=["\']prev["\'][^>]*)>', page_html)
    if prev_tag_match:
        href_match = re.search(r'href=["\']([^"\']+)["\']', prev_tag_match.group(1))
        if href_match:
            prev_url = href_match.group(1)

    return {
        "workout_date": workout_date,
        "source_title": title,
        "source_url": url,
        "raw_text": body_text,
    }, prev_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-url", default=None, help="Post URL to start from (default: current latest post)")
    ap.add_argument("--stop-date", default=None, help="Don't load anything older than this YYYY-MM-DD")
    ap.add_argument("--max-posts", type=int, default=60, help="Safety cap on how many posts to crawl")
    ap.add_argument("--dry-run", action="store_true", help="Crawl and parse, but don't write to Supabase")
    ap.add_argument("--force", action="store_true", help="Re-parse and overwrite dates that are already in the database (default: skip them, but keep crawling backward)")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests (be polite to the site)")
    args = ap.parse_args()

    for var in ("ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Missing required environment variable: {var}")

    sb = None
    existing_dates = set()
    if not args.dry_run:
        from supabase import create_client
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        existing = sb.table("workouts").select("workout_date").execute()
        existing_dates = {row["workout_date"] for row in existing.data}
        print(f"Found {len(existing_dates)} workout(s) already in Supabase.")

    url = args.start_url or find_latest_post_url()
    loaded, skipped = 0, 0

    for i in range(args.max_posts):
        print(f"\n[{i+1}] Fetching {url}")
        page_html = fetch(url)
        wod, prev_url = extract_single_post(page_html, url)
        print(f"    {wod['workout_date']} — {wod['source_title']}")

        if args.stop_date and wod["workout_date"] < args.stop_date:
            print(f"    Reached stop-date {args.stop_date}. Done.")
            break

        already_loaded = wod["workout_date"] in existing_dates
        if already_loaded and not args.force:
            print(f"    Already in database — skipping (still crawling backward).")
            skipped += 1
        elif args.dry_run:
            print(f"    [dry-run] Would parse and load this post.")
        else:
            parsed = parse_with_claude(wod["raw_text"])
            workout_id = load_into_supabase(sb, wod, parsed)
            print(f"    Loaded workout_id={workout_id} with {len(parsed['segments'])} segments.")
            loaded += 1

        if not prev_url:
            print("\nNo more 'Previous post' link — reached the start of the blog.")
            break

        url = prev_url
        time.sleep(args.delay)

    print(f"\nDone. Loaded {loaded} workout(s), skipped {skipped} already-loaded date(s).")


if __name__ == "__main__":
    main()
