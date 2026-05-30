-- voodo solutions DB schema. Idempotent — safe to re-run via launch_db.sh.
-- Embedding dim is 384 (sentence-transformers/all-MiniLM-L6-v2).
-- Postgres 13+ provides gen_random_uuid() built-in (no pgcrypto needed).

create extension if not exists vector;

create table if not exists solutions (
    id uuid primary key default gen_random_uuid(),
    problem_summary text not null,
    steps jsonb not null default '[]'::jsonb,
    success boolean not null default true,
    os text not null default 'windows',
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists solutions_embedding_idx
    on solutions using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

create index if not exists solutions_created_at_idx
    on solutions (created_at desc);

-- Pending changes submitted by IT admins or the agent, awaiting Voodo approval.
create table if not exists pending_changes (
    id uuid primary key default gen_random_uuid(),
    type text not null check (type in ('add', 'delete')),
    solution_id uuid references solutions(id) on delete set null,
    problem_summary text not null,
    fix_description text,
    steps jsonb default '[]'::jsonb,
    reason text not null,
    submitted_by text not null default 'IT Admin',
    status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
    reviewer_note text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

-- Migration: add steps column when upgrading an existing installation.
alter table pending_changes add column if not exists steps jsonb default '[]'::jsonb;

create index if not exists pending_changes_status_idx
    on pending_changes (status);

create index if not exists pending_changes_created_at_idx
    on pending_changes (created_at desc);

-- End-of-run user feedback (👍/👎) on the most recent agent result.
-- Lightweight — keeps the agent honest about whether the user
-- actually got what they asked for, independent of the "success"
-- flag the agent set itself.
create table if not exists feedback (
    id uuid primary key default gen_random_uuid(),
    rating text not null check (rating in ('like', 'dislike')),
    success boolean,
    summary text,
    source text not null default 'browser',
    created_at timestamptz not null default now()
);

create index if not exists feedback_created_at_idx
    on feedback (created_at desc);

-- Friendly-name → canonical exe basename map for `open_app`. The model
-- often says "powerpoint" / "word"; Windows only knows the actual
-- exe name (powerpnt.exe, winword.exe). Loaded by server.db.client.get_open_app_aliases
-- and applied in server/agent/tools.py::dispatch before the allow-list check.
create table if not exists open_app_aliases (
    alias text primary key,
    canonical text not null
);

insert into open_app_aliases (alias, canonical) values
    ('powerpoint', 'powerpnt'),
    ('word',       'winword'),
    ('edge',       'msedge'),
    ('vscode',     'code'),
    ('calculator', 'calc')
on conflict (alias) do nothing;

create table if not exists app_instructions (
    topic text primary key,
    control_instruction text,
    guide_instruction text
);
