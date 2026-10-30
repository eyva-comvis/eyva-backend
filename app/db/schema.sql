-- Skema Supabase/PostgreSQL (PRD bagian 11). Jalankan di SQL Editor Supabase.
-- Tidak ada kolom untuk frame/video: hanya metrik dan event (NFR-01).

create table sessions (
  id text primary key,
  user_id uuid null,
  started_at timestamptz not null,
  ended_at timestamptz,
  status text not null,
  configured_study_seconds int not null,
  configured_break_seconds int not null,
  total_study_seconds int default 0,
  total_break_seconds int default 0,
  total_pause_seconds int default 0,
  estimated_drowsy_seconds int default 0,
  blink_count int default 0,
  yawn_count int default 0,
  eye_closure_count int default 0,
  drowsiness_event_count int default 0,
  alert_1_count int default 0,
  alert_2_count int default 0,
  end_reason text
);

create table pomodoro_blocks (
  id text primary key,
  session_id text references sessions(id) on delete cascade,
  sequence_number int not null,
  planned_duration_seconds int not null,
  actual_active_seconds int default 0,
  paused_seconds int default 0,
  started_at timestamptz not null,
  ended_at timestamptz,
  status text not null,
  end_reason text
);

create table breaks (
  id text primary key,
  session_id text references sessions(id) on delete cascade,
  after_block_id text references pomodoro_blocks(id),
  planned_duration_seconds int not null,
  actual_duration_seconds int default 0,
  started_at timestamptz not null,
  ended_at timestamptz,
  status text not null
);

create table session_metrics (
  id bigserial primary key,
  session_id text references sessions(id) on delete cascade,
  block_id text references pomodoro_blocks(id),
  "timestamp" timestamptz not null,
  drowsiness_score int,
  drowsiness_status text,
  face_detected boolean,
  eye_state text,
  yawn_state text,
  head_state text
);

create table events (
  id text primary key,
  session_id text references sessions(id) on delete cascade,
  block_id text null,
  "timestamp" timestamptz not null,
  event_type text not null,
  duration_seconds real,
  metadata jsonb default '{}'::jsonb
);

create index on events (session_id, "timestamp");
create index on session_metrics (session_id, "timestamp");
