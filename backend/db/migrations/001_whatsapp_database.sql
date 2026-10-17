-- Run once in the Supabase SQL editor. Backend functions are service-role only.
begin;

create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  whatsapp_number text not null unique check (whatsapp_number ~ '^whatsapp:\+[1-9][0-9]{6,14}$'),
  timezone text not null default 'America/New_York',
  whatsapp_opt_in boolean not null default false,
  morning_enabled boolean not null default false,
  evening_enabled boolean not null default false,
  morning_time time not null default '08:00',
  evening_time time not null default '21:00',
  last_inbound_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.time_entries (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  title text not null check (length(title) between 1 and 300 and length(btrim(title)) > 0),
  category text not null check (category in ('academics','career','social','health','admin')),
  start_time timestamptz,
  end_time timestamptz,
  duration_minutes numeric generated always as (extract(epoch from (end_time-start_time))/60) stored,
  status text not null check (status in ('proposed','needs_clarification','executing','completed','failed')),
  external_id text check (external_id is null or length(btrim(external_id)) > 0),
  source text not null default 'whatsapp' check (source in ('whatsapp','dashboard','google')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((start_time is null and end_time is null) or
         (start_time is not null and end_time is not null and end_time > start_time)),
  check (status not in ('executing','completed') or start_time is not null),
  check (status <> 'completed' or external_id is not null),
  unique (user_id, external_id)
);

create table public.tasks (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  title text not null check (length(title) between 1 and 300 and length(btrim(title)) > 0),
  category text not null check (category in ('academics','career','social','health','admin')),
  due_date date,
  status text not null check (status in ('proposed','needs_clarification','executing','completed','failed')),
  external_id text check (external_id is null or length(btrim(external_id)) > 0),
  source text not null default 'whatsapp' check (source in ('whatsapp','dashboard','google')),
  completed_at timestamptz, -- Actual task completion; status=completed means Google sync succeeded.
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status <> 'completed' or external_id is not null),
  unique (user_id, external_id)
);

create table public.whatsapp_inbox (
  id text primary key, -- Twilio MessageSid
  user_id uuid not null references public.users(id) on delete cascade,
  body text not null,
  status text not null default 'pending' check (status in ('pending','processing','completed','failed')),
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.agent_actions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  message_sid text references public.whatsapp_inbox(id) on delete set null,
  activity_id uuid not null,
  activity_type text not null check (activity_type in ('event','task')),
  title text not null,
  category text not null check (category in ('academics','career','social','health','admin')),
  status text not null check (status in ('proposed','needs_clarification','executing','completed','failed')),
  external_id text,
  created_at timestamptz not null default now(),
  unique (message_sid, activity_id)
);

