# TimeSlice Google integration

Implemented: environment configuration, an OAuth service for a single backend
process, and a Google Calendar service. No HTTP routes, persistent token storage,
availability planning, or Google Tasks operations are implemented yet.

## Install and test

From the repository root (Python 3.10+):

```sh
python3 -m venv /tmp/timeslice-google-venv
/tmp/timeslice-google-venv/bin/python -m pip install -r backend/integrations/google/requirements.txt
/tmp/timeslice-google-venv/bin/python -m unittest discover -s backend/integrations/google/tests -v
```

Tests mock token exchange and refresh; no Google account or live API is needed.

## Google Cloud setup

1. Enable Google Calendar API for your project. Enable Google Tasks API when
   `GOOGLE_ENABLE_TASKS=true`.
2. Configure the OAuth consent screen and add your demo account as a test user.
3. Create an OAuth client with application type **Web application**.
4. Register `http://localhost:8000/api/google/callback` as an authorized redirect
   URI, matching `GOOGLE_REDIRECT_URI` exactly.
5. Copy `.env.example` to `.env` in this directory and fill in your client ID and
   secret locally. These files are excluded by the directory's `.gitignore`.
   The config module reads process environment variables, not `.env` files;
   the backend entry point must load the file or export those variables.

Calendar-only access is the default. It permits event management on calendars
owned by the user and free/busy lookup. Tasks access is explicitly opt-in.

## Backend handoff

Construct one service instance after loading environment variables:

```python
from backend.integrations.google.config import get_google_config
from backend.integrations.google.oauth import GoogleOAuthService

service = GoogleOAuthService(get_google_config())
```

The upcoming authenticated authorization route should call:

```python
url = service.begin_authorization(
    user_id=current_user.id,
    session_id=verified_session.id,
)
# Redirect the browser to url; never log the URL or its state.
```

The callback route uses the SAME authenticated user and browser session:

```python
credentials = service.complete_authorization(
    user_id=current_user.id,
    session_id=verified_session.id,
    state=callback_state,
    code=callback_code,
    error=callback_error,
)
# Encrypt and store credentials under current_user.id on the backend.
# Return a connection-success message, never credentials or token JSON.
```

`current_user`, `verified_session`, and callback parameters above are integration
placeholders for the team's authenticated backend routes, not provided globals.
Never identify the user from a callback query parameter. Parse callback parameters
as single values and reject duplicates in the HTTP layer. Use a secure, HttpOnly,
SameSite=Lax session cookie (Secure in production) so the browser session survives
Google's redirect. The callback route does not exist yet.

Before subsequent Google API calls, load credentials from that user's protected
record, call `service.refresh_credentials(credentials)`, and persist the returned
credentials, including any rotated refresh token. OAuth consent grants API access;
it does not approve arbitrary event/task writes. Those still require a validated,
authorized action plan.

The methods are synchronous; use FastAPI synchronous routes or a worker thread.
Handle `InvalidOAuthState`, `GoogleConsentDenied`, and `GoogleReconnectRequired`
without exposing provider exceptions or tokens. Pending sign-ins expire after ten
minutes and are consumed even when exchange fails. PKCE verifiers stay server-side.
The pending-flow store is in memory: use one backend worker for the demo, expect
pending sign-ins to be lost on restart, and use a shared protected store before
running multiple workers.

References: [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[Google Python OAuth Flow](https://googleapis.dev/python/google-auth-oauthlib/latest/reference/google_auth_oauthlib.flow.html).


## Calendar service

`calendar.py` provides `CalendarEventInput`, `CalendarAction`, `CalendarResult`,
and `GoogleCalendarService`. These are integration-local contracts; no shared
backend schemas or routes have been changed.

Construct a service per authenticated user with that user's stored credentials:

```python
from datetime import datetime
from backend.integrations.google.calendar import (
    CalendarAction, CalendarEventInput, GoogleCalendarService,
)

calendar = GoogleCalendarService(
    user_id=current_user.id,
    credentials=credentials,
    oauth=service,
)

# Read-only lookup; credentials were retrieved for current_user by the backend.
events = calendar.list_events(
    start_time=datetime.fromisoformat("2026-10-18T00:00:00-04:00"),
    end_time=datetime.fromisoformat("2026-10-19T00:00:00-04:00"),
)
```

For a create, the backend builds `CalendarEventInput` with `title`, `category`,
`start_time`, `end_time`, and optional `description`. It builds `CalendarAction`
with a stable `action_id`, authenticated `user_id`, `operation="create"`, that
`event`, and `approved=True` **only after validating the user's authorization for
that exact activity**. The default is unapproved. AI output and client-provided
approval flags must not be passed through as authorization.

`calendar.execute(action)` returns `external_id`, `calendar_id`, the operation
status (`completed`), and the Google event response (except after deletion).
`completed` means the Google operation succeeded, not that the scheduled activity
has already occurred. Eva's database layer should store the returned external ID
and sync result. The service does not write to Supabase. Its `list_events` and
`get_event` methods return native Google dictionaries, including all-day dates
and recurrence instance information; these need normalization for analytics.

For updates and deletes, set `event_id` and `expected_etag` from the specific event
reviewed by the user. Updates include a complete new `CalendarEventInput`; deletes
must not include `event`. Conditional requests reject stale approvals with
`CalendarConflictError` (HTTP 412). Review the changed event before trying again.
This milestone refuses changes to recurring events and events with attendees;
all-day event updates are also unsupported. It does not create attendees or send
invitations. Unrelated event fields and private metadata survive updates.

Create IDs are deterministic per user/calendar/action. Retry an uncertain create
with the SAME action ID and contents. A matching existing event is recovered;
reusing that ID for different contents raises `CalendarConflictError` (HTTP 409).
Writes are not automatically retried after transport errors. For ambiguous update
or delete outcomes, read the target and reconcile its state before proceeding.
Availability checks and overlap detection are a separate upcoming module; this
service does not prevent scheduling conflicts yet.

The OAuth helper refreshes credentials before requests. Persist updated
credentials in the caller's secure token record, including when a Calendar
request fails after a successful refresh. `calendar.close()` releases the HTTP
session. Like OAuth, these network methods are synchronous.

Calendar references: [event listing](https://developers.google.com/workspace/calendar/api/v3/reference/events/list),
[event creation](https://developers.google.com/workspace/calendar/api/guides/create-events),
[conditional writes](https://developers.google.com/workspace/calendar/api/guides/version-resources).

## Availability and slot suggestion service

`availability.py` provides `TimeSlot`, `Conflict`, `AvailabilityReport`, and
`GoogleAvailabilityService` to check calendar availability, detect conflicts,
and suggest open time slots.

```python
from datetime import datetime, timedelta, timezone
from backend.integrations.google.availability import (
    GoogleAvailabilityService, TimeSlot,
)

availability = GoogleAvailabilityService(calendar)

target_slot = TimeSlot(
    start_time=datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc),
    end_time=datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc),
)

report = availability.check_availability(
    target_slot=target_slot,
    suggest_alternatives=True,
    limit=3,
)

if not report.is_available:
    print(f"Conflicts found: {[c.title for c in report.conflicts]}")
    print(f"Suggested alternative slots: {report.suggested_slots}")
```

