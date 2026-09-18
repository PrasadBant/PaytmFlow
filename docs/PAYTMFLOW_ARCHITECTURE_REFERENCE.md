# PaytmFlow — Architecture & Technical Reference Manual

> **Document Type:** Developer Quick Reference & System Architecture Specification  
> **Status:** Authoritative Repository Audit  
> **Target Audience:** Systems Architects, Core Backend Engineers, Frontend Engineers, Tech Leads  
> **Format:** Table-Driven, Diagram-Rich, Machine & Human Readable  

---

## 1. System Architecture Overview

```
                      ┌─────────────────────────────────────────────────────────┐
                      │                 USER CLIENT (BROWSER)                   │
                      │       React 18 SPA · TypeScript Strict · Tailwind       │
                      └────────────────────────────┬────────────────────────────┘
                                                   │
                                                   │ HTTP / HTTPS
                                                   │ Cookies: pf_session (HttpOnly, Signed)
                                                   ▼
                      ┌─────────────────────────────────────────────────────────┐
                      │              VITE DEV PROXY / NGINX EDGE                │
                      │               /api/v1/* -> Port 8000                    │
                      └────────────────────────────┬────────────────────────────┘
                                                   │
                                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               FASTAPI BACKEND ENGINE (PORT 8000)                                │
│                                                                                                 │
│  ┌───────────────────────┐   ┌──────────────────────────┐   ┌────────────────────────────────┐  │
│  │    API ROUTERS (v1)   │──>│   SERVICES ORCHESTRATOR  │──>│     SECURITY & SESSIONS        │  │
│  │ system, packs, journey│   │  journey_service.py      │   │  itsdangerous HMAC-SHA256      │  │
│  └───────────────────────┘   └─────────────┬────────────┘   └────────────────────────────────┘  │
│                                            │                                                    │
│                     ┌──────────────────────┴──────────────────────┐                             │
│                     │                                             │                             │
│                     ▼                                             ▼                             │
│  ┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐          │
│  │          AI SUBSYSTEM (app/ai)      │       │    DETERMINISTIC CORE (app/core)    │          │
│  │  * MockAI / LLMProvider             │       │  * Pure Python, zero DB/AI imports  │          │
│  │  * Guardrails & Prompt Isolation    │       │  * DAG Dependency Resolver (DAG)    │          │
│  │  * Prohibited Claim Sanitizer       │       │  * Topological Planner & Simulator  │          │
│  │  * Advisory ONLY - never writes DB  │       │  * deterministic_check() & CheckToken│         │
│  └─────────────────────────────────────┘       └──────────────────┬──────────────────┘          │
│                                                                   │                             │
│                                                                   ▼                             │
│  ┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐          │
│  │     EVIDENCE PIPELINE (evidence/)   │       │      REPOSITORIES (app/db/repos)    │          │
│  │  * PyMuPDF PDF Text Extraction      │       │  * SnapshotRepository (Token-Gated) │          │
│  │  * Indian Financial Regex Extractor │       │  * AuditWriter (Append-Only)        │          │
│  │  * SHA-256 Content Hashing          │       │  * IdempotencyRepository            │          │
│  └─────────────────────────────────────┘       └──────────────────┬──────────────────┘          │
└───────────────────────────────────────────────────────────────────┼─────────────────────────────┘
                                                                    │
                                                                    ▼
                                       ┌───────────────────────────────────────────────┐
                                       │            POSTGRESQL 16 DATABASE             │
                                       │  * 8 Core Relational Tables                   │
                                       │  * DB-level Immutability Triggers             │
                                       │  * Non-forking Snapshot Chain Constraints     │
                                       └───────────────────────────────────────────────┘
```

---

## 2. Frontend Architecture Diagram

