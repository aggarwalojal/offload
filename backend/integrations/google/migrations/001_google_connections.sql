-- Run once in the shared Supabase project's SQL editor. This table is additive;
-- it does not modify Eva's application tables. Only the backend secret key can
-- read/write it. Ciphertext is also bound to the row's user_id and Google sub.
create table if not exists public.timeslice_google_connections (
  user_id uuid primary key references auth.users(id) on delete cascade,
  google_sub text not null,
  credentials_ciphertext text not null,
  updated_at timestamptz not null default now()
);
alter table public.timeslice_google_connections enable row level security;
revoke all on public.timeslice_google_connections from anon, authenticated;
grant select, insert, update, delete on public.timeslice_google_connections to service_role;
