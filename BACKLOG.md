# Havoc Tracker — Backlog

Last updated: Oct 22, 2026

Check items off rather than deleting them, so there's a record of what's been
considered. Add new ideas under the closest heading as they come up.

---

## Done

**Sign-in and accounts**
- [x] Magic-link sign-in that stays signed in (use a Safari bookmark, not Home Screen)
- [x] Resend domain verified, so sign-in emails reach any address (not just the account owner)
- [x] Per-user data isolation (row-level security), tested across multiple real accounts
- [x] Settled on dave@safeharbourventures.com as the main identity

**Daily entry**
- [x] Weight entry: hold-to-accelerate buttons, tap-the-number to type, no accidental zoom
- [x] Bodyweight movements: reps-only entry, optional added weight (e.g. GHD with a ball)
- [x] Cardio rounds (bike/row/ski/run): minutes, seconds, optional calories
- [x] Resume where you left off after closing the app mid-workout
- [x] Duplicate-entry protection; optional notes on every entry
- [x] Pick a Day: review any past day and edit or add individual sets
- [x] Custom workouts for days the gym doesn't post (Hyrox, Zone 2, conditioning, other)
- [x] Hamburger menu on every page, with a back arrow only where there's somewhere to go back to
- [x] WOD details: written description, benchmark name, and the full post as published
- [x] Complexes are ONE movement scored by the heaviest weight (a plain PR, no 1RM or estimate). "Havocomplex Snatch" and "Havocomplex Clean" are recognized by name, and the nightly job merges them back if the parser ever splits one into its component lifts
- [x] Every lift, skill, row/run test and benchmark name from the gym's record board is recognized (movements seeded; benchmark names like Fran, Fight Gone Bad, Filthy Fifty, King Kong are passed to the parser). No leaderboard in the app, by choice
- [x] The nightly job matches movements regardless of spelling ("Pull-ups" / "Pull-up"), so variants reuse the existing record instead of creating duplicates
- [x] The first split Havocomplex Snatch day was repaired by SQL, and the PR recorded correctly
- [x] Power Total (Back Squat + Bench Press + Deadlift) and CrossFit Total (Back Squat + Strict Press + Deadlift): three lifts done in the SAME session and added together. The total shows on the day (home screen and Day Review, with "First total recorded" / "New Total PR") and the best one is on the Personal Records page. Hand-entered lifts count as one session when they share a date. The nightly job records a total as its three lifts, and "Shoulder Press" is recognized as the Strict Press
- [x] Bodyweight movements are counted, not weighed: Toes to Rings (and Toes to Bar, T2R/T2B, Knees to Chest/Elbows, Chest to Bar, hanging knee/leg raises, V-ups, wall walks, back extensions, inchworms, jump squats) now show a reps stepper, one at a time. "Weighted" versions still use pounds
- [x] Day Review shows an "Added weight" box for a bodyweight set that carries a stray weight, so it can be cleared (blank or 0 means none)
- [x] "N Rounds for Time" workouts are scored by time. The parser had read "20 rounds for time" as a rounds-and-reps workout. The nightly job now decides from the workout's own words ("for time" = time score, "as many rounds as possible" = rounds and reps) and leaves anything ambiguous exactly as parsed. Today's mis-scored workout was repaired by SQL (preview, then apply)
- [x] Home screen: shows the full workout with one button that adapts (Log Today's WOD Results / Continue Logging WOD Results / Review / Edit WOD Results)

**Records and history**
- [x] Weekly summary (days logged, reps, volume, PRs)
- [x] Movement History for every lift, plus a plain chronological list for custom workouts
- [x] Actual 1RM (a real single) tracked separately from calculated 1RM (estimated)
- [x] Personal Records page listing every lift's records
- [x] Enter a past PR by hand, including lifts not on the list and bodyweight rep records

**Reliability**
- [x] Nightly job runs four times a day, every day, with cache-busting
- [x] Nightly job no longer erases logged results when it re-runs on an already-loaded day
- [x] Permission fixes: custom workouts on no-post days, adding new lift names

---

## Open

### Verify soon
- [ ] Run QUERY 2 of fix_wod_scoring_preview.sql once to see whether any OLDER workout was scored the wrong way (it only reads). If any show up, they can be fixed the same way
- [ ] Confirm the first real Havocomplex day after the fix comes through as one movement with no manual repair (the first one was repaired by hand)
- [ ] Run check_movements.sql to see whether the database already holds duplicate movements (for example "Shoulder Press" next to "Strict Press"), then merge any that exist with a safe SQL fix
- [ ] **Check the first new workout after the latest deploy.** The WOD description and
      benchmark name come from Claude's reading of the post and couldn't be tested live.
      Confirm the description looks right on that day's WOD screen.
- [ ] **Ask testers whether any logged results ever disappeared.** The nightly-job bug
      (now fixed) could have erased a day's results if it ran at the wrong moment. Unclear
      whether it ever did.
- [ ] Confirm Supabase's email sender is havoc@safeharbourventures.com (the alias exists).
- [ ] Rerun the usage queries (check_usage.sql) in a week to see who's actually logging.

### Rollout
- [ ] Widen beyond the current handful of testers once things stay quiet for a stretch
- [ ] Decide whether to keep the current github.io URL or move to a custom domain.
      Cheapest to change before many people have it bookmarked.
- [ ] A simple feedback channel (group text or shared note) so reports don't all route through one person
- [ ] Resend free tier is 100 emails/day; fine for now, revisit if invites come in waves

### Echo Bike Challenge — BUILT AND TESTED, ON HOLD (switched off in the app)
Anthony postponed the Nov 8-21 challenge. Everything is built, was tested on real phones (including the photo upload), and is parked rather than deleted. It is a reusable "Challenges" feature: the dates, name and instructions live in the database, so the next one needs no new code.

**What exists (all working, just switched off)**
- Athletes enter the calories shown on the bike, with a REQUIRED photo; date defaults to today and can be back-dated within the challenge
- Each athlete sees only their own entries and total; edit or remove their own counted entries
- Leaderboard: rank, name ("Alice S." or Anonymous, the athlete's choice), total; ties share a rank; gym-wide total; final standings stay up 21 days after the end
- Organizer page (organizer.html) for Anthony and Dave: totals per athlete, photo thumbnails, reject/restore with a reason, CSV export, and flags for the same photo used twice, entries logged days late, entries over 100 calories, and edits ("edited from 94")
- Entries count the moment they are saved; the organizer can reject at any time and totals update immediately
- Photos are shrunk before upload (about 210 KB each) and stored privately; only the athlete and organizers can see them
- The database rules were tested on a real PostgreSQL (athletes cannot see each other's data or change their own status)

**How to switch it off and on**
- It is OFF now: `const CHALLENGES_ENABLED = false;` near the top of the script in index.html. While false, the home screen shows no challenge button, no results button and no organizer link, and the app makes no challenge database calls.
- TO BRING IT BACK:
  1. In index.html, change that line to `const CHALLENGES_ENABLED = true;`
  2. Add the new challenge in the Supabase SQL Editor. The template is commented out at the bottom of havoc_challenge_migration.sql (name, instructions, start and end dates). The old test challenge row is harmless.
  3. Check that the organizers are still on the list (challenge_admins table: prochargedgt@aol.com and dave@safeharbourventures.com)
  4. Push the change, then do a quick end-to-end test on a phone: log an entry with a photo, see it on the organizer page, reject and restore it
  5. Make a challenge poster (the old one had Nov 8-21 on it)
- The database changes were already made (havoc_challenge_migration.sql, then havoc_leaderboard_migration.sql). Do NOT run them again for a new challenge; they only need to exist once. Keep copies of both in the repo (db/ folder) as the record of how the tables were built.
- Nothing is lost while it is off: test entries and names stay in the database.

**Housekeeping**
- [ ] Save havoc_challenge_migration.sql and havoc_leaderboard_migration.sql into the repo's db/ folder so the setup lives with the code
- [ ] When the next challenge is scheduled: follow "TO BRING IT BACK" above
- [ ] Optional later: AI cross-check of the photo against the typed number, flagging mismatches (about $2 for ~700 photos; needs a small server-side function)

### Ideas to decide
- [ ] **Estimated 1RM from very high-rep sets.** The Epley formula is only reliable up to about 10 reps, so a set of 15 or 20 gives a nonsense estimate and could trigger an "est. 1RM high" badge. Option: ignore sets over 10 reps when estimating.
- [ ] **20 Rep Total**: its definition is unclear (the board's weights don't look like one set of 20 back squats). Deliberately NOT interpreted by the app or the nightly job until it's confirmed
- [ ] Zercher Squat: an unlabeled box on the record board. Nothing to do; it is created automatically if a post uses it
- [ ] If the parser gets a workout's scoring wrong again, a small in-app option to score it differently would avoid needing a SQL repair. Not built; the parser safeguard should make this rare

### Entry app
- [ ] **Editable reps** for strength sets. Currently locked to the number in the prescribed
      scheme (a range like "8-10" is read as 8).
- [ ] **Delete a mistaken set or WOD result** from Day Review (today you can edit, but not delete,
      except for hand-entered PRs).
- [ ] **Passkey / Face ID sign-in** would remove the email step entirely. Supabase's support
      is still in beta, so expect real-device debugging.
- [ ] Native app via Capacitor + TestFlight, as a fallback if the web approach ever falls short.
      Needs a $99/yr Apple developer account; builds expire every 90 days.

### History and insights
- [ ] **Repeat-WOD detection**: when today's WOD matches one you've done, show past attempts side
      by side. The wod_fingerprints table exists but isn't filled in. The new WOD names and
      descriptions give a much better starting point than before.
- [ ] Weekly summary: compare against last week, not just this week
- [ ] Movement History's "N sessions" label actually counts sets. Count distinct workouts instead.
- [ ] Weekly PR cards can show a meaningless estimate for bodyweight lifts done with added
      weight (e.g. GHD with a ball). Skip estimate logic for rep-record movements.
- [ ] Clean-up tool for lift names: typos in custom lifts ("Zurcher" vs "Zercher") create
      separate lifts, and there's no way to merge them yet.

### Data pipeline
- [ ] If Havoc edits a post after publishing, the change is now ignored (the safe trade-off).
      A proper "update in place without touching results" path would handle this.
- [ ] Add WOD descriptions to older days (they currently use the parsed movement list plus the
      full post, which works well enough). Only worth doing with an in-place update, never a rebuild.
- [ ] Deeper historical backfill (about 3 months loaded). Low value: old days have no results attached.
- [ ] **Garmin integration**: pull heart rate and activity data and match it to workout days.
      The activities table is stubbed. This was the original goal for the whole project.

### Housekeeping
- [ ] Save every SQL file (the migrations, havoc_grants.sql and the check_*.sql reports) in the repo's db/ folder, in the order they were run, so the whole database can be rebuilt from the repo
- [x] Click-test scripts packaged as havoc-tests.zip. Unzip into the repo root (adds tests/ and db/), then `npm install` and `npm test`.
- [ ] Commit them, so they survive a reset of the working environment (they were lost once)

---

## Things worth remembering

- **Supabase changed how new tables work on Oct 30, 2026.** New tables in the public schema are no longer opened to the app automatically. Your existing tables are NOT affected. From now on, any migration that creates a table must include its own grants (copy the pattern in havoc_grants.sql) and the table must be added to that file. If the database is ever rebuilt (a new project, a test copy, a reset), run the schema and every migration, then havoc_grants.sql LAST. check_data_api_access.sql shows, for every table, whether row-level security is on and who can reach it.

- **Corrections to an already-loaded day's structure are done by SQL, not by re-running the job.** The job leaves a loaded day alone so it can never erase people's results.
- **Never run the nightly job with --force on a day people have logged.** It rebuilds the day's
  workout and erases everyone's results for it. Same for the backfill script's --force.
- **Supabase free tier allows 2 projects per person, across all organizations.** Creating
  another organization does not give extra free projects. When one project needs Pro, move
  that one to its own organization (a project transfer keeps its URL and keys unchanged).
- **Home Screen icons keep separate storage from Safari** on iPhone, so sign-in doesn't carry
  over. Use a Safari bookmark. A full PWA wouldn't change this.
- **Deploy order for changes that touch the database:** run the SQL first, then push the code.
- **After deploying, load the app once with ?v=N on the end** to get past a stale cached copy.
- The GitHub repo is public (required for free GitHub Pages). Only the Supabase publishable
  key is visible, and that's designed to be public. Real secrets stay in GitHub's encrypted secrets.