```
                                  ┌─────────────────────────┐
                                  │       main.tsx          │
                                  └────────────┬────────────┘
                                               │
                                  ┌────────────▼────────────┐
                                  │      providers.tsx      │
                                  │  QueryClient & Fallback │
                                  └────────────┬────────────┘
                                               │
                                  ┌────────────▼────────────┐
                                  │       router.tsx        │
                                  │  AppShell + 10 Routes   │
                                  └────────────┬────────────┘
                                               │
       ┌───────────────────────────────┬───────┴───────────────────────┬───────────────────────────────┐
       │                               │                               │                               │
       ▼                               ▼                               ▼                               ▼
┌──────────────┐               ┌──────────────┐                ┌──────────────┐                ┌──────────────┐
│   SCREENS    │               │  COMPONENTS  │                │  API HOOKS   │                │   STATE &    │
│ Screen01Home │               │ AppShell     │                │ useJourney   │                │   STORAGE    │
│ Screen02Packs│               │ ProgressRing │                │ usePacks     │                │ React Query  │
│ Screen03Goal │               │ BlockerCard  │                │ useApplyAct  │                │ Zustand UI   │
│ Screen04Stat │               │ RecCard      │                │ useEvidence  │                │ Cookies      │
│ Screen05Rec  │               │ Dropzone     │                │ (Types.gen)  │                │ (No LocalSt) │
│ Screen06Act  │               │ JourneyDiff  │                └──────────────┘                └──────────────┘
│ Screen07AI   │               │ NeedsReview  │
│ Screen08Upd  │               │ SchemaForm   │
│ Screen09Done │               └──────────────┘
│ Screen10List │
└──────────────┘
```

---

## 3. Backend Architecture Diagram

```
 backend/app/
 ├── api/v1/          <-- Presentation (FastAPI REST Routes)
 │   ├── system.py        [GET /health, GET /session]
 │   ├── packs.py         [GET /journey-packs, GET /journey-packs/{type}]
 │   ├── journeys.py      [POST /journeys, GET /journeys/{id}, GET /journeys]
 │   ├── recommendation.py[GET /journeys/{id}/recommendation]
 │   ├── evidence.py      [POST /journeys/{id}/evidence]
 │   ├── actions.py       [POST /journeys/{id}/actions] (THE Mutation Seam)
 │   ├── clarifications.py[POST /journeys/{id}/clarifications]
 │   └── diff.py          [GET /journeys/{id}/diff]
 ├── services/        <-- Application Orchestration
 │   └── journey_service.py (Coordinates Core + AI + DB)
 ├── core/            <-- Pure Deterministic Business Logic (NO I/O)
 │   ├── models.py        (CoreSnapshot, CoreFieldState, CheckToken)
 │   ├── dependencies.py  (DAG Validation & Topological Sort)
 │   ├── rules.py         (Fixpoint Status Resolution)
 │   ├── simulate.py      (Pure Consequence Simulator)
 │   ├── planner.py       (Shortest Recovery Path Engine)
 │   ├── readiness.py     (Deterministic Readiness Evaluator)
 │   ├── diff.py          (State Diff Engine)
 │   └── deterministic_check.py (The Mutation Choke Point)
 ├── ai/              <-- Isolated Advisory Layer
 │   ├── provider.py      (AIProvider Protocol)
 │   ├── mock.py          (MockAI - Default High-Fidelity Engine)
 │   ├── llm.py           (OpenAI-Compatible LLM Adapter)
 │   └── guardrails.py    (Injection Boundary & Banned Claim Filter)
 ├── evidence/        <-- Document Processing Pipeline
 │   ├── extract.py       (PyMuPDF Text & Regex Financial Parser)
 │   ├── reconcile.py     (Target Mapping & Conflict Heuristics)
 │   └── storage.py       (SHA-256 Hashed File Storage)
 └── db/              <-- Persistence Layer
     ├── models.py        (SQLAlchemy 2 Declarative Models)
     ├── session.py       (Async Session Maker)
     └── repositories/    (Snapshots, Journeys, Evidence, Audit, Idempotency)
```

---

## 4. Database Schema & Entity Relationships

