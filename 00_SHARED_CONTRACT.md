# PaytmFlow — Shared Contract (Dev1 ↔ Dev2)

**Authority:** the v4.2 canonical spec pack outranks this document. This document outranks anything either developer decides alone. If you need to break a rule here, use the change protocol in §9.

**Read this before writing any code. Both of you. Together. It takes 25 minutes and it is the single highest-leverage thing in the build.**

---

## 0. Scope reality for a two-person team

Be honest with yourselves before you start.

| | Value |
|---|---|
| Estimated work, full canonical scope | ~176 person-hours |
| Two devs × 40 productive hours in a 48h event | ~80 person-hours |
| Agentic multiplier (realistic: high on UI/CRUD/tests, low on engine design) | ~1.4× → ~112 effective |

**You are still ~1.5× over.** Agents make you faster at typing, not at deciding. The deterministic core, the pack dependency designs and the frontend↔backend seam are decision work, and agents help least there.

**Cuts agreed before T+0 — non-negotiable, do not relitigate at 3am:**

1. **No evaluation arms.** Ship the scenario runner (EVAL-001) and per-pack pass/fail. No A/B/C/D ablation, no comparative report. Present "six packs, 6 scenario families each, all passing" instead.
2. **No OCR.** PDF text extraction via PyMuPDF plus the "Enter Details" tab. Image uploads resolve through a fixture map. Say so out loud in the demo.
3. **Three packs get polished copy** (Lending, Insurance, KYC); three ship at contract floor with generic labels (Credit Card, Account Opening, Investment). All six still pass the Deep Journey Contract.
4. **No login.** Anonymous sessions only — this is a canonical non-goal, not a shortcut.

That lands at ~115 effective hours. Checkpoints in §10 tell you what to cut next if you slip.

---

## 1. Ownership boundary

| Domain | Owner | The other person's rule |
|---|---|---|
| Everything under `frontend/` | **Dev1** | Dev2 never edits it |
| Everything under `backend/` | **Dev2** | Dev1 never edits it |
| `contract/openapi.yaml` | **Dev2 writes, Dev1 reviews** | Changes need the §9 protocol |
| `contract/fixtures/*.json` | **Dev2 generates, both consume** | Dev1's MSW mocks are built from these |
| `frontend/src/api/types.gen.ts` | **Generated** | Nobody hand-edits. Ever. |
| `docker-compose.yml`, `Makefile` | **Dev2** | Dev1 raises issues, doesn't patch |
| `docs/` (the v4.2 pack) | **Read-only for both** | |

The boundary means: **Dev1 can finish the entire frontend without the backend existing, and Dev2 can finish the entire backend without the frontend existing.** That property is worth defending. Every time you're tempted to "just quickly add a field", you're spending it.

---

## 2. Ports, URLs and processes

| Process | Port | Command |
|---|---|---|
| Frontend dev server (Vite) | **5173** | `cd frontend && npm run dev` |
| Backend API (uvicorn) | **8000** | `make api` or `cd backend && uv run uvicorn app.main:app --reload --port 8000` |
| PostgreSQL | **5432** | `docker compose up -d postgres` |
| Playwright report | 9323 | `npx playwright show-report` |

**Vite proxies `/api` → `http://localhost:8000`** (configured in `vite.config.ts`). The frontend therefore always calls same-origin relative paths (`/api/v1/...`) and never a hardcoded host. This makes cookies work in dev without CORS gymnastics and makes the production deploy identical.

Dev1's app must run with `VITE_API_MODE=mock` and never touch port 8000 at all. That's the independence guarantee.

---

## 3. Environment variables

`backend/.env` (Dev2 owns; commit `.env.example`, never `.env`):