create table public.whatsapp_outbox (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  dedupe_key text not null unique,
  kind text not null check (kind in ('reply','morning','evening')),
  body text not null,
  status text not null default 'pending' check (status in ('pending','sending','accepted','failed','unknown','blocked')),
  twilio_sid text,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index on public.time_entries (user_id, start_time);
create index on public.tasks (user_id, due_date);
create index on public.agent_actions (user_id, created_at desc);
create index on public.whatsapp_inbox (created_at) where status = 'pending';
create index on public.whatsapp_outbox (created_at) where status = 'pending';

create function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
create trigger touch_time_entries before update on public.time_entries for each row execute function public.touch_updated_at();
create trigger touch_tasks before update on public.tasks for each row execute function public.touch_updated_at();
create trigger touch_inbox before update on public.whatsapp_inbox for each row execute function public.touch_updated_at();
create trigger touch_outbox before update on public.whatsapp_outbox for each row execute function public.touch_updated_at();

-- Linking a phone requires an authenticated, independently verified admin setup step.
-- Never create/link users based solely on a phone number sent to the webhook.
create function public.ingest_whatsapp(p_sid text, p_from text, p_body text, p_opt_out boolean default false)
returns boolean language plpgsql security invoker set search_path = public as $$
declare uid uuid; inserted integer;
begin
  if p_opt_out then
    update public.users set whatsapp_opt_in=false, morning_enabled=false, evening_enabled=false
      where whatsapp_number=p_from;
    return true;
  end if;
  select id into uid from public.users where whatsapp_number=p_from and whatsapp_opt_in;
  if uid is null then return false; end if;
  insert into public.whatsapp_inbox(id,user_id,body) values (p_sid,uid,p_body)
    on conflict (id) do nothing;
  get diagnostics inserted = row_count;
  if inserted > 0 then
    update public.users set last_inbound_at=now() where id=uid;
  end if;
  return true;
end $$;

-- At-most-once claims: crashes are visible for operator reconciliation, never
-- blindly replayed against Google/Twilio. Multiple workers safely skip locked rows.
create function public.claim_whatsapp_inbox()
returns setof public.whatsapp_inbox language sql security invoker set search_path = public as $$
  update public.whatsapp_inbox set status='processing'
  where id=(select id from public.whatsapp_inbox where status='pending'
            order by created_at for update skip locked limit 1) returning *;
$$;

create function public.claim_whatsapp_outbox()
returns setof public.whatsapp_outbox language sql security invoker set search_path = public as $$
  update public.whatsapp_outbox set status='sending'
  where id=(select id from public.whatsapp_outbox where status='pending'
            order by created_at for update skip locked limit 1) returning *;
$$;

create function public.enqueue_whatsapp(p_user_id uuid, p_key text, p_kind text, p_body text)
returns void language sql security invoker set search_path = public as $$
  insert into public.whatsapp_outbox(user_id,dedupe_key,kind,body)
  values (p_user_id,p_key,p_kind,p_body) on conflict (dedupe_key) do nothing;
$$;

-- Commit outcomes, activity feed, inbox completion and reply atomically.
create function public.finish_whatsapp(p_sid text, p_actions jsonb, p_reply text)
returns void language plpgsql security invoker set search_path = public as $$
declare uid uuid; a jsonb;
begin
  select user_id into uid from public.whatsapp_inbox where id=p_sid and status='processing' for update;
  if uid is null then raise exception 'Message is not processing'; end if;
  for a in select * from jsonb_array_elements(p_actions) loop
    if a->>'type' = 'event' then
      insert into public.time_entries(id,user_id,title,category,start_time,end_time,status,external_id)
      values ((a->>'id')::uuid,uid,a->>'title',a->>'category',
              (a->>'start_time')::timestamptz,(a->>'end_time')::timestamptz,a->>'status',a->>'external_id');
    elsif a->>'type' = 'task' then
      insert into public.tasks(id,user_id,title,category,due_date,status,external_id)
      values ((a->>'id')::uuid,uid,a->>'title',a->>'category',(a->>'due_date')::date,a->>'status',a->>'external_id');
    else raise exception 'Invalid activity type';
    end if;
    insert into public.agent_actions(user_id,message_sid,activity_id,activity_type,title,category,status,external_id)
    values (uid,p_sid,(a->>'id')::uuid,a->>'type',a->>'title',a->>'category',a->>'status',a->>'external_id');
  end loop;
  perform public.enqueue_whatsapp(uid,'reply:'||p_sid,'reply',p_reply);
  update public.whatsapp_inbox set status='completed' where id=p_sid;
end $$;

create function public.fail_whatsapp(p_sid text)
returns void language plpgsql security invoker set search_path = public as $$
declare uid uuid;
begin
  -- A timed-out finish request may already have committed. Never overwrite that
  -- successful transaction or enqueue a contradictory error confirmation.
  update public.whatsapp_inbox set status='failed',error_code='processing_failed'
    where id=p_sid and status='processing' returning user_id into uid;
  if uid is not null then
    perform public.enqueue_whatsapp(uid,'error:'||p_sid,'reply',
      'I couldn''t confirm the result of your request. Please check your calendar and dashboard before trying again.');
  end if;
end $$;

alter table public.users enable row level security;
alter table public.time_entries enable row level security;
alter table public.tasks enable row level security;
alter table public.agent_actions enable row level security;
alter table public.whatsapp_inbox enable row level security;
alter table public.whatsapp_outbox enable row level security;

create policy own_user on public.users for select to authenticated using (id=(select auth.uid()));
create policy own_events on public.time_entries for select to authenticated using (user_id=(select auth.uid()));
create policy own_tasks on public.tasks for select to authenticated using (user_id=(select auth.uid()));
create policy own_actions on public.agent_actions for select to authenticated using (user_id=(select auth.uid()));

revoke all on public.users,public.time_entries,public.tasks,public.agent_actions,
  public.whatsapp_inbox,public.whatsapp_outbox from anon,authenticated;
grant select on public.users,public.time_entries,public.tasks,public.agent_actions to authenticated;
grant all on public.users,public.time_entries,public.tasks,public.agent_actions,
  public.whatsapp_inbox,public.whatsapp_outbox to service_role;

revoke execute on function public.touch_updated_at(),
  public.ingest_whatsapp(text,text,text,boolean), public.claim_whatsapp_inbox(), public.claim_whatsapp_outbox(),
  public.enqueue_whatsapp(uuid,text,text,text), public.finish_whatsapp(text,jsonb,text), public.fail_whatsapp(text) from public,anon,authenticated;
grant execute on function public.ingest_whatsapp(text,text,text,boolean), public.claim_whatsapp_inbox(), public.claim_whatsapp_outbox(),
  public.enqueue_whatsapp(uuid,text,text,text), public.finish_whatsapp(text,jsonb,text), public.fail_whatsapp(text) to service_role;

-- Realtime only publishes dashboard data; queue contents remain backend-only.
do $$ declare t text; begin
  if exists (select 1 from pg_publication where pubname='supabase_realtime') then
    foreach t in array array['time_entries','tasks','agent_actions'] loop
      if not exists (select 1 from pg_publication_tables where pubname='supabase_realtime' and schemaname='public' and tablename=t) then
        execute format('alter publication supabase_realtime add table public.%I',t);
      end if;
    end loop;
  end if;
end $$;
commit;
