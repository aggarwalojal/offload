-- Durable reservations prevent duplicate Google Tasks inserts on worker retries.
create table if not exists public.timeslice_task_executions (
  user_id uuid not null references auth.users(id) on delete cascade,
  action_id text not null,
  payload_hash text not null,
  external_id text,
  created_at timestamptz not null default now(),
  primary key (user_id, action_id)
);
alter table public.timeslice_task_executions enable row level security;
revoke all on public.timeslice_task_executions from anon, authenticated;
grant select, insert, update on public.timeslice_task_executions to service_role;

create or replace function public.timeslice_reserve_task(p_user_id uuid, p_action_id text, p_payload_hash text)
returns table(payload_hash text, external_id text, reserved boolean)
language plpgsql set search_path = public as $$
declare inserted_count integer;
begin
  insert into public.timeslice_task_executions(user_id, action_id, payload_hash)
  values (p_user_id, p_action_id, p_payload_hash) on conflict do nothing;
  get diagnostics inserted_count = row_count;
  return query select t.payload_hash, t.external_id, inserted_count = 1
    from public.timeslice_task_executions t where t.user_id = p_user_id and t.action_id = p_action_id;
end;
$$;
revoke all on function public.timeslice_reserve_task(uuid, text, text) from public, anon, authenticated;
grant execute on function public.timeslice_reserve_task(uuid, text, text) to service_role;