```bash
DATABASE_URL=postgresql+psycopg://paytmflow:paytmflow@localhost:5432/paytmflow
APP_ENV=local                    # local | ci | demo
SESSION_COOKIE_NAME=pf_session
SESSION_SECRET=change-me-32-bytes-minimum
SESSION_TTL_DAYS=30
CORS_ORIGINS=http://localhost:5173
AI_PROVIDER=mock                 # mock | llm      <-- mock is the DEFAULT and the demo setting
AI_TIMEOUT_SECONDS=4
AI_API_KEY=                      # empty unless AI_PROVIDER=llm. Never sent to the client.
AI_MODEL=
EVIDENCE_STORAGE_DIR=./storage/evidence
EVIDENCE_MAX_BYTES=10485760      # 10 MB — must match the UI copy "Max 10MB"
DEMO_RESET_SECRET=change-me
LOG_LEVEL=INFO
```

`frontend/.env` (Dev1 owns):

```bash
VITE_API_MODE=mock               # mock | live
VITE_API_BASE=/api/v1
VITE_SHOW_DEV_BADGES=true        # shows recommendation.source etc. MUST be false for the demo build
```

**Rule:** no secret ever appears in a `VITE_` variable. Vite inlines those into the bundle.

---

## 4. Authentication and session flow

The canonical spec lists login as a non-goal. Authentication here means **anonymous session ownership**, and it is a real module, not a stub.

```
Browser boot
   │
   ├─ GET /api/v1/session
   │     ├─ no pf_session cookie  → server mints an opaque signed session_id,
   │     │                          sets HttpOnly / SameSite=Lax / Secure / Path=/ / Max-Age=30d
   │     └─ cookie present + signature valid → returns the same session_id
   │
   └─ every subsequent request carries the cookie automatically (fetch credentials: 'include')

Server, on every journey read or write:
   journey.session_id == request.session_id ?
     yes → proceed
     no  → 404 NOT_FOUND      (never 403 — a 403 leaks that the journey exists)
```

**Dev1 contract:** call `GET /api/v1/session` once on app boot, before any other request, and set `credentials: 'include'` on every fetch. Do not store the session id in localStorage — you don't need it, and the cookie is HttpOnly by design.

**Dev2 contract:** cookie is signed with `SESSION_SECRET` (itsdangerous or equivalent). Reject tampered cookies by minting a fresh session rather than erroring. `Secure` is set only when `APP_ENV != local`, otherwise localhost dev breaks.

**CI / eval bypass:** the scenario runner and Playwright can pass `X-Session-Id` instead of a cookie, accepted **only** when `APP_ENV in (local, ci)`. This is guarded by an explicit test asserting the header is ignored when `APP_ENV=demo`.

---

## 5. The API contract

`contract/openapi.yaml` is the contract. It is OpenAPI 3.1, it parses, and it covers 12 paths and 19 schemas.

**Endpoints, and which screen each one drives:**

| Method | Path | Screen | Mutates? |
|---|---|---|---|
| GET | `/api/v1/health` | — | no |
| GET | `/api/v1/session` | boot | no |
| GET | `/api/v1/journey-packs` | 2 Journey Selection | no |
| GET | `/api/v1/journey-packs/{type}` | 3 Goal & Basic Info | no |
| POST | `/api/v1/journeys` | 3 → 4 | **yes** (creates v1) |
| GET | `/api/v1/journeys` | 10 My Journeys | no |
| GET | `/api/v1/journeys/{id}` | 4 Current Status | no |
| GET | `/api/v1/journeys/{id}/recommendation` | 5 Recommendation | no |
| POST | `/api/v1/journeys/{id}/evidence` | 6 → 7 | **no** — preview only |
| POST | `/api/v1/journeys/{id}/actions` | 7 → 8 | **yes** — the only mutation |
| POST | `/api/v1/journeys/{id}/clarifications` | Needs Review | **yes** |
| GET | `/api/v1/journeys/{id}/diff` | 7, 8 | no |
| POST | `/api/v1/demo/reset` | — | yes (wipes) |

**The two properties Dev1 must internalise:**

