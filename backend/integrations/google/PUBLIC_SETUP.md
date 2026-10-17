# Multi-user Google Calendar setup

## What is implemented

The Next.js dashboard now signs users in through Supabase Google OAuth (PKCE),
exchanges the callback code on the server, saves Google credentials through the
FastAPI API, and displays each user's own timed Calendar events and analytics.
Supabase app sessions use HttpOnly cookies. Google provider tokens are never
stored in those cookies or returned to browser JavaScript. The API verifies the
Supabase JWT with Supabase, validates the Google account and OAuth client, and
stores Google credentials encrypted with Fernet under the authenticated user ID.

This is **not live yet**. The Supabase project, provider configuration, SQL table,
backend deployment, and Vercel environment settings must be supplied below.
Until then, the website stays in clearly labeled demo mode. The existing local
`demo_app.py` is a separate development test and should not be publicly deployed.

## Eva: configure the shared Supabase project

1. In SQL Editor, run `migrations/001_google_connections.sql` from this directory.
   This adds only `timeslice_google_connections`, enables RLS, and revokes all
   browser-user access. Existing app tables are not changed.
2. In Authentication → Providers → Google, enable Google and enter the project's
   Google OAuth client ID and secret. Use the SAME client configured on the
   Calendar backend. Never send the secret to the frontend developer's browser.
3. Copy Supabase's Google callback URL, usually:
   `https://YOUR_PROJECT.supabase.co/auth/v1/callback`.
4. In the TimeSlice Google Cloud OAuth web client, add that exact URL under
   **Authorized redirect URIs**. Keep the local demo URI if it is still needed.
5. In Supabase Authentication → URL Configuration, set Site URL to
   `https://timeslice-dashboard.vercel.app` and allow this exact redirect:
   `https://timeslice-dashboard.vercel.app/api/auth/callback`.
   For development also allow `http://localhost:3001/api/auth/callback`.
6. Share the Supabase project URL and publishable key for frontend configuration.
   Configure the server-only Supabase secret key directly in the backend host's
   environment (the legacy service-role JWT key also works). Never use a
   `NEXT_PUBLIC_` variable for the secret key.

## Ojal: deploy the API

Deploy the repository as a Python/Docker web service, for example on Render or
Railway. Use `backend/integrations/google/Dockerfile` with repository-root build
context. The root `.dockerignore` excludes local secrets and credential downloads.
Alternatively install `backend/integrations/google/requirements.txt` and run:

```sh
uvicorn backend.integrations.google.public_app:create_public_app --factory --host 0.0.0.0 --port 8000 --no-access-log --no-proxy-headers
```

The platform should expose HTTPS. Use one host instance for the hackathon to
avoid concurrent refresh-token updates across replicas. No persistent local disk
is needed; encrypted token records live in the shared database.

Set these backend-only environment variables:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=server-only-secret-key
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback
GOOGLE_ENABLE_TASKS=false
GOOGLE_TOKEN_ENCRYPTION_KEY=your-fernet-key
```

`GOOGLE_REDIRECT_URI` is retained for the separate OAuth helper and local demo;
the public sign-in is handled by Supabase's callback, not that helper. The public
backend uses the client ID/secret only to verify and refresh the same Google grant.

Generate a Fernet encryption key locally, once:

```sh
/tmp/timeslice-google-venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Store it in the backend host's secret environment settings. Keep it stable across
restarts/deploys and back it up securely; changing it makes existing connections
unreadable until users reconnect. It does not belong in frontend configuration.
Check `GET https://YOUR_BACKEND/health` after deployment.

## Frontend / Vercel configuration

The integrated dashboard changes are currently in the `google-integration`
working tree, based on the previously built `frontend` branch. Review and merge
the integration into the deployment branch before publishing. No branches were
pushed or merged by this implementation step.

