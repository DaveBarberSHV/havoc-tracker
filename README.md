# CrossFit Havoc Tracker — Setup Guide

## What's in here
- `db/schema_supabase.sql` — run this once in the Supabase SQL Editor to create all tables + RLS
- `scripts/nightly_ingest.py` — fetches the WOD page, parses it with Claude, loads it into Supabase
- `.github/workflows/nightly.yml` — runs the script automatically, Mon–Fri, ~9:30pm ET
- `requirements.txt` — Python dependencies
- `db/schema.sql`, `scripts/parse_wod.py`, `scripts/load_wod.py`, `samples/` — the original SQLite prototype; kept for reference, not needed going forward

## One-time setup

### 1. Supabase
1. In your Supabase project, open **SQL Editor**.
2. Paste in the full contents of `db/schema_supabase.sql` and run it.
3. Go to **Project Settings → API** and copy:
   - **Project URL** → this is `SUPABASE_URL`
   - **service_role key** (NOT the anon/public key) → this is `SUPABASE_SERVICE_ROLE_KEY`

### 2. GitHub repo
1. Create a new **private** GitHub repo and push this folder to it.
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add three secrets:
   - `ANTHROPIC_API_KEY` — your `havoc_tracker` key from the Anthropic Console
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
3. That's it — the workflow in `.github/workflows/nightly.yml` will pick these up automatically.

### 3. Test it manually first
Before waiting for the schedule, trigger it by hand:
- Go to the **Actions** tab in your repo → **Nightly WOD Ingest** → **Run workflow**.
- Check the logs, then check the Supabase **Table Editor** to confirm rows landed in `workouts` and `segments`.

You can also run it locally from your own Terminal to test/debug faster:
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
export SUPABASE_URL=your_project_url
export SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
python3 scripts/nightly_ingest.py
```

## Notes
- The scraper only ever pulls the **most recent** post on the page — it does not currently
  backfill history. Backfilling requires either pagination through older `/wod/` pages or the
  WordPress.com REST API; that's the next thing to build once tonight's flow is confirmed working.
- Holidays / weekends: since CF Havoc doesn't post Sat/Sun or major holidays, the workflow simply
  won't find a "new" post those days — no special handling needed, it's a safe no-op.
- The `SUPABASE_SERVICE_ROLE_KEY` bypasses Row Level Security — that's required here since the
  nightly job writes shared reference data (the class WOD) that isn't owned by any one user.
  Never put this key in a front-end app; only the anon/public key belongs there.
