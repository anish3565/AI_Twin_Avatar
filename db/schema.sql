create extension if not exists pgcrypto;

create table if not exists invite_links (
    code          text primary key,
    company       text not null,
    job_title     text,
    date_applied  date,
    notes         text,
    created_at    timestamptz not null default now()
);

create table if not exists visitors (
    id            uuid primary key default gen_random_uuid(),
    name          text,
    email         text,
    company       text,
    role          text,
    linkedin_url  text,
    consent_at    timestamptz not null,
    created_at    timestamptz not null default now()
);

create table if not exists sessions (
    id            uuid primary key default gen_random_uuid(),
    visitor_id    uuid references visitors(id) on delete set null,
    invite_code   text references invite_links(code) on delete set null,
    started_at    timestamptz not null default now(),
    ended_at      timestamptz,
    device        text,
    country       text,
    referrer      text,
    voice_used    boolean not null default false,
    summary       text,
    tags          text[] not null default '{}',
    message_count integer not null default 0 check (message_count >= 0)
);

create table if not exists messages (
    id                uuid primary key default gen_random_uuid(),
    session_id        uuid not null references sessions(id) on delete cascade,
    question          text not null,
    reply             text,
    provider          text,
    model             text,
    prompt_tokens     integer,
    completion_tokens integer,
    ttft_ms           integer,
    total_ms          integer,
    outcome           text not null check (outcome in ('answered', 'unknown', 'refused', 'error')),
    error_type        text,
    fallback_used     boolean not null default false,
    rating            smallint check (rating in (-1, 1)),
    created_at        timestamptz not null default now()
);

create table if not exists unknown_questions (
    id            uuid primary key default gen_random_uuid(),
    message_id    uuid references messages(id) on delete cascade,
    question      text not null,
    resolved      boolean not null default false,
    created_at    timestamptz not null default now()
);

create table if not exists events (
    id            uuid primary key default gen_random_uuid(),
    session_id    uuid references sessions(id) on delete cascade,
    name          text not null,
    component     text,
    duration_ms   integer,
    success       boolean,
    detail        jsonb,
    created_at    timestamptz not null default now()
);

create index if not exists sessions_invite_code_idx on sessions (invite_code);
create index if not exists sessions_visitor_id_idx on sessions (visitor_id);
create index if not exists messages_session_id_idx on messages (session_id, created_at);
create index if not exists messages_created_at_idx on messages (created_at);
create index if not exists unknown_questions_unresolved_idx on unknown_questions (resolved) where resolved = false;
create index if not exists events_session_id_idx on events (session_id);
create index if not exists events_created_at_idx on events (created_at);

alter table invite_links enable row level security;
alter table visitors enable row level security;
alter table sessions enable row level security;
alter table messages enable row level security;
alter table unknown_questions enable row level security;
alter table events enable row level security;

create policy "public can insert sessions" on sessions for insert to anon, authenticated with check (true);
create policy "public can insert messages" on messages for insert to anon, authenticated with check (true);
create policy "public can insert unknown questions" on unknown_questions for insert to anon, authenticated with check (true);
create policy "public can insert events" on events for insert to anon, authenticated with check (true);
create policy "public can insert visitors with consent" on visitors for insert to anon, authenticated with check (consent_at is not null);
