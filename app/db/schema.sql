-- Skema Supabase/PostgreSQL untuk Loopa (PRD bagian 11 + akun pengguna).
-- Jalankan SELURUH berkas ini di Supabase -> SQL Editor -> New query -> Run. Aman dijalankan ulang.
-- Tidak ada kolom untuk frame/video: hanya metrik dan event (NFR-01).
-- Backend memakai service_role (melewati RLS); RLS melindungi akses langsung dari browser (anon key).

-- ---------- profil pengguna (username & avatar bisa diedit) ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint username_format check (username is null or username ~ '^[A-Za-z0-9_.]{3,24}$')
);
create unique index if not exists profiles_username_lower_key on public.profiles (lower(username));

-- Buat profil otomatis saat pendaftaran (Google: avatar dari akun Google, username dari email, dibuat unik).
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  base text;
  candidate text;
begin
  base := lower(regexp_replace(coalesce(new.raw_user_meta_data->>'username', split_part(coalesce(new.email, 'looper'), '@', 1)), '[^A-Za-z0-9_.]', '', 'g'));
  if length(base) < 3 then base := 'looper'; end if;
  base := left(base, 18);
  candidate := base;
  while exists (select 1 from public.profiles where lower(username) = candidate) loop
    candidate := base || '_' || substr(md5(random()::text), 1, 4);
  end loop;
  insert into public.profiles (id, username, avatar_url)
  values (new.id, candidate, coalesce(new.raw_user_meta_data->>'avatar_url', new.raw_user_meta_data->>'picture'))
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- sesi belajar ----------
create table if not exists public.sessions (
  id text primary key,
  user_id uuid references auth.users(id) on delete set null,
  title text not null default 'Study Session',
  mandatory_break boolean not null default true,
  soundtrack text,
  reflection text check (reflection in ('good', 'okay', 'tough')),
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
create index if not exists sessions_user_started on public.sessions (user_id, started_at desc);

create table if not exists public.pomodoro_blocks (
  id text primary key,
  session_id text references public.sessions(id) on delete cascade,
  sequence_number int not null,
  planned_duration_seconds int not null,
  actual_active_seconds int default 0,
  paused_seconds int default 0,
  started_at timestamptz not null,
  ended_at timestamptz,
  status text not null,
  end_reason text
);

create table if not exists public.breaks (
  id text primary key,
  session_id text references public.sessions(id) on delete cascade,
  after_block_id text references public.pomodoro_blocks(id),
  planned_duration_seconds int not null,
  actual_duration_seconds int default 0,
  started_at timestamptz not null,
  ended_at timestamptz,
  status text not null
);

create table if not exists public.session_metrics (
  id bigserial primary key,
  session_id text references public.sessions(id) on delete cascade,
  block_id text references public.pomodoro_blocks(id),
  "timestamp" timestamptz not null,
  drowsiness_score int,
  drowsiness_status text,
  face_detected boolean,
  eye_state text,
  yawn_state text,
  head_state text
);

create table if not exists public.events (
  id text primary key,
  session_id text references public.sessions(id) on delete cascade,
  block_id text null,
  "timestamp" timestamptz not null,
  event_type text not null,
  duration_seconds real,
  metadata jsonb default '{}'::jsonb
);

create index if not exists events_session_ts on public.events (session_id, "timestamp");
create index if not exists metrics_session_ts on public.session_metrics (session_id, "timestamp");

-- ---------- Row Level Security ----------
alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.pomodoro_blocks enable row level security;
alter table public.breaks enable row level security;
alter table public.session_metrics enable row level security;
alter table public.events enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_select_own" on public.profiles for select using (auth.uid() = id);
create policy "profiles_update_own" on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "sessions_select_own" on public.sessions;
create policy "sessions_select_own" on public.sessions for select using (auth.uid() = user_id);

drop policy if exists "blocks_select_own" on public.pomodoro_blocks;
create policy "blocks_select_own" on public.pomodoro_blocks for select
  using (exists (select 1 from public.sessions s where s.id = session_id and s.user_id = auth.uid()));
drop policy if exists "breaks_select_own" on public.breaks;
create policy "breaks_select_own" on public.breaks for select
  using (exists (select 1 from public.sessions s where s.id = session_id and s.user_id = auth.uid()));
drop policy if exists "metrics_select_own" on public.session_metrics;
create policy "metrics_select_own" on public.session_metrics for select
  using (exists (select 1 from public.sessions s where s.id = session_id and s.user_id = auth.uid()));
drop policy if exists "events_select_own" on public.events;
create policy "events_select_own" on public.events for select
  using (exists (select 1 from public.sessions s where s.id = session_id and s.user_id = auth.uid()));
-- Tidak ada policy insert/update/delete untuk tabel sesi: hanya backend (service_role) yang menulis.
