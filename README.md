# PaytmFlow

A deterministic financial journey recovery platform with local Document AI.

PaytmFlow turns fragmented document and form requirements into a guided,
state-aware workflow. A user picks a financial goal, and the system tracks
exactly which requirements are outstanding, recommends the single next
action that unblocks progress, interprets uploaded documents through a
locally-run OCR and classification pipeline, and advances a versioned
journey state only when that evidence has actually been verified.

The pipeline behind every step is:

```
Document ingestion → OCR → classification → field extraction
  → evidence validation → deterministic workflow evaluation
  → next-action recommendation → user action → updated state → handoff
```

**This is a prototype.** It demonstrates the end-to-end workflow and the
technical architecture behind it — deterministic state management, a
manifest-driven journey engine, and a self-contained Document AI pipeline —
running against a real PostgreSQL database. It is not a production
financial-services platform, and nothing in this repository should be
treated as one.

## Why this exists

Financial workflows — applying for a loan, re-verifying KYC, opening an
account — usually fail the user in the same way: it's unclear what's
missing, unclear why, and unclear what happens after a document is
submitted. PaytmFlow addresses this directly. Every blocked requirement
carries a plain-language reason. Every recommended action is derived from
the journey's actual current state, not a static checklist. And every piece
of uploaded evidence goes through a real, local document-understanding
pipeline rather than a rubber stamp — a document that doesn't match what
was asked for is rejected, not silently accepted.

