# Eva: WhatsApp and database

Work on `whatsapp-database`. This component receives signed Twilio messages, hands
them to Jia's AI service, stores validated Google execution results, serves dashboard
data, and sends replies, morning briefings and evening recaps. Gemini parsing belongs
to Jia; Google OAuth, availability checks and Google writes belong to Ojal; the
dashboard UI belongs to Mahika.

## Implementation checklist

- [x] `backend/integrations/twilio/webhook.py`: signature/account/destination checks,
  durable ingestion, immediate empty TwiML, STOP opt-out, duplicate MessageSid handling.
- [x] `backend/integrations/twilio/ai_bridge.py`: replaceable parse/execute adapter,
  validation, clarification path, confirmations based on execution outcomes.
- [x] `backend/integrations/twilio/sender.py`: opt-in checks, 24-hour session window,
  template-based scheduled notifications outside the window.
- [x] `backend/db/migrations/001_whatsapp_database.sql`: users, time entries, tasks,
  actions, inbox/outbox, indexes, generated durations, RLS and Realtime publication.
- [x] `backend/db/router.py`: authenticated activities, analytics and action history.
- [x] `backend/jobs/`: durable queue processing, timezone-aware daily notifications.
- [x] Tests for signatures, validation, access control, overlaps, DST, delivery
  uncertainty, plus real SQL migration and RLS checks in an isolated local database.
- [ ] Create/configure Twilio and Supabase projects with your own credentials.
- [ ] Apply SQL and link a verified phone to a Supabase Auth user.
- [ ] Coordinate the **proposed** AI contract below with Jia and Ojal.
- [ ] Test actual WhatsApp → Gemini → Google → Supabase → dashboard → reply.

The checked items are implementation work, not evidence of successful live integration.
No mock Gemini response or fake Google success is used in the running service.

## Local setup

From the repository root:

```sh
git branch --show-current
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-whatsapp-dev.txt
cp backend/.env.example backend/.env
```

Fill `backend/.env` locally. Never paste secrets into source files, the browser or a
pull request. `SUPABASE_SERVICE_ROLE_KEY` is a backend-only secret. `AI_SERVICE_TOKEN`
must match the internal bearer token configured by Jia when `AI_BASE_URL` is enabled.
Environment variables override the env file. Start both processes in separate terminals:

```sh
source .venv/bin/activate
uvicorn backend.integrations.twilio.app:app --host 127.0.0.1 --port 8000
```

```sh
source .venv/bin/activate
python -m backend.jobs.worker
```

```sh
curl http://127.0.0.1:8000/health
ngrok http 8000
```

Set `TWILIO_WEBHOOK_URL` to the **exact public HTTPS URL** plus `/api/whatsapp`.
Restart the API process after changing it. In Twilio Console → Messaging → Try it
out → Send a WhatsApp message, join the Sandbox from your phone using its displayed
join code. Configure “When a message comes in” to that URL using **POST**. Set the
Sandbox sender, Account SID and Auth Token from your account in the env file.
Don't disable signature checks for local tests: the automated tests sign test forms.

The Twilio Console, Sandbox membership and WhatsApp template approvals are account
setup steps; the repository cannot provision them without account access. Sandbox
users must join first, and its available templates are restricted. Check the account's
Sandbox rules before enabling automatic notifications outside an active session.

## Supabase setup

1. Create a Supabase project and run `backend/db/migrations/001_whatsapp_database.sql`
   followed by `002_reject_blank_activity_fields.sql` in its SQL editor. If 001 was
   already applied, run only 002. Each is a transaction; 001 intentionally does not overwrite
   existing tables. Back up and coordinate schema conflicts rather than rerunning it.
2. Create/sign in a dashboard user through Supabase Auth. Copy the user's UUID.
3. Verify that the user owns the WhatsApp phone and explicitly wants WhatsApp
   messages. Link it in the SQL editor (replace both example values):

```sql
insert into public.users (id, whatsapp_number, timezone, whatsapp_opt_in)
values ('YOUR_AUTH_USER_UUID', 'whatsapp:+15551234567', 'America/New_York', true);
```

Use a valid IANA timezone. Users cannot change the verified number, opt-in or timezone
through the public Data API. For this prototype, an admin updates verified preferences
in the SQL editor. Do not link an arbitrary Auth user based only on an incoming phone.
Unknown or opted-out senders receive an empty acknowledgement and no AI processing.
STOP and common exact opt-out keywords disable messaging and both daily jobs. Restoring
opt-in requires another verified admin update; START does not silently re-enable it.

