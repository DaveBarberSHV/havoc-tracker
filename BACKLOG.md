# Havoc Tracker — Backlog

Deferred items, in no particular priority order unless noted. Update this file
whenever something gets deferred or completed — check items off rather than
deleting them, so we keep a record of what's already been considered.

## Auth / accounts
- [ ] **Verify safeharbourventures.com in Resend** — removes the sandbox
      restriction so magic links can go to any email (davidrbarber@mac.com,
      wife, gym friends), not just the Resend account owner's address. Use a
      dedicated sender like havoc@safeharbourventures.com, not a personal inbox.
- [ ] **Passkey / Face ID sign-in** — would remove the email-hop entirely
      (no magic link, no storage-silo risk). Supabase's Passkey support is
      currently in beta; expect real-device debugging when we build this.
- [ ] **Decide on a single permanent identity** — early test data currently
      lives under davidrbarber@mac.com; more recent testing under
      dave@safeharbourventures.com. Consolidate before inviting others.
- [ ] **Native app via Capacitor + TestFlight** — fallback if Passkeys aren't
      enough. Requires $99/yr Apple Developer account, builds expire every
      90 days and need re-uploading. Bigger lift; only pursue if the web
      approach genuinely falls short.

## Entry app
- [x] Optional notes field on strength sets and WOD results
- [x] Duplicate-entry prevention (unique constraints + upsert)
- [x] Day picker to log/review a past workout
- [ ] **Faster weight entry** (in progress) — press-and-hold acceleration on
      the +/- buttons, plus tap-the-number for direct numeric entry. Also
      fixes the iOS double-tap-zoom bug on the stepper buttons.
- [ ] **Editable reps** for strength sets — currently defaults to the leading
      number parsed from the prescribed scheme (e.g. "8-10" → 8) with no way
      to adjust if you actually did a different rep count.
- [ ] **Custom/replacement workout logging** — schema already supports this
      (segments.source='custom', custom_type, skipped flag) but there's no
      UI for it yet. Needed for days you sub in Zone 2, Hyrox, etc. instead
      of the class WOD.
- [ ] **Undo / edit affordance** — no in-app way to fix a wrong entry once
      logged; currently requires editing directly in Supabase's Table Editor.

## History & insights
- [ ] **Movement history view** — pick a lift, see every session over time
      (weight, reps, est. 1RM) as a list + simple trend chart. Directly
      answers the original "what did I lift last time" problem.
- [ ] **WOD repeat detection** — wod_fingerprints table exists in the schema
      but isn't populated. Needs a fingerprinting step added to the ingest
      pipeline (normalize movements + rep scheme into a comparable key) so
      repeat WODs can be matched and compared automatically.
- [ ] **Weekly summary: trend vs. last week** — current summary shows this
      week only; comparing volume/PRs against the prior week would show
      real week-over-week progress.

## Data pipeline
- [ ] **Deeper historical backfill** — currently ~3 months loaded (capped by
      --max-posts). Low priority since old prescribed-only data (no results
      attached) has limited value — see the "why backfill" discussion.
- [ ] **Garmin integration** — pull HR/activity data and match it to workout
      days by date/time. The `activities` table is already stubbed in the
      schema for this. Original motivating goal for the whole project;
      revisit once the core logging loop is solid.

## Multi-user rollout
- [ ] Invite wife / gym friends — blocked on the Resend domain verification
      above, plus one more clean end-to-end test before wider rollout.