1. **Uploading evidence changes nothing.** `POST /evidence` returns an interpretation and a *predicted* consequence. State only changes when the user hits Continue on Screen 7, which fires `POST /actions`.
2. **Every mutating request carries `expected_snapshot_id`.** If it doesn't match the server's current snapshot, you get `409 ACTION_STALE` with the real `current_snapshot_id` in `error.details`. Refetch, show a banner, do not retry blindly.

### 5.1 Error handling matrix — Dev1 implements exactly this

| HTTP | code | Dev1 behaviour |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Inline field errors from `error.details`; preserve all typed input |
| 400 | `INVALID_JOURNEY_TYPE` | Route to Screen 2 with an ErrorState |
| 404 | any | "This journey isn't available." → Screen 10 |
| 409 | `ACTION_STALE` | Amber banner "This journey has moved on — refreshing", invalidate queries, refetch, re-render. **No retry of the action.** |
| 422 | `ACTION_INVALID` | ErrorState card, refetch recommendation, do not re-enable the button until fresh data lands |
| 200 | body `requires_review: true` | Render `NeedsReviewCard`, hide Continue |
| 200 | `readiness: DEAD_END` | Render DeadEndState with the pack's recovery copy. No crash, no blank screen. |
| 413 | — | "That file is over 10MB." Keep the dropzone active. |
| 5xx / network | — | Retry once with backoff, then ErrorState with a Retry button |

`error.message` from the server is always safe to render directly. It is written for end users, never a stack trace.

---

## 6. Shared data model — the six things both sides must agree on

These are the concepts that appear on both sides of the wire. Full JSON Schema lives in `contract/openapi.yaml`; this is the mental model.

**1. `FieldState`** — one row of journey state. `{ key, label, status, value, display_value, explanation, resolve_action_id, mandatory, ambiguity? }`. Dev1 renders blocker cards from the entries where `status != SATISFIED`.

**2. `ProgressCounts`** — `{ completed, pending, blockers, total }`. Renders as `3/7 Completed`. **Never** as a percentage, gauge, dial, or anything with the word "score". This is the single most dangerous element in the UI and both of you own it.

**3. `ActionOption`** — `{ action_id, title, kind, why, unlocks[], accepts[]?, input_schema[]? }`. `kind` tells Dev1 which UI to open: `EVIDENCE` → Screen 6, `FORM` → generic action modal rendered from `input_schema`, `CLARIFICATION` → NeedsReviewCard. **Dev1 never hardcodes an action_id.** Everything is driven off `kind` and `input_schema`, which is what makes one UI serve all six journeys.

**4. `SimulationPreview`** — `{ newly_satisfied[], newly_unlocked[], still_blocked[], predicted_readiness, progress_before, progress_after }`. Screen 7's "Expected Outcome" list renders **this object**, not `interpretation.summary`. The AI writes the sentence; the engine writes the outcome. If Dev1 ever renders a consequence from AI text, the core product claim is broken.

**5. `JourneyDiff`** — same shape whether it's a preview (Screen 7) or actual (Screen 8). One `<JourneyDiff/>` component, two data sources.

**6. `Readiness`** — `READY | NOT_READY | NEEDS_REVIEW | DEAD_END`. Four states, four UI treatments, no fifth.

### 6.1 Field ordering and labels are the server's job

`fields[]` arrives pre-ordered for display, pre-labelled, and pre-formatted (`display_value: "₹85,000"`). Dev1 renders in array order and does not sort, relabel, or currency-format. This is what lets Insurance and KYC reuse Screen 4 with zero frontend changes.

---

## 7. Fixtures — the artefact that makes independence real

Dev2's **first deliverable**, due T+3, before any engine code:

