# Vyakhya frontend

React + Vite + TypeScript client for Vyakhya, an explainable scam pattern recognition system for UPI and banking payments. One codebase, four panels:

| Route | Panel | Roles |
|---|---|---|
| `/simulator` | Payment Simulator: pay screen, redaction preview, simulated signals, presets (incl. coached-victim trace), tier UI | user, analyst, admin |
| `/detection` | Scam Detection: live feed (`/stream`), review queue with hold countdown and dual review, novel clusters | analyst, admin |
| `/analysis` | Analysis: trends, tier and family breakdown, alert fatigue, language, fairness, model usage | analyst, admin |
| `/evaluation` | Model Evaluation: PR curve, leave-one-family-out, precision at CRITICAL, latency, registry, baseline vs fused | analyst, admin |

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # vitest
npm run typecheck && npm run lint && npm run build
```

### Demo mode vs backend

- **Demo mode (default):** with `VITE_API_BASE_URL` empty, the app uses an in-browser mock API (`src/shared/api-client/mock/`) with synthetic data. Demo accounts: `user`, `analyst`, `analyst2`, `admin`, password `demo`. Use `analyst` and `analyst2` to try the dual review of a CRITICAL release.
- **Backend:** copy `.env.example` to `.env` and set `VITE_API_BASE_URL=http://localhost:8000`. The client calls `POST /auth/login`, `POST /score`, `GET /events`, `GET /stream` (SSE, with a `/stream/ws` WebSocket fallback; token passed as `access_token` query param), `GET /cases`, `POST /verdict`, `GET /stats?range=7d|30d`, `GET /metrics`. Types are in `src/shared/api-client/types.ts`.

The mock scorer is a simple points model so the UI can be demoed. It is not the trained fusion model. It does reproduce the deck's coached-victim trace (R 18 → 40 → 66 → 82 → 90, ending in a hold), and there is a test for that.

## Structure

```
src/
  app/                 routes, layout, login
  shared/
    ui-kit/            buttons, cards, badges, fields, tables, modal, charts helpers
    api-client/        typed HTTP client + mock backend
    auth/              JWT decode, AuthProvider, RBAC route guards
    lib/               redaction, tier policy, formatting
    useLiveStream.ts   SSE with WebSocket fallback
  panels/              simulator/ detection/ analysis/ evaluation/
  theme/tokens.ts      single source for all colours (Tailwind theme reads from it)
public/mock-metrics/   placeholder metrics/*.json used in demo mode
```

## Honesty labels

- `SYNTHETIC`: figures from synthetic data. `SIMULATED`: signals the prototype cannot read for real (call, screen share, device, location, money graph). `BUILT` / `ROADMAP`: scope.
- `public/mock-metrics/*.json` are **placeholders** (marked `"placeholder": true`, shown with a banner) until `backend/jobs/eval.py` writes real ones. The text-only leave-one-family-out baseline matches the deck (mean 0.60).
- Raw message text is redacted in the browser before sending; the backend must redact again and never store it.
