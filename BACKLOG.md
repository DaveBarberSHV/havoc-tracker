# Havoc Tracker — Backlog

Last updated: Oct 7, 2026

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
- [x] Home screen: shows the full workout with one button that adapts (Log Today's Results / Continue Logging / Review / Edit Results)

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

### Echo Bike Challenge (charity; real dates Nov 8-21) — BUILT, awaiting real-phone test
Built inside Havoc Tracker as a reusable "Challenges" feature. Dates, name and instructions live in the database.
- [x] Athlete enters calories (the CALORIES box on the monitor); a photo is REQUIRED
- [x] Date defaults to today, editable, limited to the challenge window (never the future)
- [x] Athletes see only their own total; no leaderboard; can edit or remove their own counted entries
- [x] Organizer page (organizer.html) for Anthony and Dave: totals, per-athlete entries with photos, reject/restore with a reason, CSV export
- [x] Name collected on first use; visible to organizers only
- [x] Photos shrunk before upload (about 210 KB per entry, so ~146 MB for 700 entries)
- [x] Private photo storage; organizers and the athlete themselves can see a photo, nobody else
- [x] Integrity flags for the organizer: same photo used twice, entered days late, edited
- [x] "Log Challenge Progress" button on the home screen, only while a challenge is active
- [ ] Run havoc_challenge_migration.sql, then deploy index.html and organizer.html
- [ ] Real-phone test with a few people (camera and photo upload on iPhone) before announcing
- [ ] Have Anthony sign in once, a few days early (check spam for the sign-in email)
- [ ] When ready, insert the real Nov 8-21 challenge (the SQL is commented at the bottom of the migration)
- [ ] After the challenge: export the CSV, then delete the photos
- [ ] Optional later: AI cross-check of the photo against the typed number, flagging mismatches (about $2 for ~700 photos; needs a small server-side function)

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
- [ ] Save the click-test scripts into the repo (tests/ folder). They currently live only in
      the working environment and caught several real bugs that syntax checks missed.

---

## Things worth remembering

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