On the existing Vercel project set:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-project-publishable-key
TIMESLICE_SITE_URL=https://timeslice-dashboard.vercel.app
GOOGLE_BACKEND_URL=https://YOUR_BACKEND
```

Redeploy the frontend. When deploying via CLI from inside `frontend/`, run
`npx vercel --prod` and use the existing `timeslice-dashboard` project. For Git
builds, set Root Directory to `frontend`. These variables are read server-side.
Never set the Google client secret, Fernet key, or Supabase secret key on the
frontend. The Next.js routes proxy only the allowed Calendar endpoints, forward
the verified user access token, reject cross-origin disconnect/logout requests,
and disable caching. The backend does not need browser CORS access.

For local testing, copy `frontend/.env.example` to `frontend/.env.local`, replace
its placeholders, run the public backend on 8001 with real configuration, then
run `npm run dev -- --port 3001` from `frontend/`. Supabase must allow the local
app callback. Do not use fake credentials and claim live OAuth has been tested.

## Google audience and publication

While the Google OAuth app is in Testing, add every demo account to its test-user
list. Keep Google Calendar API enabled. The sign-in request includes offline
access and consent so Google can return a refresh token; Calendar permissions
must be approved. Users need no Cloud project or API keys of their own.

Before letting arbitrary public users connect, configure the Google app's
branding, application links/domains, privacy policy, requested scopes and audience
for publication. Google may require verification for these Calendar scopes.
Do not promise unrestricted sign-in until Google accepts the production setup.
If the UI shows an unverified-app warning, the user must review and complete it.

## Validation / demo

1. Open the app in a fresh browser session. It should show demo data, not another
   person's Calendar. Open Settings → Sign in & connect Google Calendar.
2. Choose an allowed test account, approve the requested scopes, and return to
   the app. The Settings status should show that account's email and Connected.
3. The charts and activities should show real timed events. All-day and
   transparent/free events are excluded from hourly charts. Imported events
   without a TimeSlice category appear in Admin with an explicit UI explanation.
4. Overlapping time is counted once and split evenly between active categories.
   Event duration in the activities table still describes its own scheduled span.
5. Sign out. A second user signs in and must see only their own data. The backend
   never accepts a client-supplied user ID to choose a token record.
6. Disconnect removes that user's stored Google grant; it does not revoke the
   grant in Google's account console. Sign out revokes the current Supabase
   session and clears local session cookies. Neither operation deletes events.
7. The WhatsApp/AI feed remains simulated for anonymous demo users and is
   replaced by a connection note for real accounts until Eva/Jia wire action data.

Automated checks (all Google/Supabase calls mocked):

```sh
/tmp/timeslice-google-venv/bin/python -m pip install -r backend/integrations/google/requirements-dev.txt
/tmp/timeslice-google-venv/bin/python -m unittest discover -s backend/integrations/google/tests -q
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

References: [Supabase Google OAuth](https://supabase.com/docs/guides/auth/social-login/auth-google),
[Supabase server-side auth](https://supabase.com/docs/guides/auth/server-side),
[Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Google OAuth web applications](https://developers.google.com/identity/protocols/oauth2/web-server).

## WhatsApp execution service

`backend.main:app` now executes Calendar plans instead of returning simulated
success. Deploy it with `backend/requirements.txt` and the same Google, Supabase,
and encryption settings as the connection API. Set `AI_SERVICE_TOKEN` to the
same server-only value on the Twilio worker and AI service. The worker's
`AI_BASE_URL` must point to that AI service.

`POST /api/execute` requires its service bearer token, the resolved Supabase user
UUID, message ID, and `authorization_source=inbound_whatsapp_create_request`.
Only proposed timed events are accepted. Availability is checked before writes,
Google IDs are returned only after successful creation, and retry IDs are derived
from the WhatsApp message and plan position. Retry the same plan in the same order;
a changed payload is rejected by the Calendar adapter's payload checks. Unscheduled
Tasks are returned for clarification rather than reported as synchronized.

## Enable Google Tasks

1. Enable Google Tasks API in the same Google Cloud project as the OAuth client.
2. Run `migrations/002_task_executions.sql` in Supabase SQL Editor.
3. Set `GOOGLE_ENABLE_TASKS=true` on both Next.js and Python services; restart/redeploy.
4. Reconnect Google from Settings and approve Tasks permission in addition to Calendar.

Task-only WhatsApp plans now create tasks in the user's default Google Tasks list,
including category notes and optional due dates. Mixed event/task plans require
separate messages. Tasks do not contribute hours to Calendar analytics.
Durable per-user message reservations reuse completed task IDs on retries. Pending
reservations are never automatically reinserted: after an uncertain response, an
operator must check Google Tasks and reconcile the stored ID before retrying.
Do not delete a pending reservation without confirming the provider did not write.

## Separate connection buttons

Settings offers Calendar and Tasks buttons with statuses derived from the saved,
verified scopes. `GET /api/auth/login?service=calendar|tasks` requests the selected
service; Google incremental authorization retains existing permissions. The chosen
service is held in a short-lived HttpOnly cookie through the PKCE callback. Backend
verification requires the selected scope and rejects a grant that drops an existing
service. Both services use the same encrypted Google account grant; disconnecting
the Google account removes both local connections. No extra database migration is
needed for separate statuses.
