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
