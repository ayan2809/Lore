# Lore frontend

React + Vite + TypeScript + Tailwind v4 + `react-force-graph-2d`. No router, no state library, no UI kit.

## Run it

```bash
cd frontend
npm install
cp .env.example .env        # optional; defaults work for a local backend
npm run dev                 # http://localhost:5173
```

**Normal mode** talks to the FastAPI backend at `VITE_API_BASE` (default `http://localhost:8000`).
The backend must allow CORS from `http://localhost:5173` with credentials (the session is a cookie).

**Mock mode** needs no backend. Everything comes from fixtures and a scripted event stream:

```bash
VITE_MOCK=1 npm run dev     # or set VITE_MOCK=1 in .env
```

Mock mode tips:

- Press **Run the 3 AM incident** as Arjun, then switch to Dana and run again: Dana's report includes the restricted `#pricing-private` thread, Arjun gets the yellow "1 restricted source matched" warning.
- As Dana, **Approve** the Slack post: it is blocked (it quotes a private thread). Delete the quoted line from the text and approve again: it is sent.
- Select alert **A-3002** to see the memory story (playbook recalled, 4 tool steps instead of 11).
- Turn **Graph OFF** and run again to see the weaker vector-only baseline.
- Contractor **Sam** sees almost nothing (public only).
- Add `?speed=3` to the URL to play the stream 3x faster.
- The mock lives in `src/api/mock.ts` (scripts) and `src/api/mockData.ts` (graph, sources, personas).

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm run build` | type-check (`tsc -b`) then production build into `dist/` |
| `npm run lint` | oxlint |
| `npm run preview` | serve the built `dist/` locally |

## Code map

```
src/
  api/
    types.ts        TS mirror of backend/lore/models.py (the contract) + the `Api` interface
    client.ts       fetch wrapper, SSE subscription; `api` = real client or mock (the ONE switch)
    mock.ts         fake backend for VITE_MOCK=1: scripted Story A / Story B / Graph-OFF runs
    mockData.ts     fixtures: personas, 67-node Kettle graph, source texts
  hooks/
    investigationState.ts   pure reducer: StepEvent -> trail, report, actions, summary + highlight sets
    useInvestigation.ts     hook: start a run, subscribe to SSE, expose state
  components/       TopBar, AlertPanel, GraphCanvas, Trail, ReportCard, ActionsPanel,
                    RunSummary, AskPanel, SourceDrawer (+ CitationChip, ui helpers)
  lib/format.ts     node colours, agent colours, formatting helpers
  App.tsx           layout and the few pieces of app-wide state (persona, mode, tab, graph)
```

How the live graph works: each `tool_result` event carries `node_ids` and `edges`. The reducer stores them on the trail
step. `computeHighlights()` turns the latest step (or the one you clicked) into the "glowing" set and all earlier steps into
the "visited" set; `GraphCanvas` draws glow, pulse and particles from those sets.

## Deploy to Vercel

1. Import the repo in Vercel, set **Root Directory** to `frontend`. Framework preset: Vite (build `npm run build`, output `dist`).
2. Add the environment variable `VITE_API_BASE=https://<your-api-domain>` (the Caddy HTTPS address of the VM). Do not set `VITE_MOCK`.
3. `vercel.json` rewrites every path to `index.html` (single page app).
4. Backend side: CORS must allow the Vercel origin with `allow_credentials=True`, and the `lore_session` cookie must be
   `SameSite=None; Secure`, because the page (vercel.app) and the API (your domain) are different sites.

Vite bakes `VITE_*` values in at build time, so redeploy after changing them.
