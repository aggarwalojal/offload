# Eva's component test results

Verified October 17, 2026 on `whatsapp-database` using Python 3.13 and PostgreSQL 15.

**Result: 83 tests passed, none failed or skipped.** Runtime was about 4 seconds.
`python -m pip check` also passed with no broken requirements.

## What was exercised

| Area | Cases and verified outcome |
| --- | --- |
| Full component flow | A signed webhook passes through the real API, AI adapter, repository, SQL functions, queue workers, sender and dashboard endpoints. One event and one task persist, with a 120-minute planned total and one confirmation. |
| Duplicate delivery | Submitting the same MessageSid twice and running workers repeatedly produces one inbox row and one outgoing confirmation. |
| Partial execution | A successful event and failed task retain their separate outcomes; the reply reports both accurately. |
| Clarification | Missing event times prevent execution of the entire plan; clarification records persist and add no planned minutes. |
| Missing/broken AI | Unconfigured service, timeout, malformed output, HTTP failure, duplicate action IDs, mismatched results, changed approved fields and nonterminal outcomes cannot generate a false successful sync. |
| Webhook security | Invalid signatures, tampered text, wrong account/destination, malformed identifiers, JSON input and oversized text are rejected without persistence. New signed Twilio fields remain supported. |
| User isolation | Dashboard endpoints require verified user identity. A second user sees none of the first user's events, tasks or actions. Real PostgreSQL RLS and grants are tested separately from simulated Auth responses. |
| Database durability | Invalid event outcomes roll back without queuing a success reply. A late failure cannot overwrite a committed success. Error confirmations deduplicate. Unknown/opted-out phones are ignored. |
| Concurrent workers | Four concurrent claimers each compete for 12 messages; all 12 are claimed exactly once, with no duplicate IDs. |
| Outbound errors | Twilio 400/401/429 failures remain visible; 5xx, transport uncertainty and persistence failure after acceptance do not cause automatic duplicate sends. |
| Messaging window | Freeform replies work inside the window. Exactly 24 hours requires a template. Missing templates block delivery; configured templates use ContentSid/ContentVariables rather than a freeform body. |
| Opt-out | STOP disables messaging; a previously queued incoming request is not sent to AI after opt-out. Sender checks opt-in again before delivery. |
| Daily jobs | Both morning and evening jobs enqueue and send through the real SQL outbox. Repeated runs deduplicate. Disabled jobs do not fetch activities. An invalid user profile does not prevent processing the next user. |
| Daylight saving | Day boundaries and planned-time totals correctly span 23- and 25-hour days. A repeated fall-back local minute queues only one briefing. |
| Summaries | Events sort chronologically across different offsets. Due/overdue tasks appear; future and actually completed tasks are excluded. Recaps label planned rather than measured time. |
| Analytics | Overlapping categories share time, same-category overlaps count once, midnight clips correctly, and tasks/proposed/failed events add no planned time. Empty data returns zero totals. |
| Pagination | Activity reads and user scheduling continue when a server caps pages below the requested size. |
| Lifecycle | Health endpoint responds, and the owned HTTP client closes even when the application lifespan is interrupted. |

## Problems found and fixed

1. Short provider pages could silently truncate activities or skip users' daily jobs.
   Pagination now advances by the actual returned count until it reaches an empty page.
2. Briefings sorted timestamp strings, which could order mixed UTC offsets incorrectly.
   They now sort by the actual UTC instant.
3. Whitespace-only titles and external IDs passed validation. Python validation and
   the initial SQL migration now reject blank values.
4. An interrupted app lifespan could leave an HTTP client open. Cleanup now runs in
   a `finally` block.

Each fix has a regression test that reproduced the problem before the fix.
Existing installations can apply `002_reject_blank_activity_fields.sql` to upgrade
the database checks. Fresh installations apply both migrations in order. Do not
rerun the create-table migration on an existing database. The follow-up migration
rolls back if existing blank values need review rather than silently modifying data.

## How to repeat

From the repository root:

```sh
source .venv/bin/activate
python -m pytest -q
python -m pip check
```

PostgreSQL tests start a temporary UTF-8 cluster on a private Unix socket and stop
and delete it afterward. They do not connect to the existing local database. Set
`TEST_POSTGRES_BIN` to a PostgreSQL `bin` directory if its tools aren't found. A
sandbox may require approval to start PostgreSQL because it uses shared memory.

Fast unit/boundary checks without PostgreSQL:

```sh
python -m pytest backend/tests/test_whatsapp.py backend/tests/test_boundaries.py -q
```

Test code lives in `backend/tests/test_whatsapp.py`, `test_boundaries.py`,
`test_component_flow.py`, `test_database.py` and `database_assertions.sql`.

## What these results do and do not establish

The production Python modules and real SQL migration/functions run in these tests.
The integration harness substitutes HTTP transports for Twilio, Jia's proposed AI
API, Supabase Auth and Supabase's PostgREST interface. Its PostgREST stand-in forwards
the actual queries and RPC calls to disposable PostgreSQL under `service_role`.
It is not a complete emulation or verification of hosted PostgREST.

No real WhatsApp message or Google event was sent/created. Hosted Supabase Auth,
Realtime delivery, WhatsApp Sandbox membership/template approval, Google OAuth,
Gemini interpretation and the teammates' final API compatibility still need the
live smoke test in [the setup guide](eva-integration.md). A Twilio accepted SID is
not proof of delivery to a phone.

The only pytest warning was an installed Starlette TestClient deprecation notice
about its httpx integration; it did not affect results.
