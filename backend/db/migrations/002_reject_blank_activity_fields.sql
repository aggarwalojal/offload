-- Upgrade installations that applied 001 before the boundary-test fixes.
-- Safe on fresh installations too. Existing invalid rows cause a rollback so
-- they can be reviewed; no application data is silently rewritten or deleted.
begin;
alter table public.time_entries drop constraint if exists time_entries_title_check;
alter table public.time_entries add constraint time_entries_title_check
  check (length(title) between 1 and 300 and length(btrim(title)) > 0);
alter table public.time_entries drop constraint if exists time_entries_external_id_check;
alter table public.time_entries add constraint time_entries_external_id_check
  check (external_id is null or length(btrim(external_id)) > 0);
alter table public.tasks drop constraint if exists tasks_title_check;
alter table public.tasks add constraint tasks_title_check
  check (length(title) between 1 and 300 and length(btrim(title)) > 0);
alter table public.tasks drop constraint if exists tasks_external_id_check;
alter table public.tasks add constraint tasks_external_id_check
  check (external_id is null or length(btrim(external_id)) > 0);
commit;