Enable scheduled messages only after the user agrees:

```sql
update public.users
set morning_enabled=true, evening_enabled=true,
    morning_time='08:00', evening_time='21:00'
where id='YOUR_AUTH_USER_UUID';
```

The scheduler runs on the user's local clock, deduplicates by user/date/kind and
doesn't backfill missed times after downtime. A spring-forward nonexistent clock
minute is skipped; a repeated fall-back minute generates one message. Keep the worker
running for notifications. No actual time tracking is inferred from scheduled events.

## Proposed API contract: confirm with Jia and Ojal

These schemas are isolated in Eva's adapter/models; they do not overwrite
`backend/main.py` or the teammates' shared schemas. Adapt this boundary once the team
agrees. The app here does **not** implement `/api/parse` or `/api/execute`.

Both AI requests use `Authorization: Bearer AI_SERVICE_TOKEN` and
`Idempotency-Key: <Twilio MessageSid>`. The internal service must authenticate that
credential and enforce tenant ownership. Do not expose its token in the frontend.

`POST /api/parse`:

```json
{
  "user_id": "SUPABASE_AUTH_UUID",
  "message_id": "SM0123456789abcdef0123456789abcdef",
  "timezone": "America/New_York",
  "reference_time": "2026-10-17T20:00:00+00:00",
  "message": "Schedule Java study tomorrow from 7 to 9 PM"
}
```

Response (all IDs must be stable UUIDs; enum values match the master prompt):

```json
{
  "actions": [{
    "id": "33333333-3333-3333-3333-333333333333",
    "type": "event",
    "title": "Study Java",
    "category": "academics",
    "start_time": "2026-10-18T19:00:00-04:00",
    "end_time": "2026-10-18T21:00:00-04:00",
    "due_date": null,
    "status": "proposed",
    "external_id": null,
    "source": "whatsapp"
  }],
  "reply": ""
}
```

Use `type: task`, null times and optional `due_date: YYYY-MM-DD` for Google Tasks.
An incomplete event may have both times null with `needs_clarification`; never invent
a duration/date. When any action needs clarification, **the entire plan waits** and
nothing is executed. The next incoming text goes to the parser with the same user ID;
Jia must provide conversation context or ask the user to restate the complete request.
Only explicit create intent is supported by this adapter. Jia must not interpret a
question, update or delete request as a create authorization.

`POST /api/execute` receives the same context fields, `actions` and
`authorization_source: inbound_whatsapp_create_request`. The incoming user's explicit
create instruction authorizes only those creations. Ojal/Jia must revalidate the plan,
ownership, OAuth authorization, conflicts and any required confirmation; the adapter
does not bypass those checks. Return the same `actions/reply` shape, with the same IDs
and approved activity fields, and terminal statuses `completed`, `failed` or
`needs_clarification`. `completed` must include a real Google `external_id`.

The execution service must use message/action IDs for durable idempotency and return
previous outcomes on replay. Its response can describe partial success, with one
outcome for every action. Eva atomically persists all outcomes, action feed records
and the WhatsApp reply. **Only Eva persists these results on this path**; coordinate
other sources separately to avoid duplicate Google IDs. `status=completed` means
successful synchronization; `tasks.completed_at` separately records actual completion.

## Dashboard handoff to Mahika

All reads require a real Supabase **user access token** in `Authorization: Bearer ...`.
Identity comes from `/auth/v1/user`; a query `user_id` never selects another account.
Use a same-origin Next.js server proxy to this service in development/deployment, or
coordinate an explicit CORS allowlist in the integrated backend. No wildcard CORS is
enabled here. Poll every 10–15 seconds with refresh-on-focus for the simplest demo.

| Route | Response |
| --- | --- |
| `GET /health` | Liveness only: `status`, `service`; not a credential/readiness check |
| `GET /api/activities` | `{activities: [...]}`; time entries have `type=event`, tasks `type=task` |
| `GET /api/analytics/today` | `date`, `timezone`, `metric`, `overlap_policy`, `planned_minutes`, `categories` |
| `GET /api/analytics/week` | `{days: [seven daily analytics objects]}`, Monday through Sunday |
| `GET /api/agent-actions` | `{actions: [...]}`, latest 100, newest first |

Categories contain `category`, `minutes`, `percentage`. Planned analytics count only
successfully synced events, clipped to the user's day. Overlapping categories split
the overlapping minutes equally; same-category overlaps count once. Task-only due
dates add zero planned minutes. These values describe planned time, not actual time.

