-- Tapedeck dashboard schema. Idempotent: safe to run on every deploy.

create table if not exists users (
  id          bigserial primary key,
  github_id   bigint unique not null,
  login       text not null,
  name        text,
  email       text,
  avatar_url  text,
  created_at  timestamptz not null default now()
);

create table if not exists orgs (
  id                      bigserial primary key,
  slug                    text unique not null,
  name                    text not null,
  plan                    text not null default 'free' check (plan in ('free', 'team', 'enterprise')),
  stripe_customer_id      text unique,
  stripe_subscription_id  text unique,
  subscription_status     text,
  current_period_end      timestamptz,
  created_at              timestamptz not null default now()
);

create table if not exists memberships (
  org_id      bigint not null references orgs(id) on delete cascade,
  user_id     bigint not null references users(id) on delete cascade,
  role        text not null check (role in ('owner', 'member')),
  created_at  timestamptz not null default now(),
  primary key (org_id, user_id)
);

create table if not exists invites (
  id            bigserial primary key,
  org_id        bigint not null references orgs(id) on delete cascade,
  github_login  text not null,
  created_by    bigint references users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create unique index if not exists invites_org_login on invites (org_id, lower(github_login));

create table if not exists projects (
  id          bigserial primary key,
  org_id      bigint not null references orgs(id) on delete cascade,
  slug        text not null,
  name        text not null,
  created_at  timestamptz not null default now(),
  unique (org_id, slug)
);

-- Only a SHA-256 hash of each token is stored; the token itself is shown once.
create table if not exists api_tokens (
  id            bigserial primary key,
  project_id    bigint not null references projects(id) on delete cascade,
  name          text not null,
  prefix        text not null,
  token_hash    text unique not null,
  created_by    bigint references users(id) on delete set null,
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz,
  revoked_at    timestamptz
);

-- One row per `tapedeck test --upload`. Only results are uploaded, never tapes.
create table if not exists runs (
  id                   bigserial primary key,
  project_id           bigint not null references projects(id) on delete cascade,
  created_at           timestamptz not null default now(),
  passed               boolean not null,
  commit_sha           text,
  branch               text,
  pr_number            integer,
  model                text not null,
  prompt_label         text,
  prompt_sha           text,
  baseline_prompt_sha  text,
  runs_per_case        integer not null,
  alpha                double precision not null,
  min_effect           double precision not null,
  cost_usd             double precision not null default 0,
  error_count          integer not null default 0,
  case_count           integer not null,
  regressed_count      integer not null
);
create index if not exists runs_project_time on runs (project_id, created_at desc);

create table if not exists case_results (
  run_id         bigint not null references runs(id) on delete cascade,
  case_id        text not null,
  base_passes    integer not null,
  base_n         integer not null,
  cand_passes    integer not null,
  cand_n         integer not null,
  p_adjusted     double precision not null,
  regressed      boolean not null,
  explanation    text,
  failing_check  text,
  primary key (run_id, case_id)
);

-- Stripe retries webhooks; each event is applied once.
create table if not exists stripe_events (
  id          text primary key,
  type        text not null,
  created_at  timestamptz not null default now()
);
