WhatsApp messages need a signed, durable path to the AI service and a shared database
that the dashboard can read securely. This adds Eva's standalone FastAPI integration,
Supabase schema with per-user read policies, message queues, authenticated dashboard
reads and planned-time analytics, plus timezone-aware morning briefings and recaps.

The AI adapter validates proposed creates and Google execution outcomes before
persisting them and composing confirmations. Its proposed contract is documented for
Jia/Ojal; Gemini and Google integrations remain in their teammates' components.
WhatsApp sends require opt-in and enforce session/template restrictions.

Validation: 103 automated tests, including disposable PostgreSQL migration/security
checks, cover webhook signatures, ownership, duplicates, rollback, analytics overlaps,
DST, briefing/recap scheduling and uncertain delivery. A real classic Sandbox message
was persisted to hosted Supabase and answered by the worker; Twilio reported the reply
as read. Local credentials are excluded from Git. See `docs/eva-integration.md` for
setup and API contracts. Team agreement on the AI contract and integrated Google/AI
testing remain; real-phone scheduled briefing/recap delivery has not been checked.
