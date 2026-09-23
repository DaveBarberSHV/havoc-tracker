-- CrossFit Havoc tracker — Supabase (Postgres) schema
-- Run this in the Supabase SQL Editor.
--
-- Design: the daily class WOD (workouts/movements/havoc-sourced segments) is
-- shared reference data, same for every user. Personal logs (results, custom
-- segments, activities) carry user_id and are protected by RLS so each
-- person only ever sees their own.

create extension if not exists "uuid-ossp";

-- ============================================================
-- SHARED / REFERENCE DATA (same for everyone, written only by
-- the nightly scraper job using the service_role key, which
-- bypasses RLS)
-- ============================================================

create table workouts (
    id              bigint generated always as identity primary key,
    workout_date    date not null unique,
    source_title    text,
    source_url      text,
    raw_text        text not null,
    parsed_at       timestamptz,
    parse_version   text,
    scraped_at      timestamptz not null default now()
);

create table movements (
    id              bigint generated always as identity primary key,
    name            text not null unique,
    category        text
);

create table segments (
    id              bigint generated always as identity primary key,
    workout_id      bigint not null references workouts(id) on delete cascade,
    segment_order   integer not null,
    segment_type    text not null check (segment_type in
                        ('warmup','strength','wod','accessory','skill','other')),
    title           text,
    structure_type  text,
    raw_text        text not null,
    score_type      text not null check (score_type in
                        ('load','reps','time','rounds_reps','distance','calories','none')),
    source          text not null default 'havoc' check (source in ('havoc','custom')),
    custom_type     text check (custom_type in
                        ('hyrox','zone2_machine','zone2_run','conditioning','other')),
    -- owner is null for havoc-sourced (shared) segments; set for a user's custom segment
    user_id         uuid references auth.users(id),
    skipped         boolean not null default false,
    notes           text
);

create table segment_movements (
    id                  bigint generated always as identity primary key,
    segment_id          bigint not null references segments(id) on delete cascade,
    movement_id         bigint not null references movements(id),
    movement_order      integer not null,
    prescribed_reps     text,
    prescribed_sets     integer,
    prescribed_scheme   text
);

create table wod_fingerprints (
    id              bigint generated always as identity primary key,
    segment_id      bigint not null references segments(id) on delete cascade,
    fingerprint     text not null,
    known_name      text
);
create index idx_fingerprint on wod_fingerprints(fingerprint);

-- ============================================================
-- PERSONAL DATA (per user, protected by RLS)
-- ============================================================

create table strength_results (
    id                  bigint generated always as identity primary key,
    user_id             uuid not null references auth.users(id) default auth.uid(),
    segment_id          bigint not null references segments(id) on delete cascade,
    movement_id         bigint not null references movements(id),
    set_number          integer not null,
    reps_completed      integer,
    weight_lbs          numeric,
    rpe                 numeric,
    notes               text,
    logged_at           timestamptz not null default now()
);

create table wod_results (
    id                  bigint generated always as identity primary key,
    user_id             uuid not null references auth.users(id) default auth.uid(),
    segment_id          bigint not null references segments(id) on delete cascade,
    score_type          text not null check (score_type in
                            ('time','reps','rounds_reps','distance','calories','load')),
    time_seconds        integer,
    rounds_completed    integer,
    extra_reps          integer,
    total_reps          integer,
    distance_value       numeric,
    distance_unit        text,
    calories            integer,
    rx_or_scaled         text check (rx_or_scaled in ('rx','scaled','rx+')),
    scale_notes         text,
    machine              text,
    avg_hr               integer,
    max_hr               integer,
    notes               text,
    logged_at           timestamptz not null default now()
);

create table activities (
    id                  bigint generated always as identity primary key,
    user_id             uuid not null references auth.users(id) default auth.uid(),
    workout_id          bigint references workouts(id),
    garmin_activity_id  text unique,
    start_time          timestamptz,
    duration_seconds    integer,
    avg_hr              integer,
    max_hr              integer,
    calories            integer,
    training_load       numeric,
    raw_json            jsonb
);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

-- Shared reference tables: readable by any authenticated user;
-- writes only via service_role key (the nightly job), which bypasses RLS entirely.
alter table workouts enable row level security;
alter table movements enable row level security;
alter table segment_movements enable row level security;
alter table wod_fingerprints enable row level security;

create policy "workouts readable by authenticated users"
    on workouts for select using (auth.role() = 'authenticated');
create policy "movements readable by authenticated users"
    on movements for select using (auth.role() = 'authenticated');
create policy "segment_movements readable by authenticated users"
    on segment_movements for select using (auth.role() = 'authenticated');
create policy "fingerprints readable by authenticated users"
    on wod_fingerprints for select using (auth.role() = 'authenticated');

-- segments: havoc-sourced rows (user_id is null) are readable by everyone;
-- custom rows are only visible/writable by their owner.
alter table segments enable row level security;

create policy "havoc segments readable by authenticated users"
    on segments for select using (source = 'havoc' and auth.role() = 'authenticated');
create policy "own custom segments readable"
    on segments for select using (source = 'custom' and auth.uid() = user_id);
create policy "insert own custom segments"
    on segments for insert with check (source = 'custom' and auth.uid() = user_id);
create policy "update own custom segments"
    on segments for update using (source = 'custom' and auth.uid() = user_id);
create policy "delete own custom segments"
    on segments for delete using (source = 'custom' and auth.uid() = user_id);

-- Personal logs: strictly owner-only, full CRUD.
alter table strength_results enable row level security;
alter table wod_results enable row level security;
alter table activities enable row level security;

create policy "own strength_results" on strength_results
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own wod_results" on wod_results
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own activities" on activities
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
