# Connect your real Google Calendar locally

The deployed dashboard still uses mock data. This local page verifies real Google
OAuth and reads your Calendar without creating or modifying events. Credentials
are held only in server memory; restart means reconnect. Do not expose this demo
through ngrok or deploy it as a public backend.

## 1. Google Cloud

1. Open https://console.cloud.google.com/ and create/select **TimeSlice**.
2. Open **APIs & Services → Library**, search **Google Calendar API**, and enable it.
3. Open **Google Auth Platform**. If prompted, configure the app's branding and
   contact email. Choose an external audience for a personal Gmail account.
4. Keep the app in Testing and add the Google account you will use under
   **Audience → Test users**.
5. Under **Data Access**, configure these scopes:
   - `https://www.googleapis.com/auth/calendar.events.owned`
   - `https://www.googleapis.com/auth/calendar.freebusy`
6. Under **Clients**, create an OAuth client of type **Web application**.
7. Add this exact **Authorized redirect URI**:
   `http://localhost:8000/api/google/callback`
8. Copy the client ID and client secret into your local configuration below.
   Do not paste secrets into chat, commit them, or put them in frontend variables.

Calendar event-management access supports the existing integration's eventual
validated writes; the connection page itself only exposes read operations.

## 2. Local configuration

From the repository root:

```sh
cp backend/integrations/google/.env.example backend/integrations/google/.env
```

Edit `backend/integrations/google/.env` locally. Replace the client ID and client
secret placeholders. Keep:

```dotenv
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback
GOOGLE_ENABLE_TASKS=false
```

If `.env` already exists, edit it rather than overwriting it. `python-dotenv`
loads this specific file automatically; existing process environment takes priority.
The directory's `.gitignore` excludes `.env` and Google credential JSON files.

## 3. Run the connection page

```sh
python3 -m venv /tmp/timeslice-google-venv
/tmp/timeslice-google-venv/bin/python -m pip install -r backend/integrations/google/requirements.txt
/tmp/timeslice-google-venv/bin/python -m backend.integrations.google.demo_app
```

Open **http://localhost:8000/** in Chrome or Safari, click **Connect Google
Calendar**, then select your test account and approve the requested permissions.
Use that exact hostname throughout; `localhost` and `127.0.0.1` have different cookies.
If Google displays a warning or requires account action, complete it yourself in
your browser. Once connected, click **Read my next 7 days** to verify your events.
It returns a JSON event list. An empty list is valid if nothing is scheduled.

Routes:

- `POST /api/google/connect`: CSRF-protected start of Google OAuth.
- `GET /api/google/callback`: validates state and stores tokens on the server.
- `GET /api/google/status`: connection status without tokens.
- `GET /api/google/events`: upcoming seven days by default; optional timezone-aware
  `start_time` and `end_time` query parameters.

Access logging is disabled by the launcher so OAuth codes are not logged. The
server only listens on loopback; it rejects other hosts and non-local peers.
Cookies are HttpOnly and SameSite=Lax. No Google tokens appear in browser cookies,
HTML, JSON responses, or token files.

## 4. Connect the actual application

`routes.create_google_router` can be included in Jia's FastAPI application. Supply
an authenticated identity dependency that resolves the TimeSlice user from the
verified session and enforces CSRF for the connect POST. Supply Eva's encrypted,
per-user persistent credential store. Do not use browser-provided user IDs.
Update the callback URI to the hosted backend and register it in Google Cloud.
Then the frontend developer can connect Settings to the backend and replace mock
data with its activity endpoints. The local demo session is not production login.

## Tests

```sh
/tmp/timeslice-google-venv/bin/python -m pip install -r backend/integrations/google/requirements-dev.txt
/tmp/timeslice-google-venv/bin/python -m unittest discover -s backend/integrations/google/tests -v
```

These tests simulate Google responses; a real account is needed to verify the
live connection. No live events are written by the tests or connection page.