The part of the implementation most worth reading is the separation between
interpretation and decision: an evidence pipeline extracts and scores what a
document contains, but it never writes state directly. A separate,
deterministic engine — driven entirely by per-journey YAML configuration —
is the only thing that can decide a requirement is satisfied and advance the
journey. That boundary is enforced in code, not just in convention (see
[Document integrity](#document-integrity) below).

## Key capabilities

- **Six independent financial journeys** sharing one frontend and one
  backend engine, entirely configuration-driven — no journey-specific
  branching in application code.
- **Deterministic workflow engine**: journey state is a set of typed
  fields connected by an explicit dependency graph; state only changes
  through one audited mutation path.
- **Local Document AI**: OCR, document-type classification, and structured
  field extraction all run locally, with no external API dependency.
- **Cross-document consistency checks**: a second document that
  contradicts an already-applied value (a different income figure, a
  mismatched identifier) is flagged for review rather than silently
  overwriting the first.
- **Evidence integrity controls**: uploaded documents are untrusted input.
  Client-declared document types and client-supplied extracted values are
  never taken at face value — the server independently resolves and
  classifies evidence.
- **Explicit "Needs Review" handling** for evidence that is genuine but
  falls short of the confidence needed for automatic verification, instead
  of a binary accept/reject.
- **Snapshot-based, append-only state transitions**, each requiring the
  caller's expected snapshot version — stale or conflicting mutations are
  rejected, never silently applied.
- **Session isolation**: a signed, anonymous session cookie scopes every
  journey, and one session cannot read or mutate another's data.
- **Idempotent mutations** on the sole state-changing endpoint, keyed by a
  client-supplied idempotency key, so a retried or double-submitted request
  cannot double-apply.
- **Responsive, accessible web UI** covering the full journey lifecycle
  from goal selection through handoff.
- **Real PostgreSQL persistence** with append-only, trigger-enforced
  snapshot immutability.
- **API-first design**: the frontend and backend communicate over a single
  documented REST contract (`contract/openapi.yaml`).
- **A substantial automated test suite** spanning unit, integration,
  contract, and end-to-end browser coverage (see [Testing & quality](#testing--quality)).

## The six journeys

| Journey | Purpose |
|---|---|
| Lending | Instant unsecured personal loan application, up to ₹5,00,000 |
| Insurance | Health insurance enrollment with cashless hospitalization cover |
| KYC | RBI-mandated periodic identity re-verification for existing customers |
| Credit Card | Co-branded cashback credit card application with zero annual fee |
| Account Opening | Digital zero-balance savings account opening |
| Investment | Mutual fund SIP and lump-sum investment portfolio setup |

Each journey is defined entirely by a YAML manifest under
`backend/app/packs/manifests/` — its required fields, its dependency graph,
its available actions, and which document types satisfy which fields. The
frontend and the deterministic engine are both journey-agnostic; adding or
changing a journey is a configuration change, not a code change.

## How the system works

```
Browser
   │
   ▼
React Frontend  (Vite dev server / static build)
   │
   │ REST / JSON, single documented contract
   ▼
FastAPI API
   │
   ├── Journey Service           orchestrates requests, loads manifests
   ├── Deterministic Engine      pure state evaluation, no I/O
   ├── Recommendation Planner    derives the next action from current state
   ├── Evidence Pipeline         resolves, stores, and reconciles uploads
   ├── Local Document AI
   │      ├── OCR                 PyMuPDF (native PDF text) + Tesseract (images/scans)
   │      ├── Classification      TF-IDF + logistic regression, one model per journey
   │      └── Field Extraction    rule/regex-based, with OCR-noise normalization
   │
   ▼
PostgreSQL  (append-only snapshots, trigger-enforced immutability)
```

- **React Frontend** renders the ten-screen journey flow (Home, journey
  selection, goal, status, recommendation, evidence/form action, AI
  analysis, updated state, handoff, and journey list) from server-supplied
  data only — labels, values, and explanations are never computed
  client-side.
- **FastAPI API** exposes a single REST surface documented in
  `contract/openapi.yaml`; every mutating request goes through one endpoint.
- **Journey Service** is the orchestration layer: it loads the relevant
  journey manifest, calls the deterministic engine to evaluate state, and
  calls the evidence pipeline when a document is involved.
- **Deterministic Engine** (`backend/app/core`) is intentionally pure — no
  database access, no AI calls, no randomness. It evaluates the current
  snapshot's fields against the manifest's dependency graph and produces
  the next valid state. This boundary is enforced by an import-linter
  contract, not just convention.
- **Evidence Pipeline** resolves an uploaded document through OCR,
  classification, and extraction, then reconciles the result against the
  manifest's evidence mappings — but it can only *propose* a resulting
  state; only the deterministic engine can commit one.
- **PostgreSQL** stores every journey as an append-only sequence of
  immutable snapshots, with database triggers (not just application code)
  preventing an existing snapshot row from being modified.

## Document AI

The Document AI pipeline (`backend/app/docai/`) is a from-scratch, locally
run implementation — no external AI API, no hosted model. It exists to turn
an uploaded file into structured, validated field values, in six stages:

1. **Ingestion** — the uploaded file's magic bytes are validated against an
   allow-list before anything else touches it; its declared MIME type is
   never trusted on its own.
2. **OCR** — native PDF text is extracted with PyMuPDF; scanned PDFs and
   images fall back to Tesseract OCR via `pytesseract`, with layout and
   confidence metadata (bounding boxes, per-line confidence) carried
   forward rather than discarded.
3. **Document-type classification** — a TF-IDF (1–2 gram) vectorizer feeding
   a logistic-regression classifier, trained separately per journey
   (`backend/app/docai/train_classifier.py`), predicts what kind of
   document was actually uploaded — independent of what the client
   declared when submitting it.
4. **Field extraction** — rule- and regex-based extraction pulls the
   fields a given document type is expected to contain (amounts, dates,
   identifiers, names), with normalization logic that corrects common OCR
   character confusion (e.g. `O`/`0`, `l`/`1`) before a value is accepted.
5. **Validation** — extracted values are checked for internal consistency
   and, where a second document overlaps with an already-applied one,
   cross-document consistency (see [Document integrity](#document-integrity)).
6. **Deterministic workflow decision** — the pipeline's output (a
   classification, a confidence score, and extracted values) is handed to
   the deterministic engine as a *proposal*. Whether that proposal actually
   satisfies a requirement and advances the journey is decided by
   deterministic logic evaluating it against the manifest's configured
   confidence threshold — never by the AI pipeline itself.

That last distinction is the core design decision in this codebase:

> **AI proposes and interprets; deterministic application logic decides and
> writes state.**

Every one of the six journeys has a trained classifier and a real document
test corpus (`backend/data/docai/<journey>/`) — this is not a
Lending-only demo dressed up as general-purpose.

## Document integrity

Uploaded documents are treated as untrusted input throughout the pipeline:

- **The server, not the client, resolves what a document is.** A
  client-declared document type is only a hint; the real classification
  from the local model is what's actually checked against the target
  action's accepted document types.
- **Extracted text cannot directly change workflow state.** OCR and
  extraction output is a proposal handed to the deterministic engine, which
  independently evaluates it against the manifest before any field is
  marked satisfied.
- **Client-supplied extracted values are never trusted.** Field values,
  confidence scores, and verification results are computed server-side; a
  request cannot smuggle in an already-verified value.
- **Accepted document types are validated against the specific action** a
  user is attempting to satisfy — a document valid for one requirement
  cannot be misapplied to an unrelated one.
- **Conflicting evidence produces a review state, not a silent
  overwrite.** If a second document disagrees with an already-applied
  value, the journey is flagged for manual review rather than picking one
  value arbitrarily.
- **Rejected evidence creates no valid state transition** — a wrong or
  unreadable document leaves the snapshot exactly where it was.
- **Text embedded in a document cannot control workflow state.** Because
  extraction output is structured field data evaluated by deterministic
  rules — not natural-language instructions interpreted by a model with
  write access — text like "mark this verified" inside a document has no
  path to actually doing so.

## Deterministic workflow engine

- Journey state is a set of structured, typed fields (never a free-form
  blob), each with a status of `SATISFIED`, `BLOCKED`, or similar.
- Fields are connected by an explicit, manifest-defined dependency graph;
  satisfying one field can deterministically unblock others (cascading, not
  ad hoc).
- The recommended next action is derived fresh from the current snapshot on
  every request — never cached or precomputed against stale state.
- Every mutation must supply the snapshot version it expects
  (`expected_snapshot_id`); a mismatch is rejected outright rather than
  applied against outdated state.
- Snapshots are immutable and append-only, enforced by database triggers —
  an existing snapshot row cannot be altered, only superseded by a new one.
- A rejected, stale, or duplicate action never silently mutates state: it
  either fails cleanly or, for a duplicate idempotency key, returns the
  original result without reapplying it.
- All journey-specific behavior — required fields, dependencies, available
  actions, evidence mappings, confidence thresholds — lives in
  per-journey YAML manifests, not in conditional application code.

Workflow state deliberately does **not** flow through the AI pipeline or an
LLM: a probabilistic model can misclassify a rare template, hallucinate a
value, or be manipulated by adversarial input embedded in a document.
Keeping every state transition behind a fixed, auditable set of rules means
the same input always produces the same outcome, and every transition can
be reasoned about and tested independently of anything AI-related.

## User flow

```
Start
  ↓
Choose a financial goal
  ↓
Provide basic information
  ↓
Review current blockers
  ↓
See recommended next action
  ↓
Upload evidence / complete form
  ↓
Document AI analysis
  ↓
Deterministic validation
  ↓
Journey state update
  ↓
Review remaining blockers
  ↓
Handoff
```

A document that is genuinely correct but falls below the manifest's
confidence threshold for automatic verification produces an honest **Needs
Review** state — the extracted value isn't in question, but it's routed for
manual confirmation instead of being applied immediately. The UI never
represents an unverified or under-review result as complete, and never
surfaces a score, probability, or eligibility figure of any kind.

## Technology stack

**Frontend**

| Technology | Role |
|---|---|
| React 18 + TypeScript | UI framework |
| Vite | Dev server and build |
| React Router | Client-side routing |
| TanStack Query | Server-state management |
| Zustand | Local UI state |
| React Hook Form + Zod | Form handling and validation |
| Tailwind CSS | Styling |
| MSW | Mock API layer for offline frontend development |
| Vitest + Testing Library | Unit tests |
| Playwright | End-to-end browser tests |

**Backend**

| Technology | Role |
|---|---|
| Python 3.12+ | Runtime |
| FastAPI | API framework |
| Pydantic v2 | Schema validation |
| SQLAlchemy 2 (async) | ORM / database access |
| Alembic | Database migrations |
| PostgreSQL 16 | Persistence |
| itsdangerous | Signed session cookies |
| uv | Dependency management |

**Document AI**

| Technology | Role |
|---|---|
| PyMuPDF | Native PDF text extraction |
| Tesseract OCR (via `pytesseract`) | OCR for scanned documents and images |
| Pillow | Image preprocessing |
| scikit-learn (TF-IDF + logistic regression) | Per-journey document classification |
| Custom rule/regex extraction | Structured field extraction and OCR-noise normalization |
| joblib | Trained model serialization |

**Quality tooling**

| Tool | Scope |
|---|---|
| pytest + HTTPX | Backend unit, integration, and contract tests |
| ruff | Python linting |
| mypy | Python type checking |
| import-linter | Enforces the deterministic engine's dependency boundary |
| Playwright | Browser end-to-end tests |
| ESLint + `tsc` | Frontend linting and type checking |

## Project structure

```
paytmflow/
├── frontend/                  React + TypeScript SPA
│   ├── src/screens/           The ten journey-flow screens + Help
│   ├── src/components/        Shared UI and primitives
│   ├── src/mocks/              MSW fixtures for offline (mock-mode) development
│   └── tests/                 Unit and end-to-end tests
├── backend/                    FastAPI service
│   ├── app/core/               Pure deterministic engine (no I/O)
│   ├── app/api/                REST endpoints
│   ├── app/services/           Orchestration layer
│   ├── app/evidence/           Evidence resolution, storage, reconciliation
│   ├── app/docai/               OCR, classification, extraction, trained models
│   ├── app/packs/manifests/    Per-journey YAML configuration
│   └── tests/                  Unit, integration, contract, and safety tests
├── contract/
│   └── openapi.yaml             The single source of truth for the API surface
└── README.md
```

## Getting started

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Backend runtime |
| [uv](https://docs.astral.sh/uv/) | Backend dependency and virtualenv management |
| Node.js (recent LTS) and npm | Frontend tooling — no exact version is pinned in this repository; Vite 5 and TypeScript 5.6 require a reasonably current Node release |
| PostgreSQL 16 | Via Docker (recommended) or a local install |
| Docker (recommended) | Runs PostgreSQL via `backend/docker-compose.yml` |

### 1. Clone

```bash
git clone <repository-url>
cd paytmflow
```

### 2. Configure environment

Backend configuration lives in `backend/.env` (copy from
`backend/.env.example`); frontend configuration lives in `frontend/.env`
(copy from `frontend/.env.example`). **Never commit real secrets** — the
values below are the safe local-development placeholders already shipped
in the example files.

`backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow
APP_ENV=local
SESSION_COOKIE_NAME=pf_session
SESSION_SECRET=change-me-32-bytes-minimum-session-secret-key
SESSION_TTL_DAYS=30
CORS_ORIGINS=http://localhost:5173
AI_PROVIDER=mock          # mock | llm | local_ml — see "Local Document AI" below
AI_TIMEOUT_SECONDS=4
AI_API_KEY=
AI_MODEL=
EVIDENCE_STORAGE_DIR=./storage/evidence
EVIDENCE_MAX_BYTES=10485760
DEMO_RESET_SECRET=change-me-demo-reset-secret
LOG_LEVEL=INFO
```

The application deliberately refuses to start with these placeholder
`SESSION_SECRET` / `DEMO_RESET_SECRET` values outside `APP_ENV=local` or
`ci` — supply real, unique values before running with any other
`APP_ENV`.

`frontend/.env`:

```env
VITE_API_MODE=mock        # mock (MSW, no backend needed) | live (real backend)
VITE_API_BASE=/api/v1
VITE_SHOW_DEV_BADGES=true
```

## Running the application

### Start the database

```bash
cd backend
docker compose up -d postgres
```

### Start the backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --loop none
```

The API is now at `http://localhost:8000` (interactive docs at
`http://localhost:8000/docs`).

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend is now at `http://localhost:5173`, proxying `/api/v1/*` to the
backend above.

### Open the application

Visit `http://localhost:5173`. With `VITE_API_MODE=mock` (the default), the
frontend runs entirely against MSW-mocked responses and needs no backend at
all — useful for frontend-only development. Set `VITE_API_MODE=live` to
talk to the real backend and PostgreSQL started above.

## Local Document AI

Setting `AI_PROVIDER=local_ml` in `backend/.env` switches evidence
processing from the deterministic mock provider to the real local pipeline
described in [Document AI](#document-ai) above.

- **No API key is required** — `local_ml` performs OCR, classification, and
  extraction entirely on the machine running the backend.
- **Trained models are already committed to the repository** under
  `backend/app/docai/models/` (one `.joblib` classifier plus metadata per
  journey) — no separate download or training step is needed to run the
  application.
- **Tesseract OCR must be installed and on `PATH`** on the host machine
  (`pytesseract` calls out to the `tesseract` binary); everything else is a
  standard Python dependency installed via `uv sync`.
- Model training scripts (`backend/app/docai/train_classifier*.py`) and the
  underlying labeled datasets (`backend/data/docai/`) are included for
  anyone who wants to retrain or inspect them, but are not required for
  normal operation.

## API

The full, authoritative API surface is documented in
`contract/openapi.yaml`; the backend also serves interactive Swagger docs
at `/docs` once running. Major endpoints, grouped by purpose:

**System**
- `GET /api/v1/health`
- `GET /api/v1/session`

**Journey packs**
- `GET /api/v1/journey-packs`
- `GET /api/v1/journey-packs/{journey_type}`

**Journeys**
- `GET /api/v1/journeys`
- `POST /api/v1/journeys`
- `GET /api/v1/journeys/{journey_id}`
- `GET /api/v1/journeys/{journey_id}/recommendation`
- `GET /api/v1/journeys/{journey_id}/diff`

**Evidence and actions**
- `POST /api/v1/journeys/{journey_id}/evidence` — preview-only; creates no state transition
- `POST /api/v1/journeys/{journey_id}/actions` — the sole state-mutating endpoint
- `POST /api/v1/journeys/{journey_id}/clarifications`

**Demo**
- `POST /api/v1/demo/reset`

## Security

- **Signed, anonymous session cookies** (`itsdangerous`) scope every
  journey to the session that created it — no username/password account
  system.
- **Cross-session isolation is enforced server-side**: a request for a
  journey belonging to a different session is rejected, not merely hidden
  by the UI.
- **Stale-snapshot protection**: every mutation must supply the snapshot
  version it expects; a mismatch is rejected before anything is written.
- **Idempotent mutation handling** on the state-changing endpoint via a
  client-supplied idempotency key.
- **Evidence size limits** (`EVIDENCE_MAX_BYTES`, 10 MB by default) and
  **magic-byte file validation** — a file's actual content, not its
  declared extension or MIME type, determines whether it's accepted.
- **Untrusted document handling** throughout the evidence pipeline (see
  [Document integrity](#document-integrity)).
- **No client-side trust for critical evidence values** — verification
  results, extracted values, and confidence scores are computed and owned
  server-side.
- **Secret/config separation**: backend secrets never reach the frontend
  bundle; the application refuses to start with known placeholder secrets
  outside local/CI environments.

This describes the controls actually implemented in this codebase — it is
not a claim of formal security certification or a completed audit for
production use.

## Testing & quality

The most recent full verification pass (see
`backend/docs/paytmflow_ultimate_qa_report.md` for the complete history):

| Suite | Result |
|---|---|
| Backend pytest | 501/501 passed |
| Frontend unit tests (Vitest) | 339/339 passed |
| Playwright end-to-end | 52/52 passed |
| Ruff (backend lint) | Clean |
| ESLint + TypeScript (frontend) | Clean |
| import-linter | Clean — deterministic engine boundary intact |
| mypy (whole-app) | 126 pre-existing errors across 23 files, unrelated to and unaffected by this project's changes (zero delta) |

Beyond the automated suites, the application was verified with real
Chromium browser sessions against the real backend and a real PostgreSQL
database (not just mocked fixtures), covering:

- End-to-end walkthroughs of all six journeys through to handoff
- Deliberate wrong-document uploads, confirming rejection without state
  advancement
- A reproduced cross-document value conflict, confirming it triggers review
  rather than a silent overwrite
- XSS and injection payloads through form inputs, clarification responses,
  and document text
- Accessibility-tree inspection (landmarks, heading structure, labeled
  controls, dialog semantics) across key screens
- Responsive behavior at 375px, 768px, 1024px, and 1440px viewports

**Limitations of this testing, stated plainly**: the mypy result reflects
pre-existing, unrelated typing debt outside the deterministic engine's
`app/core` package (which itself type-checks cleanly under `mypy --strict`);
accessibility verification used the browser's accessibility tree and manual
keyboard testing, not certification against a real screen reader (NVDA,
JAWS, VoiceOver). Nothing here should be read as "bug-free," "fully
secure," or "production-ready" — it reflects what was actually tested and
what passed.

## Design and UX

The interface follows a single, consistent flow regardless of which
journey is active: a blocker-first status view surfaces exactly what's
outstanding and why, a recommendation view presents one primary next
action, and the same evidence/form interaction pattern handles every
document upload or field submission across all six journeys. An AI
analysis screen shows what the document pipeline actually found — including
an honest "Needs Review" state — before an updated-status screen confirms
what changed. A handoff screen closes out a completed journey without
implying an approval or guarantee, and a journeys list lets a user resume
any in-progress journey. A Help section provides searchable guidance
independent of any specific journey. The layout is responsive across
mobile, tablet, and desktop widths.

## Prototype limitations

- **Anonymous, cookie-based sessions rather than full user authentication**
  — there is no account system, password, or multi-device login.
- **Local, single-machine deployment assumptions** — the setup here targets
  a developer's machine or a demo environment, not a scaled production
  deployment.
- **Pre-existing mypy debt** outside the deterministic engine's `app/core`
  package (126 errors across 23 files), tracked but not yet resolved.
- **A small number of manifest-level configuration decisions remain
  deferred** (documented in the QA report) where the correct behavior
  depends on a product decision rather than an engineering fix.
- **No formal assistive-technology certification** — accessibility was
  verified via the browser's accessibility tree and manual testing, not a
  certified audit with a real screen reader.
- **Tesseract OCR must be available on the host** for the local Document AI
  pipeline to function; there is no bundled or containerized OCR runtime.

## Design principles

1. **Deterministic state over probabilistic workflow decisions** — the same
   input always produces the same journey outcome.
2. **Configuration-driven journeys** — journey behavior lives in YAML
   manifests, not conditional code.
3. **Server-authoritative evidence** — the client can propose; only the
   server decides what a document is and what it proves.
4. **Immutable, append-only state transitions** — history is never
   rewritten, only extended.
5. **AI as an interpreter, not the state authority** — the Document AI
   pipeline informs a decision; it never makes one.
6. **Explicit review paths for uncertainty** — evidence that doesn't clear
   a confidence threshold is routed for review, never silently accepted or
   rejected.
7. **Secure-by-default input handling** — uploaded files, extracted text,
   and client-declared values are all treated as untrusted until
   independently validated.

## License

License: Not currently specified.

## Contributing

1. Create a focused branch for your change.
2. Keep changes scoped — avoid mixing unrelated fixes or refactors in one
   branch.
3. Add or update tests covering the change.
4. Run the relevant checks before opening a pull request:
   ```bash
   # Backend
   cd backend && uv run pytest && uv run ruff check . && uv run mypy --strict app/core

   # Frontend
   cd frontend && npm run typecheck && npm run lint && npm run test
   ```
5. Open a pull request describing the change and its motivation.
