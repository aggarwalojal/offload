# WhatsApp-first onboarding

1. A Sandbox participant texts the configured TimeSlice number.
2. The signed webhook replies to an unlinked sender with the dashboard link.
   It does not create an account or schedule the original text.
3. The user opens the dashboard Settings and connects Google Calendar using
   the existing Supabase Google OAuth flow.
4. In Settings they select **Connect WhatsApp**, then **Open WhatsApp and send
   verification**. Sending that message proves control of their WhatsApp number
   and links it to the verified dashboard account. They approve messaging by
   explicitly sending that verification message.
5. The dashboard shows Connected. The user returns to WhatsApp and sends their
   task again. AI/Google execution uses the now-linked Supabase user UUID.
   For the live demo, keep the WhatsApp webhook server, worker, and ngrok running.

## Deployment

- Apply `backend/db/migrations/003_whatsapp_onboarding.sql` after the existing
  Eva migrations, in the shared Supabase SQL Editor.
- Set `DASHBOARD_URL=https://YOUR_ACTUAL_DASHBOARD` in the WhatsApp server AND
  worker environment. It must be an HTTPS origin with no path/query/fragment.
- Set `WHATSAPP_BACKEND_URL=https://YOUR_WHATSAPP_SERVER` in the frontend server
  environment. This is the webhook service base address, without `/api/whatsapp`.
  A localhost HTTP address is supported only for local development.
- Restart the webhook/worker and redeploy the frontend from these changes.
- Existing Google OAuth, Supabase, AI, and Twilio configuration is still needed.
  For Sandbox demos each phone must first join using the Sandbox QR/join message.

## Identity and retries

The dashboard backend forwards only the verified Supabase app access token to
the WhatsApp service. It never receives a Supabase service key. The WhatsApp
service validates that token against Supabase and requires a verified email.
It generates an unpredictable 192-bit code valid for 15 minutes. Only its SHA256
hash is stored in a backend-only RLS table. A new code invalidates the previous
one for that user. Only a signed Twilio message can consume a code.

Consumption is atomic and single-use. Existing phone/account associations cannot
be reassigned by this flow; a conflicting pre-existing test profile requires
operator review. Existing tasks and events are never moved or deleted. STOP
keeps its opt-out behavior. Sending a fresh verification message can opt back in.
Do not log challenge URLs or LINK message bodies in access/application logs.

The first welcome and linking confirmations use TwiML replies; Twilio controls
their delivery. They do not run the AI or enqueue scheduling. Retried webhook
requests may repeat a welcome; replaying a consumed code cannot relink an account.

## Demo check

Use a fresh test account/phone: join Sandbox, text hello, follow the dashboard
link, connect Google, verify WhatsApp, then create an event at an available time.
Confirm it appears in that account's Calendar. Repeat with another account to
verify isolation. Test an expired code, a reused code, STOP, and a phone already
linked to another account. Automated tests use mocked providers and disposable
PostgreSQL; they do not establish that production OAuth/deployment is configured.

## Live Offload deployment

Frontend: `https://timeslice-dashboard.vercel.app`. Google API:
`https://timeslice-google-api.vercel.app`. The frontend uses `WHATSAPP_BACKEND_URL`
for account verification; update it and redeploy whenever the ngrok origin changes.
The latest frontend refreshes Calendar events and open Google Tasks every 15 seconds
while visible, on focus, and on reconnect. It preserves charts during background
refreshes. Tasks have a separate list and do not count as planned Calendar hours.

### Required worker handoff

The WhatsApp web service **and** `python -m backend.jobs.worker` must run with
the same shared Supabase project and current code. Configure:

```dotenv
DASHBOARD_URL=https://timeslice-dashboard.vercel.app
AI_BASE_URL=https://YOUR_AI_SERVICE
GOOGLE_EXECUTION_URL=https://timeslice-google-api.vercel.app
AI_SERVICE_TOKEN=the-same-private-token-on-worker-and-google-api
```

Set `AI_SERVICE_TOKEN` as a production secret on the Google API Vercel project.
The worker also sends it to the parser service. The AI service needs its Gemini
key; the Google API already holds Google OAuth/storage credentials. If
`GOOGLE_EXECUTION_URL` is empty, execution uses `AI_BASE_URL` as before and that
AI service must hold the Google/storage configuration. Never share tokens in chat.

Mixed event/task messages are supported. Calendar validation/conflicts run first,
Tasks are prevalidated, and original message positions preserve retry identity.
Partial provider failures return only confirmed outcomes; operations are not a
transaction across Google products. Uncertain Tasks writes require reconciliation.

### Acceptance test (requires the running services)

1. Text hello from a Sandbox participant phone; receive the public dashboard link.
2. Connect Calendar and Tasks, then use Connect WhatsApp and SEND the generated
   verification message from that same phone. Verify the Connected status.
3. Send an event with explicit dates/times plus a task with a due date. Verify
   the agent replies with actual outcomes, not just a welcome or demo message.
4. Verify the event in Google Calendar and the task in Google Tasks. Leave the
   dashboard open; both should appear within 15 seconds after the write finishes.
5. Reload, switch tabs, and retry the same message through the queue: verify data
   persists and retries do not duplicate Google writes. Repeat with a second
   account to confirm each sees only their own Google data.

The first unlinked message intentionally is not scheduled; resend plans after
verification. A healthy ngrok `/health` proves the web server only, not the worker,
Gemini configuration, shared execution token, or the Twilio webhook setting.

## Fast ngrok demo command

On the laptop running the WhatsApp service, install both sets of dependencies:

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-whatsapp.txt
python scripts/run_demo.py
```

This validates `backend/.env`, checks that `AI_SERVICE_TOKEN` matches the hosted
Google API using an empty invalid plan (no writes), starts the AI parser on port
8002 if needed, and starts the WhatsApp worker. Keep that terminal, the existing
WhatsApp web server, and ngrok open. Ctrl+C stops only the processes this command
started. It does not host services permanently or configure the Twilio console.

The WhatsApp web server itself must have
`DASHBOARD_URL=https://timeslice-dashboard.vercel.app` in `backend/.env` and be
restarted after changing it. The runner configures its worker subprocess to use
that same dashboard and the hosted Google execution URL. `GEMINI_API_KEY`,
Twilio credentials, shared Supabase credentials, and the exact public Twilio
webhook URL must already be present privately in `backend/.env`.

Run `python scripts/run_demo.py --check` for a configuration-only check. Passing
that check does not prove Gemini or Twilio message delivery works; send one real
WhatsApp message after account linking to verify the complete demo.