```
contract/fixtures/
├── session.json
├── packs.list.json                  # GET /journey-packs — all six
├── packs.LENDING.json               # GET /journey-packs/LENDING
├── packs.INSURANCE.json ... ×6
├── lending/
│   ├── v1.state.json                # after POST /journeys — 3/7, three blockers
│   ├── v1.recommendation.json       # UPLOAD_INCOME_PROOF + 3 alternatives
│   ├── evidence.salary_slip.json    # verified, ₹85,000, preview + diff
│   ├── v2.action.json               # ActionResponse: state 4/7 + diff + next rec
│   ├── v3.recommendation.json
│   ├── evidence.bank_statement.json # requires_review: true, INCOME_MISMATCH
│   ├── v4.clarification.json
│   ├── v5.ready.json                # readiness READY, 7/7
│   ├── error.stale.json
│   ├── error.invalid.json
│   └── error.deadend.json
├── insurance/  credit_card/  kyc/  account_opening/  investment/
│   └── (v1.state, v1.recommendation, ready — three files each, enough for the selector demo)
└── journeys.list.json               # Screen 10, six rows, mixed statuses
```

Rules:
- Hand-written by Dev2 (with an agent) against the OpenAPI schema, **before** the code that would produce them.
- Validated in CI: `pytest tests/contract/test_fixtures_match_schema.py` asserts every fixture validates against its schema. This catches drift the moment it happens.
- Once the real endpoints exist, a `make refresh-fixtures` target regenerates them from live responses. Diffs in that command's output are exactly the contract drift Dev1 needs to know about.

Dev1 builds the entire frontend against these. **Dev1's Playwright suite runs green against fixtures before the backend exists.**

---

## 8. Git workflow

**Single repo, two top-level directories.** A monorepo is right here: one contract, one CI, one `docker compose up`, and no submodule pain.

```
main                    protected, always green, always demoable
├── fe/<slug>           Dev1 branches   (fe/screen-04-status)
├── be/<slug>           Dev2 branches   (be/deterministic-check)
└── contract/<slug>     either, but requires both approvals
```

Rules:

1. **Small PRs, merged often.** Target: every branch merges within 4 hours of being cut. A two-person team does not need long-lived branches and will not survive a merge conflict in hour 40.
2. **Nobody reviews the other's internals.** Dev1 approves Dev2's PRs on contract impact only, and vice versa. Reading each other's implementation is a waste of the little time you have.
3. **`contract/` changes need both approvals and a Slack/voice ping.** Not because of ceremony — because the other person's mocks silently go stale otherwise.
4. **CI must be green to merge.** Job runs: backend lint+type+test, frontend lint+type+test, fixture-schema validation, Playwright-against-mocks.
5. **Conventional commits** (`feat(fe):`, `fix(be):`, `chore(contract):`). Agents write good conventional commits if you tell them to in `CLAUDE.md`.
6. **Tag `demo-freeze` at T+42.** Deploy that exact tag. No commits to `main` afterwards. If something is broken at T+42, you demo around it.

**Merge conflicts should be near-zero** because the directory ownership is strict. If you're getting conflicts, someone crossed the boundary.

---

## 9. Contract change protocol

The contract is frozen at **T+3**. After that, changing it costs both of you time, so the protocol is deliberately slightly annoying.

**Additive change** (new optional field, new enum value, new endpoint):
1. Whoever needs it opens a `contract/` PR editing `openapi.yaml` **and** the affected fixtures in the same commit.
2. Ping the other person. Not async — actually tell them.
3. Merge. Dev1 runs `make types`. Done.

**Breaking change** (renamed field, changed type, removed field, changed semantics):
1. Stop. 90% of the time you can do it additively — add the new field, deprecate the old one in a comment, remove it after the demo.
2. If genuinely necessary: both developers stop feature work, make the change together in one sitting, update contract + fixtures + both sides, and merge as one PR.

**Never:** change a response shape in backend code without updating `openapi.yaml` in the same PR. This is the failure that will cost you four hours at hour 40. A CI job compares FastAPI's generated OpenAPI against the committed file and fails on drift.