```
┌────────────────────────────────┐                 ┌──────────────────────────────────────────────┐
│            sessions            │                 │                   journeys                   │
├────────────────────────────────┤                 ├──────────────────────────────────────────────┤
│ PK  id               UUID      │1               N│ PK  id                   UUID                │
│     created_at       TIMESTAMPT│────────────────<│ FK  session_id           UUID                │
│     expires_at       TIMESTAMPT│                 │     journey_type         VARCHAR(50)         │
│     meta             JSONB     │                 │     schema_version       VARCHAR(20)         │
└────────────────────────────────┘                 │     status               VARCHAR(50)         │
                                                   │     readiness            VARCHAR(50)         │
                                                   │ FK  current_snapshot_id  UUID                │
                                                   │     goal                 JSONB               │
                                                   │     display_title        VARCHAR(200)        │
                                                   │     display_summary      VARCHAR(500)        │
                                                   │     created_at           TIMESTAMPTZ         │
                                                   │     updated_at           TIMESTAMPTZ         │
                                                   └──────────────────────┬───────────────────────┘
                                                                          │
                    ┌───────────────────────────────┬─────────────────────┼───────────────────────────────┐
                    │ 1:N                           │ 1:N                 │ 1:N                           │ 1:N
                    ▼                               ▼                     ▼                               ▼
┌───────────────────────────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────────────────────┐
│           journey_snapshots           │ │     evidence      │ │  clarifications   │ │            audit_events           │
├───────────────────────────────────────┤ ├───────────────────┤ ├───────────────────┤ ├───────────────────────────────────┤
│ PK  id                   UUID         │ │ PK  id        UUID│ │ PK  id        UUID│ │ PK  id             UUID           │
│ FK  journey_id           UUID         │ │ FK  journey_idUUID│ │ FK  journey_idUUID│ │ FK  journey_id     UUID           │
│     version_number       INTEGER      │ │     doc_type  STR │ │     ambiguity_idST│ │ FK  session_id     UUID (Nullable)│
│ FK  previous_snapshot_id UUID         │ │     filename  STR │ │     field_key STR │ │     event_type     VARCHAR(100)   │
│     readiness            VARCHAR(50)  │ │     file_path STR │ │     question  TEXT│ │     payload        JSONB          │
│     fields               JSONB        │ │     sha256    STR │ │     answer_typeSTR│ │     created_at     TIMESTAMPTZ    │
│     goal                 JSONB        │ │     file_size INT │ │     user_resp JSON│ └───────────────────────────────────┘
│     pending_clarificationJSONB        │ │     mime_type STR │ │     resolved_atTS │
│     created_at           TIMESTAMPTZ  │ │     ext_text  TEXT│ │     created_at TS │
└───────────────────────────────────────┘ │     ext_data  JSON│ └───────────────────┘
                                          │     confidenceFLT │
                                          │     created_at TS │
                                          └───────────────────┘
```

---

## 5. End-to-End Sequence Diagrams

### A. App Boot & Session Minting Sequence

```
User (Browser)               Frontend (boot.ts)            FastAPI (/api/v1/session)           PostgreSQL (sessions)
      │                               │                                 │                                │
      │────── Open App ──────────────>│                                 │                                │
      │                               │── GET /api/v1/session ─────────>│                                │
      │                               │   (credentials: include)        │                                │
      │                               │                                 │── Inspect pf_session cookie ───│
      │                               │                                 │   [Cookie Absent or Invalid]   │
      │                               │                                 │── Mint session_id (UUIDv4) ────│
      │                               │                                 │── INSERT INTO sessions ───────>│
      │                               │                                 │<── Commit OK ──────────────────│
      │                               │<── 200 OK ──────────────────────│                                │
      │                               │    Set-Cookie: pf_session=...;  │                                │
      │                               │    Body: { session_id, created }│                                │
      │                               │                                 │                                │
      │                               │── QueryClient Prefetch ────────>│                                │
      │<───── Render Screen 1 ────────│                                 │                                │
```

### B. Evidence Upload & Preview Sequence (Zero Mutation)

```
User (Screen 6)             Frontend (Dropzone)          FastAPI (/evidence)           PyMuPDF & AI Provider       PostgreSQL (evidence)
      │                              │                            │                            │                            │
      │── Drop salary_slip.pdf ─────>│                            │                            │                            │
      │                              │── POST /evidence ─────────>│                            │                            │
      │                              │   (multipart: file,        │                            │                            │
      │                              │    expected_snapshot_id)   │                            │                            │
      │                              │                            │── SHA256 & Store Disk ─────│                            │
      │                              │                            │── Extract PDF Text ───────>│                            │
      │                              │                            │<── Return Parsed Text ─────│                            │
      │                              │                            │── Reconcile & Guardrails ─>│                            │
      │                              │                            │<── Verified: true, ₹85,000─│                            │
      │                              │                            │── Simulate (Pure Core) ────│ (No DB State Change)       │
      │                              │                            │── INSERT INTO evidence ────────────────────────────────>│
      │                              │<── 200 EvidenceResponse ───│                                                         │
      │                              │    (preview_diff, summary) │                                                         │
      │<── Show Preview (Screen 7) ──│                            │                                                         │
```

