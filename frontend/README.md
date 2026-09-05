# RiskMesh frontend

React console for the PRD's four Primary Screens (Risk Control Center, Ring
Details / Investigator, Threshold & Cost Analysis, Evaluation / Benchmark),
built against the existing, unchanged FastAPI backend in `riskmesh/api/`. No
endpoint changes; this directory is purely a new client.

## Stack

Vite + React 19 + TypeScript + Tailwind v4 (`@tailwindcss/vite`) +
`react-router-dom` + `@phosphor-icons/react`. Every dependency is pinned to
an exact version in `package.json` -- notably TypeScript at 5.9.3 rather than
the newly-registered 7.0.2 native rewrite, too fresh to trust for a project
this size; see `audit.md`'s Task 10 entry for the rest of the pin rationale.
No animation library, no global state
library, no data-fetching library -- local `useState`/`useEffect` plus a
~35-line `useFetch` hook cover every screen.

## Running it

1. Start the backend from the repo root (a separate process; this frontend
   never bundles or reimplements it):

   ```
   python -m uvicorn riskmesh.api.main:app --port 8000
   ```

2. Install and run the dev server from this directory:

   ```
   npm install
   npm run dev
   ```

   Opens on `http://localhost:5173` (or the next free port). The client talks
   directly to `http://127.0.0.1:8000` (hardcoded in `src/api/client.ts`,
   same pattern as `mockups/api.js`); the backend already sends
   `Access-Control-Allow-Origin: *`, so no dev-server proxy is configured.

3. Production build:

   ```
   npm run build
   ```

   Runs `tsc -b` then `vite build`, output in `dist/`. Preview it with
   `npm run preview`.

## Layout

- `src/api/` -- typed fetch wrappers (`client.ts`) and wire types
  (`types.ts`) for all 8 endpoints.
- `src/components/` -- shared UI: `RingGraph.tsx` (ported graph renderer),
  `ActionBar.tsx` (the four analyst actions, non-optimistic), `StatusTag.tsx`
  (icon + text status, never color-only), `AsyncState.tsx`
  (loading/error/empty primitives), `ExplainPanel.tsx`, `AuditTrail.tsx`.
- `src/pages/` -- the four screens, one per route.
- `src/hooks/useFetch.ts` -- the one data-fetching primitive the app needs.
