-- Additive: apply after 001 and 002. Only the backend may issue/consume links.
begin;
create table public.whatsapp_link_codes (
  user_id uuid primary key references auth.users(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  timezone text not null,
  expires_at timestamptz not null
);
alter table public.whatsapp_link_codes enable row level security;
revoke all on public.whatsapp_link_codes from public, anon, authenticated;
grant select, insert, update, delete on public.whatsapp_link_codes to service_role;

create function public.issue_whatsapp_link(p_user_id uuid, p_hash text, p_timezone text)
returns void language sql security invoker set search_path = public as $$
  insert into public.whatsapp_link_codes(user_id,token_hash,timezone,expires_at)
  values (p_user_id,p_hash,p_timezone,now()+interval '15 minutes')
  on conflict (user_id) do update set token_hash=excluded.token_hash,
    timezone=excluded.timezone,expires_at=excluded.expires_at;
$$;

create function public.consume_whatsapp_link(p_hash text, p_from text)
returns text language plpgsql security invoker set search_path = public as $$
declare link public.whatsapp_link_codes; owner uuid; phone text;
begin
  if p_from !~ '^whatsapp:\+[1-9][0-9]{6,14}$' then return 'invalid'; end if;
  select * into link from public.whatsapp_link_codes
    where token_hash=p_hash and expires_at>now() for update;
  if not found then return 'invalid'; end if;
  -- Serialize claims of the same phone across different authenticated users.
  perform pg_advisory_xact_lock(hashtextextended(p_from,0));
  select id into owner from public.users where whatsapp_number=p_from;
  select whatsapp_number into phone from public.users where id=link.user_id;
  if (owner is not null and owner<>link.user_id) or (phone is not null and phone<>p_from) then
    return 'conflict';
  end if;
  insert into public.users(id,whatsapp_number,timezone,whatsapp_opt_in,last_inbound_at)
    values(link.user_id,p_from,link.timezone,true,now())
    on conflict (id) do update set whatsapp_opt_in=true,last_inbound_at=now(),timezone=excluded.timezone;
  delete from public.whatsapp_link_codes where user_id=link.user_id;
  return 'linked';
end $$;

revoke all on function public.issue_whatsapp_link(uuid,text,text),
  public.consume_whatsapp_link(text,text) from public, anon, authenticated;
grant execute on function public.issue_whatsapp_link(uuid,text,text),
  public.consume_whatsapp_link(text,text) to service_role;
commit;