### C. State Mutation & Snapshot Transition Sequence

```
User (Screen 7)             Frontend (useApplyAction)     FastAPI (/actions)            Deterministic Core          PostgreSQL (Snapshots)
      │                              │                            │                            │                            │
      │── Click Continue ───────────>│                            │                            │                            │
      │                              │── POST /actions ──────────>│                            │                            │
      │                              │   (action_id, expected_id, │                            │                            │
      │                              │    idempotency_key)        │                            │                            │
      │                              │                            │── Check Idempotency Cache ─│───────────────────────────>│
      │                              │                            │<── Cache Miss (Proceed) ───│                            │
      │                              │                            │── deterministic_check() ──>│                            │
      │                              │                            │    * Snapshot freshness    │                            │
      │                              │                            │    * Preconditions         │                            │
      │                              │                            │    * Input validation      │                            │
      │                              │                            │<── Mint CheckToken ────────│                            │
      │                              │                            │                                                         │
      │                              │                            │── BEGIN TRANSACTION ───────────────────────────────────>│
      │                              │                            │── INSERT INTO journey_snapshots (vN+1) ────────────────>│
      │                              │                            │── INSERT INTO audit_events ────────────────────────────>│
      │                              │                            │── INSERT INTO idempotency_keys ────────────────────────>│
      │                              │                            │── COMMIT TRANSACTION ──────────────────────────────────>│
      │                              │<── 200 ActionResponse ─────│                                                         │
      │<── Render Screen 8 (Diff) ───│                            │                                                         │
```

---

## 6. Journey State Machine

```
                                      ┌────────────────────────────────┐
                                      │           [START]              │
                                      │ User Selects Pack (Screen 2)   │
                                      └───────────────┬────────────────┘
                                                      │
                                                      │ POST /api/v1/journeys
                                                      ▼
                                      ┌────────────────────────────────┐
                                      │           NOT_READY            │
                                      │ Snapshot v1 Created (3/7 Comp) │
                                      └───────┬───────────────▲────────┘
                                              │               │
                        POST /evidence (Doc Mismatch)         │ POST /clarifications
                                              │               │ (Ambiguity Answered)
                                              ▼               │
                                      ┌───────────────────────┴────────┐
                                      │         NEEDS_REVIEW           │
                                      │ Pending Clarification Triggered│
                                      └───────┬────────────────────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │ All Mandatory Satisfied                           │ Hard Regulatory Block
                    ▼                                                   ▼
     ┌─────────────────────────────┐                     ┌─────────────────────────────┐
     │            READY            │                     │          DEAD_END           │
     │ Screen 9: Handoff Ready     │                     │ Terminal State (Recovery UX)│
     └─────────────────────────────┘                     └─────────────────────────────┘
```

---

## 7. Route Map Table

