# PaytmFlow

A deterministic financial-journey recovery engine. AI proposes and explains; deterministic
code decides and writes. Six journey packs — **LENDING, INSURANCE, CREDIT_CARD, KYC,
ACCOUNT_OPENING, INVESTMENT** — share one journey-agnostic frontend and one backend engine
driven entirely by YAML manifests.

This repository is the merged result of two independently built halves (frontend + backend)
integrated against a single frozen API contract. See `00_SHARED_CONTRACT.md` for the
ownership boundary and cross-cutting rules, `01_DEV1_FRONTEND_PLAN.md` /
`02_DEV2_BACKEND_PLAN.md` for the per-side implementation plans, and `contract/openapi.yaml`
for the authoritative API surface (12 endpoints, frozen per Shared Contract §9).

## Layout

```
paytmflow/
├── frontend/    # React 18 + TS + Vite SPA (owned by the frontend side)
├── backend/     # FastAPI + PostgreSQL engine (owned by the backend side)
├── contract/    # Shared: openapi.yaml + fixtures (both sides read this, neither owns it)
├── 00_SHARED_CONTRACT.md
├── 01_DEV1_FRONTEND_PLAN.md
├── 02_DEV2_BACKEND_PLAN.md
└── README.md
```

## Stack

**Frontend:** React 18, TypeScript (strict), Vite, Tailwind, React Router, TanStack Query,
Zustand, React Hook Form + Zod, MSW (mock mode), Vitest, Playwright.

**Backend:** Python 3.12, FastAPI, Pydantic v2 (strict), SQLAlchemy 2 (async), Alembic,
PostgreSQL 16, uv, PyMuPDF, itsdangerous (signed session cookie), pytest, HTTPX, ruff,
mypy (strict on `app/core`), import-linter, structlog.

## Running locally

```bash
# 1. Postgres + backend
cd backend
docker compose up -d postgres
uv sync
uv run alembic upgrade head
make api      # or: uv run uvicorn app.main:app --port 8000 --loop none

# 2. Frontend (separate shell)
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api -> http://localhost:8000
```

`make api` runs without `--reload` and with `--loop none` - required on native Windows,
where uvicorn's default event loop setup silently breaks psycopg3's async driver (every
request would 500). Harmless on Docker/Linux, where that code path never runs; see the
comment above the `api` target in `backend/Makefile` for the full explanation. If you're
on macOS/Linux and want hot-reload for local dev, `uv run uvicorn app.main:app --reload
--port 8000` works fine directly.

By default the frontend runs in `VITE_API_MODE=mock` (MSW, no backend required — see
`frontend/.env`). Set `VITE_API_MODE=live` to talk to the real backend above through the
Vite dev proxy at the relative path `/api/v1/...` (never hardcode `http://localhost:8000`
in application code).

## Core invariants

- The deterministic engine (`backend/app/core`) is pure: no imports from `app.ai`, `app.db`,
  `app.api`, `app.services`, or `app.evidence` (enforced by `.importlinter`).
- Snapshots are immutable and append-only; only `deterministic_check()` mints a `CheckToken`.
- `POST /evidence` is preview-only and creates no snapshot; `POST /actions` is the sole state
  mutation endpoint and requires `expected_snapshot_id` + a fresh `idempotency_key`.
- Readiness is an enum only: `READY | NOT_READY | NEEDS_REVIEW | DEAD_END` — never a score,
  probability, or percentage.
- Journey-specific behaviour lives in `backend/app/packs/manifests/*.yaml`, not in code.

## Tests

```bash
# Backend
cd backend
uv run pytest                    # add REQUIRE_POSTGRES=1 to fail instead of skipping if Postgres is down
uv run ruff check app tests
uv run mypy --strict app/core    # the actual spec requirement, and clean
lint-imports

# Frontend
cd frontend
npm run lint && npm run typecheck && npm run test && npm run test:e2e
```

`uv run mypy app` (whole-app, non-strict) also runs and is what `make type-check` invokes,
but it currently reports pre-existing errors outside `app/core` (mostly `app/services`,
`app/evidence`, `app/eval` - narrow-typing gaps like unvalidated `Any` flowing into a
`Literal` field, not runtime bugs). `app/core` itself - the one the spec holds to strict
typing - is clean. Don't expect a clean whole-app `mypy` run; do expect a clean
`mypy --strict app/core`.