Alternatively, subscribe to `time_entries`, `tasks`, `agent_actions` through Supabase
Realtime with the signed-in user's session and `user_id=eq.<auth.uid()>`. The migration
publishes these tables when the standard `supabase_realtime` publication exists.
Their SELECT policies enforce ownership. Use the public/publishable Supabase key in
the browser, **never the service-role key**. Inbox and outbox have no client access.

## Integration into Jia's FastAPI app

Eva's standalone service works on its own while the AI app is developed. Jia can
instead include `whatsapp_router` and `dashboard_router` from
`backend/integrations/twilio/app.py` in the main app and initialize the same
`app.state` dependencies shown in `create_app`: settings, client and repo (the two
routers share these three dependencies). Copy the HTTP-error handler as well. Avoid
duplicating `/health`. Merge requirements deliberately with the team's backend
requirements. Run `backend.jobs.worker` separately from uvicorn/Gunicorn processes.

## Testing and demo

See [Eva's test report](eva-test-report.md) for the independent component scenarios,
results, fixes and remaining live integration checks.

```sh
source .venv/bin/activate
python -m pytest -q
```

The SQL test starts a **disposable** local PostgreSQL cluster with a private Unix
socket, creates Supabase-like roles/auth helpers, applies the real migration and
checks dedupe, transaction rollback, RLS and grants. It never connects to your existing
databases. If PostgreSQL binaries are missing, that test skips; point
`TEST_POSTGRES_BIN` at your PostgreSQL `bin` directory to enable it. Unit tests use
mock HTTP transports, not live provider calls. Real Supabase Auth/Realtime and Twilio
Sandbox behavior still require a live smoke test.

For the live demo:

1. Link the user, configure credentials and start API, worker and ngrok.
2. Confirm Jia's parse/execute contract and Ojal's OAuth connection for that same user.
3. Send a complete dated/timed create request from the joined WhatsApp phone.
4. Check the real Google event, a `completed` inbox record, the event's external ID,
   action feed row and an `accepted` outbox record.
5. Sign in as that user and confirm the dashboard refresh and WhatsApp confirmation.
6. Send an ambiguous request: expect clarification, with no Google write.
7. Test a briefing within an active window. Outside the window, configure an approved
   `TWILIO_MORNING_CONTENT_SID` / `TWILIO_EVENING_CONTENT_SID`, each accepting `{{1}}`
   as summary text, and ensure their approved wording fits that use. Otherwise the
   outbox records `blocked/template_required` and no free-form message is sent.

## Failure handling and operations

Queues are durable, and claims use PostgreSQL row locks so workers cannot claim the
same pending row. Claims are deliberately **not automatically retried** after a
crash or ambiguous provider result: Google writes and Twilio sends cannot be made
exactly-once by this service alone. A process death leaves `processing` / `sending`
for reconciliation; errors are stored without raw messages, secrets or provider dumps
in logs. A Twilio accepted SID is acceptance, not a delivery receipt.

Inspect stuck rows after a worker restart:

```sql
select id,status,error_code,updated_at from public.whatsapp_inbox
where status in ('processing','failed') order by updated_at;
select id,status,twilio_sid,error_code,updated_at from public.whatsapp_outbox
where status in ('sending','unknown','failed','blocked') order by updated_at;
```

Before requeueing, check Google/Twilio and the AI service's idempotency record. Reconcile
Google outcomes through `finish_whatsapp` only while the inbox is `processing`; don't
rerun Google creations to repair a persistence failure. A failed inbox may require a
verified admin to restore `processing` before reconciliation. A `sending` or `unknown`
outbox may already have been sent; consult Twilio logs first. Blocked notifications
are not automatically backfilled. This prototype uses admin reconciliation rather
than claiming automatic recovery of ambiguous writes.

## Commit and PR

The pre-existing frontend deletions are outside Eva's work. Stage only these files:

```sh
git add .gitignore backend docs/eva-integration.md pytest.ini
git diff --cached --stat
git commit -m "Add signed WhatsApp integration, Supabase storage and daily briefings"
git push -u origin whatsapp-database
gh pr create --base main --head whatsapp-database --title "Add WhatsApp and database integration" --body-file docs/eva-pr.md
```

Do not use `git add -A` while unrelated frontend changes are present.

Reference documentation: [Twilio webhook signatures](https://www.twilio.com/docs/usage/webhooks/webhooks-security),
[WhatsApp sessions and templates](https://help.twilio.com/articles/360007721954),
[Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Supabase Realtime](https://supabase.com/docs/guides/realtime/postgres-changes).
