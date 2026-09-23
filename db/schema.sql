-- CrossFit Havoc tracker schema
-- Designed for SQLite (prototype) — same schema ports cleanly to Postgres/Supabase later.

PRAGMA foreign_keys = ON;

-- One row per day's post scraped from the site.
CREATE TABLE workouts (
    id              INTEGER PRIMARY KEY,
    workout_date    TEXT NOT NULL UNIQUE,   -- 'YYYY-MM-DD'
    source_title    TEXT,                   -- e.g. "WOD Thursday September 17th"
    source_url      TEXT,
    raw_text        TEXT NOT NULL,          -- untouched scraped text, always kept
    parsed_at       TEXT,                   -- timestamp when LLM parsing ran
    parse_version   TEXT,                   -- prompt/schema version, for re-parsing later
    scraped_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per labeled block within a day: warmup / strength / wod / accessory / etc.
-- A day can have more than one strength block or more than one WOD-scored block (rare but happens).
CREATE TABLE segments (
    id              INTEGER PRIMARY KEY,
    workout_id      INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    segment_order   INTEGER NOT NULL,       -- 1,2,3... order within the day
    segment_type    TEXT NOT NULL CHECK (segment_type IN
                        ('warmup','strength','wod','accessory','skill','other')),
    title           TEXT,                   -- "Push Press", "AMRAP 16", free label
    structure_type  TEXT,                   -- 'sets_reps','emom','amrap','for_time','tabata','max_effort','none'
    raw_text        TEXT NOT NULL,          -- the parsed slice of text for this segment
    -- scoring shape for RESULTS logged against this segment:
    score_type      TEXT NOT NULL CHECK (score_type IN
                        ('load','reps','time','rounds_reps','distance','calories','none')),
    source          TEXT NOT NULL DEFAULT 'havoc' CHECK (source IN ('havoc','custom')),
    custom_type     TEXT CHECK (custom_type IN
                        ('hyrox','zone2_machine','zone2_run','conditioning','other')),
                                            -- only set when source = 'custom'
    skipped         INTEGER NOT NULL DEFAULT 0,   -- 1 = the class did this, but you didn't (e.g. you subbed a custom workout)
    notes           TEXT
);

-- Canonical movement list, so "Back Squat" always matches "back squat" / "BACK SQUATS"
CREATE TABLE movements (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,           -- normalized display name
    category        TEXT                            -- 'barbell','gymnastics','monostructural','kb_db','other'
);

-- Movements referenced within a segment, with the prescribed scheme (parsed, best-effort).
-- For strength work this is typically one row per movement per segment.
-- For a WOD this can be multiple rows (e.g. pull-ups, burpee box jump overs, clean and jerks).
CREATE TABLE segment_movements (
    id                  INTEGER PRIMARY KEY,
    segment_id          INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    movement_id         INTEGER NOT NULL REFERENCES movements(id),
    movement_order      INTEGER NOT NULL,
    prescribed_reps     TEXT,       -- e.g. "3", "8-10", "50 cal" — kept as text, free-form
    prescribed_sets     INTEGER,    -- e.g. 5 (sets), null if not applicable
    prescribed_scheme   TEXT        -- e.g. "EMOM x10 @ 1:30", raw scheme description
);

-- A "WOD fingerprint" lets us detect repeats even when wording varies slightly.
-- Populated by the LLM parse step: normalized movement list + rep scheme, hashed.
CREATE TABLE wod_fingerprints (
    id              INTEGER PRIMARY KEY,
    segment_id      INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    fingerprint     TEXT NOT NULL,      -- hash or normalized key, e.g. "amrap16|pullup:8|burpee_bjo:4|clean_jerk:2"
    known_name      TEXT                -- if it's a named benchmark, e.g. "Fran", "Grace" (nullable)
);
CREATE INDEX idx_fingerprint ON wod_fingerprints(fingerprint);

-- YOUR results for a strength segment: one row per set, one row per rep if weight varies per rep.
-- Simplest durable model: one row per SET, with reps done at that set and weight used.
-- If every rep in a set is the same weight (99% of cases), reps_completed covers it.
CREATE TABLE strength_results (
    id                  INTEGER PRIMARY KEY,
    segment_id          INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    movement_id         INTEGER NOT NULL REFERENCES movements(id),
    set_number          INTEGER NOT NULL,
    reps_completed      INTEGER,
    weight_lbs          REAL,          -- null when movement is bodyweight (e.g. HSPU, pull-ups, GHD sit-ups)
    rpe                 REAL,          -- optional, if you ever want to log perceived effort
    notes               TEXT,
    logged_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- YOUR result for a WOD-scored segment: one row per attempt (normally one per day).
CREATE TABLE wod_results (
    id                  INTEGER PRIMARY KEY,
    segment_id          INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    score_type          TEXT NOT NULL CHECK (score_type IN
                            ('time','reps','rounds_reps','distance','calories','load')),
    time_seconds        INTEGER,        -- for score_type = 'time' (e.g. 8:15 -> 495)
    rounds_completed    INTEGER,        -- for 'rounds_reps'
    extra_reps          INTEGER,        -- for 'rounds_reps' (the "+N reps" after full rounds)
    total_reps          INTEGER,        -- for 'reps'
    distance_value      REAL,           -- for 'distance'
    distance_unit       TEXT,
    calories            INTEGER,        -- for 'calories'
    rx_or_scaled         TEXT CHECK (rx_or_scaled IN ('rx','scaled','rx+')),
    scale_notes         TEXT,           -- what you scaled, if anything
    machine              TEXT,           -- optional modality tag: 'bike','row','ski','run','other' — useful for zone2/hyrox/conditioning entries
    avg_hr               INTEGER,        -- optional manual entry until Garmin sync is wired up
    max_hr               INTEGER,
    notes               TEXT,
    logged_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Placeholder for future Garmin integration — one row per activity, linked to a workout day.
CREATE TABLE activities (
    id                  INTEGER PRIMARY KEY,
    workout_id          INTEGER REFERENCES workouts(id),
    garmin_activity_id  TEXT UNIQUE,
    start_time          TEXT,
    duration_seconds    INTEGER,
    avg_hr              INTEGER,
    max_hr              INTEGER,
    calories            INTEGER,
    training_load       REAL,
    raw_json            TEXT            -- full Garmin payload, for future-proofing
);
