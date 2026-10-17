# TimeSlice frontend

A responsive Next.js App Router dashboard for the TimeSlice hackathon demo.

## Run locally

```sh
npm ci
npm run dev
```

Open http://localhost:3000. If that port is in use, run
`npm run dev -- --port 3001`.

```sh
npm run lint
npm run build
```

Production builds use Next.js's Webpack option for compatibility with the local
sandbox. Tailwind v4 is processed using its official PostCSS adapter. System fonts
keep builds independent of Google Fonts downloads.

## What works

- Daily planned-time distribution and weekly category charts with hover details.
- Dashboard, Activity, and Settings navigation.
- Previous/current week switching.
- Activity category filters, search, and empty states.
- A simulated AI activity feed with pause/resume controls.
- CSV export of the sample day's eight activities.
- Session-only demo preference toggles.
- Responsive layouts and keyboard-accessible controls.

## Data and components

The fixed October 17, 2026 demo schedule lives in `lib/mock-data.ts`. All totals,
category percentages, activity durations, and weekly summaries derive from mock
data. Times display in America/New_York; charts represent planned time. The agent
feed cycles illustrative examples without changing analytics.

Reusable components live in `components/`: dashboard shell, charts, activity
table, agent feed, settings, and shared UI. The App Router entry point is
`app/page.tsx`, not `src/app/page.tsx`.

## Multi-user Calendar integration

The integration now includes server-side Supabase Google sign-in, per-user
Calendar connection/disconnect, app sign-out, a backend proxy, live Calendar
analytics, loading/error/empty states, and the anonymous demo fallback. Google
provider credentials do not enter browser JavaScript or app-session cookies.

It requires Supabase, the encrypted token table, Google provider configuration,
a deployed backend, and Vercel environment settings before real sign-in works.
Follow `../backend/integrations/google/PUBLIC_SETUP.md`; `.env.example` lists the
frontend server variables. `npm test` checks overlap accounting, date clipping,
all-day exclusion, and timezone behavior. Live Google OAuth still needs an
end-to-end test with configured accounts; automated provider tests use mocks.

All-day and free/transparent events do not count toward planned hours. Unlabeled
Calendar events appear in Admin until categorized; the interface explains this.
Overlap time is split evenly between active categories and counted only once.
WhatsApp, briefings, and AI action history still need the shared backend wiring.
