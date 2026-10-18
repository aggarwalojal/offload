# Always-on Offload backend

The frontend and encrypted Google API stay on their existing Vercel projects.
`render.yaml` adds one persistent Python web service containing the signed Twilio
webhook, authenticated AI parser, and queue worker. Gemini runs via its API;
Supabase remains the durable store. No laptop, ngrok, or extra database is needed.

## Before creating a service

This Blueprint selects paid `0.5c-512mb` compute (approximately US$7/month at the
time of preparation). Review Render's current price and billing terms before
applying it. Twilio, Gemini, Vercel, and Supabase usage charges are separate.
Free sleeping services do not provide the intended always-on worker behavior.

Keep exactly one instance and one Uvicorn process for the hackathon. The worker
lives for the service's process lifetime and stops cleanly on shutdown. Its queues
are stored in Supabase, not process memory. Interrupted `processing`/`sending`
items retain the existing reconciliation rules; never blindly reset uncertain
Google/Twilio writes. This setup is suitable for the demo, not a promise of
zero-downtime processing during hosting/provider outages.

## Deploy

1. Sign in to Render and create a Blueprint from `aggarwalojal/timeslice`, branch
   `main`, using `render.yaml` at the repository root.
2. Review the one-service paid plan before approving creation.
3. Enter these values in Render's private environment settings:
   - `SUPABASE_SERVICE_ROLE_KEY`: Eva's shared server key (never a publishable key).
   - `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`: the account owning the bot.
   - `AI_SERVICE_TOKEN`: exactly the same token as `timeslice-google-api` on Vercel.
   - `GEMINI_API_KEY`: the working Gemini API key.
   - Confirm `TWILIO_WHATSAPP_FROM` matches the Sandbox or registered sender.
4. Deploy. Render supplies `RENDER_EXTERNAL_URL` and `PORT`. The hosted entrypoint
   derives the exact webhook URL from this trusted origin and uses loopback HTTP
   for the parser. It does not trust forwarded request Host headers.
5. Open the new `/health`. It should report `worker_running: true`. Read its
   `webhook_url` value: use that exact URL in Twilio's **When a message comes in**
   field with HTTP POST. The worker probes the shared execution token with an
   empty invalid plan before claiming messages; no Google writes occur in that
   check. A failed probe makes health fail for operator investigation.
6. Set `WHATSAPP_BACKEND_URL` on the frontend Vercel project to the new Render
   origin (without `/api/whatsapp`), then redeploy the frontend.
7. Stop Eva's old local worker after the hosted service is ready. Keep the old
   web server/ngrok available until the Twilio webhook and frontend have switched.
8. Send Hi from a Sandbox participant, follow the link, connect Google services,
   verify WhatsApp, and send an explicit event plus a task. Confirm Google writes
   and dashboard updates. Only then close the old server/ngrok and Eva's laptop.

Never paste secret values in chat, source control, screenshots, or deployment logs.
The Render deployment needs explicit permission to store these credentials in
that hosting account; existing Vercel secrets are not automatically copied.

## Alternative hosts

A persistent Docker/VM/Python host can run:

```sh
pip install -r backend/requirements.txt -r backend/requirements-whatsapp.txt
uvicorn backend.hosted:create_hosted_app --factory --host 0.0.0.0 --port "$PORT" --workers 1 --no-access-log --no-proxy-headers
```

Set `OFFLOAD_PUBLIC_URL` to its public HTTPS origin when `RENDER_EXTERNAL_URL`
isn't provided. Provision required environment secrets as above. Always-on
process support is required; do not deploy this combined worker to Vercel Functions.