| Route | Screen Name | Component | Primary Hook / Query | Key Parameters | Transitions To | Special Routing Rules |
|---|---|---|---|---|---|---|
| `/` | Home & Landing | [`Screen01Home`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen01Home.tsx) | `useJourneyList()` | None | `/start`, `/j/:id` | Displays resume card if active journeys exist in session. |
| `/start` | Journey Selection | [`Screen02JourneySelection`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen02JourneySelection.tsx) | `usePacks()` | None | `/start/:type` | Renders 6 pack cards with Flagship badge on `LENDING`. |
| `/start/:type` | Goal & Basic Info | [`Screen03GoalBasicInfo`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen03GoalBasicInfo.tsx) | `usePack(type)`, `useCreateJourney()` | `type` (JourneyType) | `/j/:id` | Renders dynamic `<SchemaForm />` from `goal_schema`. |
| `/j/:id` | Current Status | [`Screen04CurrentStatus`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen04CurrentStatus.tsx) | `useJourney(id)` | `id` (Journey UUID) | `/j/:id/next`, `/j/:id/complete` | Automatically redirects to `/j/:id/complete` if `readiness == READY`. |
| `/j/:id/next` | Recommendation | [`Screen05Recommendation`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen05Recommendation.tsx) | `useRecommendation(id)` | `id` (Journey UUID) | `/j/:id/act/:actionId` | Highlights top topological candidate action + alternatives. |
| `/j/:id/act/:actionId` | Provide Input / Evidence | [`Screen06UploadEvidence`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen06UploadEvidence.tsx) | `useUploadEvidence()`, `useApplyAction()` | `id`, `actionId` | `/j/:id/analysis`, `/j/:id/updated` | Renders dropzone for `EVIDENCE`; renders dynamic form for `FORM`. |
| `/j/:id/analysis` | AI Analysis & Preview | [`Screen07AiAnalysis`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen07AiAnalysis.tsx) | Route State (`EvidenceResponse`) | `id` (Journey UUID) | `/j/:id/updated` | Renders deterministic `consequence_preview` & diff. |
| `/j/:id/updated` | Updated Status & Diff | [`Screen08UpdatedStatus`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen08UpdatedStatus.tsx) | Route State (`ActionResponse`) | `id` (Journey UUID) | `/j/:id`, `/j/:id/complete` | Shows committed diff and updated progress ring. |
| `/j/:id/complete` | Complete Journey | [`Screen09CompleteJourney`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen09CompleteJourney.tsx) | `useJourney(id)` | `id` (Journey UUID) | `/my-journeys` | Route guard: redirects back to `/j/:id` if not `READY`. |
| `/my-journeys` | My Journeys Dashboard | [`Screen10MyJourneys`](file:///d:/Projects/PatymFlow/PaytmFlow/frontend/src/screens/Screen10MyJourneys.tsx) | `useJourneyList()` | Tab query param | Direct Resume Route | Obeys server-supplied `resume_screen` on resume action. |

---

## 8. API Endpoints Table

| Method | Path | OperationId | Mutates? | Auth / Security | Request Payload | Response Schema |
|---|---|---|---|---|---|---|
| `GET` | `/api/v1/health` | `getHealth` | No | None | None | `{ status, db, packs_loaded, ai_provider }` |
| `GET` | `/api/v1/session` | `getSession` | No (Issues cookie) | Cookie / Header | None | `{ session_id, created }` |
| `GET` | `/api/v1/journey-packs` | `listJourneyPacks` | No | `sessionCookie` | None | `{ packs: JourneyPackSummary[] }` |
| `GET` | `/api/v1/journey-packs/{journey_type}` | `getJourneyPack` | No | `sessionCookie` | Path param | `JourneyPackDetail` |
| `GET` | `/api/v1/journeys` | `listJourneys` | No | `sessionCookie` | Query: `status, type, limit` | `{ journeys: JourneyListItem[] }` |
| `POST` | `/api/v1/journeys` | `createJourney` | **Yes (Creates v1)** | `sessionCookie` | `{ journey_type, goal, natural_language? }` | `JourneyStateResponse` |
| `GET` | `/api/v1/journeys/{journey_id}` | `getJourney` | No | `sessionCookie` | Path param | `JourneyStateResponse` |
| `GET` | `/api/v1/journeys/{journey_id}/recommendation` | `getRecommendation` | No | `sessionCookie` | Path param | `RecommendationResponse` |
| `POST` | `/api/v1/journeys/{journey_id}/evidence` | `uploadEvidence` | **No (Preview Only)** | `sessionCookie` | Multipart: `file, doc_type, expected_snapshot_id` | `EvidenceResponse` |
| `POST` | `/api/v1/journeys/{journey_id}/actions` | `applyAction` | **Yes (Sole Mutation)** | `sessionCookie` | `{ action_id, expected_snapshot_id, idempotency_key, input }` | `ActionResponse` |
| `POST` | `/api/v1/journeys/{journey_id}/clarifications` | `submitClarification` | **Yes (Disambiguates)** | `sessionCookie` | `{ ambiguity_id, field, answer, expected_snapshot_id }` | `ActionResponse` |
| `GET` | `/api/v1/journeys/{journey_id}/diff` | `getDiff` | No | `sessionCookie` | Query: `from, to` | `JourneyDiff` |
| `POST` | `/api/v1/demo/reset` | `resetDemo` | **Yes (Wipes DB)** | `X-Demo-Secret` | None | `{ reset, elapsed_ms }` |

---

## 9. Contract-to-Implementation Traceability

```
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│   OpenAPI Schema   │────>│  Generated TS Type │────>│ Frontend Component │────>│  Backend Model /   │
│ (contract/openapi) │     │  (src/api/types)   │     │ (src/components/..)│     │     Repository     │
└────────────────────┘     └────────────────────┘     └────────────────────┘     └────────────────────┘
```

| Canonical Contract Schema | Generated TypeScript Interface | Backend Core / Pydantic Model | Frontend Consuming Component | Fixture Test Reference |
|---|---|---|---|---|
| `JourneyStateResponse` | `components['schemas']['JourneyStateResponse']` | `app.schemas.journeys.JourneyStateResponse` | `Screen04CurrentStatus`, `useJourney` | `contract/fixtures/lending/v1.state.json` |
| `JourneyPackDetail` | `components['schemas']['JourneyPackDetail']` | `app.schemas.packs.JourneyPackDetail` | `Screen03GoalBasicInfo`, `SchemaForm` | `contract/fixtures/packs.LENDING.json` |
| `ActionOption` | `components['schemas']['ActionOption']` | `app.schemas.journeys.ActionOption` | `RecommendationCard`, `ActionList` | `contract/fixtures/lending/v1.recommendation.json` |
| `SimulationPreview` | `components['schemas']['SimulationPreview']` | `app.core.models.CoreSimulationResult` | `Screen07AiAnalysis`, `ConsequencePreview`| `contract/fixtures/lending/evidence.salary_slip.json` |
| `JourneyDiff` | `components['schemas']['JourneyDiff']` | `app.core.models.CoreJourneyDiff` | `JourneyDiff.tsx` (Screen 7 & Screen 8) | `contract/fixtures/lending/v2.action.json` |
| `EvidenceResponse` | `components['schemas']['EvidenceResponse']` | `app.schemas.evidence.EvidenceResponse` | `Screen06UploadEvidence`, `Screen07` | `contract/fixtures/lending/evidence.salary_slip.json` |
| `FieldState` | `components['schemas']['FieldState']` | `app.core.models.CoreFieldState` | `BlockerCard.tsx`, `StatusBadge.tsx` | `contract/fixtures/lending/v1.state.json` |
| `ProgressCounts` | `components['schemas']['ProgressCounts']` | `app.core.models.CoreProgressCounts` | `ProgressRing.tsx` | `contract/fixtures/lending/v1.state.json` |
| `Readiness` (Enum) | `components['schemas']['Readiness']` | `app.core.models.CoreReadiness` | `StatusBadge.tsx`, `AppShell.tsx` | `contract/fixtures/lending/v5.ready.json` |

---

## 10. Complete Error Matrix

| HTTP Status | Error Code | Error Message Definition | Root Cause / Trigger | Frontend Mapping & Reaction |
|---|---|---|---|---|
| `400` | `VALIDATION_ERROR` | `"Required input field 'X' is missing"` | Input does not conform to `GoalFieldSpec` or number out of bounds | Inline field errors rendered on `<SchemaForm />`; retains typed inputs. |
| `400` | `INVALID_JOURNEY_TYPE`| `"Journey type 'XYZ' is not supported"` | Path parameter does not match registered 6 packs | Displays ErrorState card and routes user back to Screen 2. |
| `404` | `NOT_FOUND` | `"Journey not found"` | Unknown journey ID or cross-session access attempt | "This journey is not available"; routes user to `/my-journeys`. |
| `409` | `ACTION_STALE` | `"The journey state has changed since this action was requested"` | `expected_snapshot_id != current_snapshot_id` | Amber banner shown; queries invalidated; **no blind action retry**. |
| `413` | `PAYLOAD_TOO_LARGE` | `"That file is over 10MB"` | Uploaded file size exceeds `10,485,760` bytes | Dropzone remains active; inline message shown; prevents network transmission. |
| `422` | `ACTION_INVALID` | `"Action precondition 'X' is not satisfied"` | Action invoked out of topological order or unlisted | Disables action CTA; re-fetches recommendation; displays alert toast. |
| `500` | `INTERNAL_ERROR` | `"An unexpected error occurred"` | Unhandled server exception | Exponential backoff retry once; displays `<ErrorState />` with Retry button. |

---

## 11. Testing & Validation Matrix

| Test Domain | Framework | File Path | Tests Count | Validation Scope |
|---|---|---|---|---|
| **Contract Schemas** | pytest | `backend/tests/contract/test_openapi_matches.py` | 2 | Asserts FastAPI auto-generated OpenAPI matches committed `openapi.yaml`. |
| **Fixture Integrity**| pytest | `backend/tests/contract/test_fixtures_match_schema.py` | 36 | Validates every JSON fixture file against OpenAPI JSON schemas. |
| **Deterministic Invariants** | pytest | `backend/tests/unit/test_invariants.py` | 27 | Proves 100 runs of simulation produce byte-identical results; no AI in core. |
| **DAG & Topo Planner**| pytest | `backend/tests/unit/test_planner.py` | 6 | Tests topological ordering and cycle rejection across all manifests. |
| **Prompt Injection** | pytest | `backend/tests/safety/test_prompt_injection.py` | 15 | Verifies `<untrusted_document>` boundary tags isolate adversarial prompts. |
| **Scenario Runner** | pytest | `backend/tests/scenarios/test_scenarios.py` | 37 | Runs 6 scenario families across all 6 journey packs. |
| **Frontend Primitives**| Vitest | `frontend/src/components/primitives/primitives.test.tsx`| 12 | Tests Button, Input, MoneyInput, Badge, Modal, and Tabs focusability. |
| **Dynamic Schema Form**| Vitest | `frontend/src/components/SchemaForm/SchemaForm.test.tsx` | 18 | Validates runtime Zod compilation from dynamic schema specs. |
| **Claim Safety Scan**| Vitest | `frontend/tests/unit/claim-safety.test.tsx` | 10 | Scans all rendered UI strings for banned words (`approved`, `guaranteed`). |
| **Idempotency Client**| Vitest | `frontend/tests/unit/idempotency.test.tsx` | 8 | Asserts single UUID generated per click; duplicate clicks reuse UUID. |
| **E2E Golden Path** | Playwright | `frontend/tests/e2e/golden-path.spec.ts` | 6 | Complete headless browser walk through Screens 1 to 9 against MSW. |

---

## 12. Environment Configuration Reference

### Backend (`backend/.env`)
```ini
DATABASE_URL=postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow
APP_ENV=local                    # local | ci | demo
SESSION_COOKIE_NAME=pf_session
SESSION_SECRET=change-me-32-bytes-minimum-session-secret-key-1234
SESSION_TTL_DAYS=30
CORS_ORIGINS=http://localhost:5173
AI_PROVIDER=mock                 # mock | llm (mock is default and demo setting)
AI_TIMEOUT_SECONDS=4
AI_API_KEY=                      # Required only if AI_PROVIDER=llm
AI_MODEL=gpt-4o-mini
EVIDENCE_STORAGE_DIR=./storage/evidence
EVIDENCE_MAX_BYTES=10485760      # 10 MB (Matches UI 10MB copy)
DEMO_RESET_SECRET=change-me-demo-secret
LOG_LEVEL=INFO
```

### Frontend (`frontend/.env`)
```ini
VITE_API_MODE=mock               # mock | live
VITE_API_BASE=/api/v1
VITE_SHOW_DEV_BADGES=true        # Set false for production demo
```

---

## 13. Related Documents
- [Complete Project Guide & Master Document](file:///d:/Projects/PatymFlow/PaytmFlow/docs/PAYTMFLOW_COMPLETE_PROJECT_GUIDE.md)
- [Developer & Operations Playbook](file:///d:/Projects/PatymFlow/PaytmFlow/docs/PAYTMFLOW_DEVELOPER_PLAYBOOK.md)
- [Shared Development Contract](file:///d:/Projects/PatymFlow/PaytmFlow/00_SHARED_CONTRACT.md)
- [Canonical OpenAPI Specification](file:///d:/Projects/PatymFlow/PaytmFlow/contract/openapi.yaml)