---

## 10. Integration schedule and checkpoints

Both of you work against mocks/fixtures until **T+26**. That is deliberate. Integrating early feels productive and isn't — you'll spend the time debugging half-built things on both sides.

| Time | Event | Who |
|---|---|---|
| T+0 → T+3 | **Contract freeze session.** Read spec together, finalise `openapi.yaml`, agree fixtures list | both |
| T+3 | Dev2 publishes fixtures. Dev1 runs `make types` and builds MSW handlers | both |
| T+3 → T+26 | Fully independent build | both |
| **T+26** | **Integration Point 1: Lending golden.** Dev1 flips `VITE_API_MODE=live`. Walk Screens 1→9 against the real backend, together, in one sitting | both |
| T+26 → T+34 | Fix the seam. Then back to independent work | both |
| **T+34** | **Integration Point 2: six packs + Needs Review + stale + resume** | both |
| T+34 → T+42 | Polish, visual QA, tests | both |
| **T+42** | **Freeze.** Tag, deploy, rehearse, record backup video | both |

### Checkpoint cuts

**T+26 — if Lending golden doesn't complete end to end against the real API:**
Cut to three packs (Lending, Insurance, KYC). Show the other three in the selector as validated manifests with a "configured" badge. This is honest and still demonstrates the generic engine.

**T+34 — if six packs aren't loading and passing scenarios:**
Cut scenario families to four (GOLDEN, AMBIGUITY_CONFLICT, INVALID_ACTION, STALE_ACTION) for non-flagship packs. Keep all six for Lending.

**T+42 — freeze regardless of state.**
A working demo of a smaller thing beats a broken demo of a bigger thing. Every time.

---

## 11. Integration rules (the ones that prevent rework)

1. **Dev1 never invents a field.** If the UI needs data the contract doesn't have, that's a contract PR, not a client-side derivation. The one exception: nothing. Even the progress ring comes from `progress`.
2. **Dev2 never returns a field the UI can't use.** Every response field maps to something on a screen or is diagnostic and clearly named.
3. **Server formats, client renders.** Currency, dates, labels, ordering, and the resume screen are all server decisions.
4. **The server never sends HTML.** All strings are plain text. Dev1 renders them as text nodes. `dangerouslySetInnerHTML` is banned by lint rule, because AI-written `summary` strings flow to the screen.
5. **Journey-specific behaviour lives in pack manifests, not in either codebase.** If Dev1 writes `if (journeyType === 'INSURANCE')`, that's a bug. If Dev2 writes it in engine code, that's a worse bug.
6. **Idempotency:** every `POST /actions` carries a client-generated `idempotency_key` UUID. Replaying the same key returns the original response instead of double-applying. Dev1 generates it once per user click, not per retry.
7. **The AI never reaches the client.** No AI key, no model name, no prompt, ever crosses the wire.

---

## 12. Joint definition of done

The build is done when all of these are true. Check them together, out loud, at T+42.

- [ ] `docker compose up` + `npm run dev` gives a working app on a clean machine
- [ ] All 10 screens reachable and matching the reference image
- [ ] Lending golden: Screens 1→9 with real snapshots, ending at `READY`
- [ ] Evidence upload → deterministic preview → apply → diff → recompute
- [ ] Conflicting evidence → `NEEDS_REVIEW` → exactly one question → resolved
- [ ] Stale action returns 409 and creates **zero** snapshots (verify `version_number`)
- [ ] Invalid action returns 422 and creates **zero** snapshots
- [ ] All six packs load, validate, and appear in the selector
- [ ] Screen 10 lists journeys and resumes to the correct screen
- [ ] No occurrence of: approved, approval, probability, credit score, eligibility score, readiness score, guaranteed — in any user-visible string, verified by an automated test on both sides
- [ ] `POST /demo/reset` restores a clean demo in one call
- [ ] Backup video recorded; local run verified on a second machine
