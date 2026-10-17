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

There are no API calls, real connected accounts, persistent preferences, or
Supabase subscriptions. Category IDs match the shared contract: `academics`,
`career`, `social`, `health`, and `admin`. Replace the mock data layer when backend
contracts and account authentication are ready. Frontend demo activity phases
(`completed` and `upcoming`) are display-only and do not represent backend Google
sync execution status.
