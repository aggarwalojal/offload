WhatsApp messages need a signed, durable path to the AI service and a shared database
that the dashboard can read securely. This adds Eva's standalone FastAPI integration,
Supabase schema with per-user read policies, message queues, authenticated dashboard
reads and planned-time analytics, plus timezone-aware morning briefings and recaps.

The AI adapter validates proposed creates and Google execution outcomes before
persisting them and composing confirmations. Its proposed contract is documented for
Jia/Ojal; Gemini and Google integrations remain in their teammates' components.
WhatsApp sends require opt-in and enforce session/template restrictions.

Validation: automated Python tests plus a disposable PostgreSQL migration/security
test cover webhook signatures, ownership, duplicates, rollback, analytics overlaps,
DST and uncertain delivery. See `docs/eva-integration.md` for setup and live smoke tests.
Live Twilio/Supabase credentials and agreement on the AI contract are still required.
