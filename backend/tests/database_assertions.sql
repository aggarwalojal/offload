-- Executed only in the disposable PostgreSQL cluster created by test_database.py.
begin;
insert into auth.users(id) values ('11111111-1111-1111-1111-111111111111'),('22222222-2222-2222-2222-222222222222');
insert into public.users(id,whatsapp_number,whatsapp_opt_in) values
('11111111-1111-1111-1111-111111111111','whatsapp:+15551111111',true),
('22222222-2222-2222-2222-222222222222','whatsapp:+15552222222',true);

set local role service_role;
select public.ingest_whatsapp('SMtest','whatsapp:+15551111111','Study');
select public.ingest_whatsapp('SMtest','whatsapp:+15551111111','Duplicate');
select public.claim_whatsapp_inbox();
select public.finish_whatsapp('SMtest', '[{"id":"33333333-3333-3333-3333-333333333333","type":"event","title":"Study","category":"academics","start_time":"2026-10-17T10:00:00-04:00","end_time":"2026-10-17T12:00:00-04:00","status":"completed","external_id":"google-event"}]', 'Added Study');
select public.enqueue_whatsapp('11111111-1111-1111-1111-111111111111','reply:SMtest','reply','Duplicate');
select public.fail_whatsapp('SMtest'); -- Late failure must not overwrite committed success.
do $$ begin
  assert (select count(*) from public.whatsapp_inbox)=1, 'Inbound dedupe failed';
  assert (select body from public.whatsapp_inbox where id='SMtest')='Study', 'Duplicate overwrote message';
  assert (select count(*) from public.whatsapp_outbox)=1, 'Outbound dedupe failed';
  assert (select count(*) from public.agent_actions)=1, 'Missing feed action';
  assert (select duration_minutes from public.time_entries limit 1)=120, 'Wrong duration';
  assert (select status from public.whatsapp_inbox where id='SMtest')='completed', 'Inbox not completed';
  assert not exists (select * from public.claim_whatsapp_inbox()), 'Reclaimed completed message';
end $$;
select public.claim_whatsapp_outbox();
do $$ begin
  assert not exists (select * from public.claim_whatsapp_outbox()), 'Reclaimed sending message';
end $$;

-- Verify transaction rollback if any outcome violates a constraint.
select public.ingest_whatsapp('SMbad','whatsapp:+15551111111','Invalid result');
select public.claim_whatsapp_inbox();
do $$ begin
  begin
    perform public.finish_whatsapp('SMbad', '[{"id":"44444444-4444-4444-4444-444444444444","type":"event","title":"Bad","category":"academics","status":"completed","external_id":"bad-id"}]', 'Incorrect confirmation');
    raise exception 'Invalid event was accepted';
  exception when check_violation then null;
  end;
  assert (select status from public.whatsapp_inbox where id='SMbad')='processing', 'Partial transaction committed';
  assert not exists (select 1 from public.whatsapp_outbox where dedupe_key='reply:SMbad'), 'Invalid confirmation queued';
end $$;

select public.fail_whatsapp('SMbad');
select public.fail_whatsapp('SMbad');
do $$ begin
  assert (select status from public.whatsapp_inbox where id='SMbad')='failed', 'Failure state missing';
  assert (select count(*) from public.whatsapp_outbox where dedupe_key='error:SMbad')=1, 'Duplicate error confirmation';
end $$;

insert into public.tasks(id,user_id,title,category,due_date,status,external_id)
values ('55555555-5555-5555-5555-555555555555','11111111-1111-1111-1111-111111111111',
        'Apply for internship','career','2026-10-18','completed','google-task');
do $$ begin
  begin
    insert into public.tasks(id,user_id,title,category,status,external_id)
    values (gen_random_uuid(),'11111111-1111-1111-1111-111111111111','   ','career','completed','valid-id');
    raise exception 'Blank title accepted';
  exception when check_violation then null; end;
  begin
    insert into public.tasks(id,user_id,title,category,status,external_id)
    values (gen_random_uuid(),'11111111-1111-1111-1111-111111111111','Task','career','completed','   ');
    raise exception 'Blank external ID accepted';
  exception when check_violation then null; end;
end $$;

select public.ingest_whatsapp('SMstop','whatsapp:+15551111111','STOP',true);
do $$ begin
  assert not (select whatsapp_opt_in from public.users where id='11111111-1111-1111-1111-111111111111'), 'Opt out failed';
  assert not public.ingest_whatsapp('SMignored','whatsapp:+15551111111','Ignored'), 'Opted out message accepted';
  assert not public.ingest_whatsapp('SMunknown','whatsapp:+15559999999','Unknown'), 'Unknown user accepted';
end $$;
reset role;

-- User 2 must not see user 1's events or execute privileged queue functions.
set local role authenticated;
select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',true);
do $$ begin
  assert (select count(*) from public.users)=1, 'Profile isolation failed';
  assert (select count(*) from public.time_entries)=0, 'Cross-user event disclosure';
  assert (select count(*) from public.tasks)=0, 'Cross-user task disclosure';
  assert (select count(*) from public.agent_actions)=0, 'Cross-user feed disclosure';
  assert not has_table_privilege(current_user,'public.whatsapp_inbox','select'), 'Inbox is exposed';
  assert not has_function_privilege(current_user,'public.claim_whatsapp_inbox()','execute'), 'Queue function is exposed';
  assert not has_table_privilege(current_user,'public.users','update'), 'User can change verified phone';
end $$;
select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',true);
do $$ begin
  assert (select count(*) from public.time_entries)=1, 'Own event is inaccessible';
  assert (select count(*) from public.tasks)=1, 'Own task is inaccessible';
end $$;
reset role;
set local role anon;
do $$ begin
  assert not has_table_privilege(current_user,'public.time_entries','select'), 'Anonymous reads allowed';
  assert not has_function_privilege(current_user,'public.ingest_whatsapp(text,text,text,boolean)','execute'), 'Anonymous ingestion allowed';
end $$;
rollback;
