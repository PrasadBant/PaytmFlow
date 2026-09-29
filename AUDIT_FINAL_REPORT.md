# PaytmFlow: Final Deployment-Readiness Audit

**Audit dates:** 2026-09-29 to 2026-09-30 · **Base commit:** `6fb559e` (branch `main`, remote `origin` = github.com/PrasadBant/PaytmFlow)
**Environment:** Windows 11, Python 3.13.12, Node 24.15, PostgreSQL 16 (`postgres:16-alpine` container on :5433), Tesseract available.

This report supersedes `AUDIT_PROGRESS.md`. That earlier report overstated its evidence (§A.0). Every result below comes from a command run during this audit. Passing tests do not prove the absence of bugs. The limits of this audit are listed in §G and §H.

---

## A. Verified findings

### A.0 Corrections to the previous audit

| Previous claim | Verified reality |
|---|---|
| "371 unit tests, all passing" | 371 was a line count of `pytest --co -q` output. The actual unit suite is **369 tests**, all passing. |
| "660 backend tests passing" | Quoted from the README, never reproduced. The actual full suite is **697 tests** (673 existing + 24 new), all passing on PostgreSQL. |
| "All phases complete", "Safe to deploy" | Integration, frontend and authorization testing had not been run. This audit found **4 High and 1 Medium** security defects that the earlier report missed. |
| Commit `6fb559e` | Created without the user asking for a commit. The change itself is correct (§A.1). |
| Untracked `backend/demo_recommendations`, `state.json` | Neither path exists. See §F. |

### A.1 Commit `6fb559e` (assertions in `app/ai/mock.py::_diff_reply`)
Correct. The preceding `readiness_changed` guard already requires `from_` and `to` to be truthy, and `Readiness` members are non-empty strings, so the assertions restate an existing invariant for mypy and hide no invalid state.

### A.2 Verified sound
- **Journey isolation:** a static route map (§D) shows every `/journeys/{journey_id}/*` route depends on `verify_journey_ownership`, which returns 404 for journeys owned by another session.
- **Reviewer endpoints:** all 10 `/review/cases*` and `/review/dashboard` routes depend on `verify_reviewer`. A new test confirms all 10 return 403 for an ungranted session.
- **Snapshot immutability (PostgreSQL):** verified directly on a migrated scratch database. `UPDATE` and `DELETE` on `journey_snapshots` fail with `immutable table: journey_snapshots`, and a duplicate `(journey_id, version_number)` fails on `uq_snapshots_journey_version`.
- **Migrations:** `alembic upgrade head` → `downgrade base` → `upgrade head` on a fresh PostgreSQL database succeeds and ends at `005_evidence_provider (head)`, with triggers `no_update_audit` and `no_update_snapshots` present.
- **Upload handling:** magic-byte allow-list (PDF/JPEG/PNG), a 10 MB limit, and stored filename = sha256 + allow-listed extension. The client filename never reaches the path.
- **Evidence ownership:** `apply_action` requires `evidence.journey_id == journey.id`. The existing tests cover cross-journey, cross-session, unknown, malformed and mismatched evidence, and forged values.
- **n8n:** outbound only; there is no inbound webhook, so HMAC and replay verification don't apply to this repo. Events are queued in memory and flushed **only after `db.commit()`** at all 6 call sites. Dispatch errors are logged and swallowed, and the secret is never logged. There is no retry: a failed notification is lost (logged only).
- **Sarvam fallback:** each failure path logs and falls back to the local pipeline, and the provider used is stored per evidence row.

---

## B. Confirmed defects

| ID | Severity | Status | Summary |
|---|---|---|---|
| D1 | **High** (critical for any real deployment) | Fixed, verified | Any anonymous session could make itself REVIEW_OFFICER and read or mutate every customer's review cases |
| D2 | **High** | Fixed, verified | EVIDENCE actions without `evidence_id` took client-supplied values, bypassing Document AI and verification |
| D3 | Medium | Fixed, verified | Idempotency replay not scoped to session, journey or payload |
| D6 | **High** | Fixed, verified | Client-supplied `ambiguity_id` alongside verified evidence forced the field AMBIGUOUS, opening a clarification route around the verified value |
| D7 | **High** | Fixed, verified | `POST /clarifications` accepted answers for ambiguities that were not open, so any ambiguity-rule field (e.g. `monthly_income`) could be set to any value without evidence |
| D4 | Low | Open | `ruff format --check` fails on 7 pre-existing files |
| D5 | Info | Open (not a code defect) | Untracked `backend/demo_state.json` holds a live signed session cookie |
| D8 | Low | Open | `npm run test:e2e` fails by default because the tracked `frontend/.env` sets `VITE_API_MODE=live`. The suite needs mock mode |

"Verified" means a regression test fails with the fix disabled and passes with it restored, run against PostgreSQL with `REQUIRE_POSTGRES=1`.

### D1: Reviewer self-promotion
- **Before:** `POST /review/role` wrote any requested role into the caller's session. `verify_reviewer` trusted that role, and `/review/cases` has no ownership scope, so any visitor could list all cases, read other customers' evidence filenames and extracted values (income, names, ID numbers), and resolve, escalate or request information on their journeys.
- **Fix (`app/security/reviewer.py`, `app/api/v1/review.py`, `app/config.py`, `app/schemas/review.py`):**
  - New `REVIEWER_ACCESS_CODE` setting. Promotion requires it, compared with `secrets.compare_digest`.
  - Outside `local`/`ci`, promotion **fails closed** when no code is configured. Downgrading to CUSTOMER is always allowed.
  - The role is bound to `reviewer_grant` = HMAC-SHA256(`SESSION_SECRET`, code). `verify_reviewer` rejects sessions promoted before this fix and sessions promoted under a rotated code.
  - Contract (`contract/openapi.yaml`) and generated frontend types are updated. `Header.tsx` prompts for the code.
- **Tests:** `tests/integration/test_reviewer_role_authorization.py` (14): missing, wrong, malformed (int, list, object, >256 chars) and valid codes; fail-closed with no configured code; downgrade; per-session isolation; client role headers ignored; pre-fix grant not honoured; rotation revokes; all 10 reviewer endpoints return 403 for an ungranted session. **With the fix disabled, 5 of these fail.**
- **Remaining limitation:** a shared code is not staff identity. Everyone holding it is a reviewer, attributed as `Reviewer-<session prefix>`.

### D2: Evidence bypass via action input
- **Before:** `deterministic_check` fills EVIDENCE fields without `evidence_id` from `action_input`, then `simulation_defaults`, then a bare `True`. For example, `{"action_id":"UPLOAD_INCOME_PROOF","input":{"monthly_income":999999}}` marked income proof SATISFIED with no document.
- **Fix (`app/services/journey_service.py`, service layer; the pure core is untouched):** EVIDENCE actions without `evidence_id` return 422 `ACTION_INVALID` unless `ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE` is true. It defaults to true only in `local`/`ci`, where existing fixture tests rely on it. The real frontend always sends `evidence_id` for EVIDENCE actions (`Screen07AiAnalysis.tsx`). FORM actions are unaffected.
- **Tests:** `test_evidence_required_for_evidence_actions.py`: rejected with the gate closed and no snapshot written; FORM action unaffected; gate closed by default outside local/ci.
- **Limitation:** most existing integration tests run with the gate open (`ci`). Gate rejections are not written to the audit log.

### D3: Unscoped idempotency replay
- **Before:** any stored key returned its cached `ActionResponse` whatever the caller's session, journey or payload. That leaks another session's journey state to anyone presenting its key, and silently returns stale results when a key is reused with a different payload.
- **Fix:** replay requires a matching `session_id`, `journey_id` and request hash. A mismatch returns 400 `VALIDATION_ERROR` with no cached content.
- **Tests:** `test_idempotency_scoping.py` (4): same-request replay still works; cross-session rejected with no leakage; same key with a different payload rejected; same key on another journey of the same session rejected. **With the fix disabled, 3 fail.**
- **Note:** exploiting this needed the victim's client-generated UUID key, so real-world likelihood was low. Two concurrent identical requests are serialized by the journey row lock. The second then gets 409 `ACTION_STALE` rather than the replayed response, which is safe but not ideal.

### D6: Forged ambiguity alongside verified evidence
- **Before:** `apply_action` honoured any manifest `ambiguity_id` sent by the client. Evidence with a real conflict is stored `verified=false` and is already rejected, so the only way to reach this path with real evidence was with verified, conflict-free evidence. That made it useful only for forging a clarification.
- **Fix:** 422 `ACTION_INVALID` when `ambiguity_id` accompanies a resolved `evidence_id`.
- **Test:** `test_evidence_action_integrity.py::test_client_asserted_ambiguity_with_verified_evidence_rejected` (uses real OCR on a generated salary slip).

### D7: Clarification for ambiguities that are not open
- **Found while testing D6.** With D6 fixed, the same test showed `POST /clarifications {"ambiguity_id":"INCOME_MISMATCH","field":"monthly_income","answer":999999999}` succeeding on a journey where the field was merely BLOCKED. It set income to ₹99,99,99,999 SATISFIED with no evidence at all.
- **Fix:** `submit_clarification` now requires the ambiguity to be open on the current snapshot: it must be the `pending_clarification`, or an AMBIGUOUS field carrying the same `ambiguity_id`. Otherwise it returns 422 `ACTION_INVALID`. The reviewer resolution path, which calls the same method, is unchanged: all 50 review, n8n and reviewer tests pass.
- **Tests:** two tests in `test_evidence_required_for_evidence_actions.py` (no open ambiguity; a different ambiguity open) plus the D6 test. **With the fix disabled, all 3 fail.**

---

## C. Test commands and results

| # | Check | Command | Result | Status |
|---|---|---|---|---|
| 1 | New security regression tests | `REQUIRE_POSTGRES=1 uv run pytest <24 new tests>` | 24 passed. With fixes disabled: D1/D2/D3 9 failed, D6/D7 3 failed | PASS |
| 2 | Full backend suite, PostgreSQL | `REQUIRE_POSTGRES=1 uv run pytest -q` | **697 passed**, 0 failed, 0 skipped (404.8 s) | PASS |
| 2a | by suite | `pytest tests/<dir> --co` | unit 369 · integration 220 · contract 38 · safety 15 · packs 18 · scenarios 37 | n/a |
| 3 | Review/n8n suites after final HMAC change | `pytest test_reviewer_role_authorization test_review_cases test_review_adversarial test_review_ai_summary test_n8n_notifications` | 50 passed | PASS |
| 4 | Migrations round-trip | `alembic upgrade head / downgrade base / upgrade head` (scratch DB, dropped afterwards) | succeeded, head `005_evidence_provider` | PASS |
| 5 | PostgreSQL trigger and uniqueness enforcement | manual SQL on scratch DB | UPDATE and DELETE rejected; duplicate version rejected | PASS |
| 6 | Ruff lint | `uv run ruff check app tests` | All checks passed | PASS |
| 7 | Ruff format | `uv run ruff format --check app tests` | 7 pre-existing files would be reformatted; all changed files formatted | FAIL (pre-existing, D4) |
| 8 | mypy (whole app) | `uv run mypy app` | 41 errors in 15 files (see §E) | FAIL (pre-existing, stubs only) |
| 9 | mypy strict (engine) | `uv run mypy --strict app/core` | no issues in 10 files | PASS |
| 10 | Import boundary | `uv run lint-imports` | 1 kept, 0 broken | PASS |
| 11 | Frontend typecheck | `npm run typecheck` | exit 0 | PASS |
| 12 | Frontend lint | `npm run lint` (max-warnings 0) | exit 0 | PASS |
| 13 | Frontend unit tests | `npx vitest run` | 48 files, **417 passed** | PASS |
| 14 | Frontend build | `npm run build` | built; chunk-size warning | PASS |
| 15 | Frontend E2E | `VITE_API_MODE=mock npx playwright test` | **52 passed** (baseline on unmodified HEAD, via a temporary worktree: 52 passed) | PASS |
| 16 | Python dependency scan | `uvx pip-audit -r <uv export --no-dev> --no-deps --disable-pip` | No known vulnerabilities | PASS |
| 17 | npm dependency scan (prod) | `npm audit --omit=dev` | 2 moderate: `react-router` / `react-router-dom` < 7.18 | FAIL (accepted, see §D) |
| 18 | npm dependency scan (all) | `npm audit` | 7 (5 moderate, 1 high `vite`, 1 critical `vitest`), dev tooling only | Informational |

## D. Security status

| Item | Status |
|---|---|
| D1 reviewer self-promotion | **Fixed and verified.** Requires `REVIEWER_ACCESS_CODE` in deployed environments. |
| D2 evidence bypass | **Fixed and verified.** Requires `APP_ENV` ≠ local/ci in deployment (§H). |
| D3 idempotency isolation | **Fixed and verified.** |
| D6 forged ambiguity | **Fixed and verified.** |
| D7 clarification without open ambiguity | **Fixed and verified.** |
| `react-router` moderate advisories | **Accepted risk, not fixed.** The open-redirect advisory needs attacker-controlled URLs passed to `<Link>`/`navigate`, and a search found none (only `?tab=` and `?scenario=` are read, never navigated to). The SSR advisory doesn't apply to this SPA. The fix is a breaking v7 upgrade. |
| `vite` / `vitest` advisories | Dev server and test tooling only; not in the production bundle. Upgrade when convenient. |
| n8n notification loss | No retry. Notifications can't corrupt committed state (flushed after commit), but a failed one is lost. |
| Reviewer identity | Shared-code prototype, not staff authentication. |
| Unauthenticated AI endpoints | `POST /chat` and `POST /translate` need only a session and have no rate limiting (cost/abuse risk; not tested). |

## E. mypy

`uv run mypy app`: **41 errors in 15 files, unchanged by this audit.** Every error is `import-untyped` or `import-not-found` (missing stubs or packages); none is a type error in project logic.

| Location | Errors | Imported by runtime code? |
|---|---|---|
| `app/docai/bench_*.py` (5 files) | 12 | No: grep finds no import from outside the offline scripts |
| `app/docai/dataset/generate*.py` (7 files) | 21 | No |
| `app/docai/train_classifier.py` | 6 | No |
| `app/docai/classifier.py` (joblib) | 1 | **Yes**, via `app/ai/local_ml.py` and `app/evidence/reconcile.py` |
| `app/docai/ocr.py` (pytesseract) | 1 | **Yes** |

Impact: the 2 runtime entries mean calls into joblib and pytesseract are typed as `Any`, so mypy doesn't check them. They aren't logic errors, and both modules are exercised by the 697-test suite.

## F. Untracked and modified files

| Path | Status | Action |
|---|---|---|
| `backend/demo_state.json` | Untracked, not ignored, 164 bytes | **Not committed.** Contains a journey ID and a signed `pf_session` cookie, which is a bearer credential for that session. Delete when no longer needed. If it came from the live deployment, rotating `SESSION_SECRET` invalidates it. |
| `AUDIT_PROGRESS.md` | Untracked | Rewritten as a short pointer to this report. Not committed. |
| `frontend/.env`, `frontend/.env.production` | Tracked | Only public `VITE_*` values, no secrets. |
| `backend/.env` | Ignored | Not read. |

## G. Verification status summary

| Area | Status |
|---|---|
| Security regression tests (D1, D2, D3, D6, D7) | PASS |
| Backend unit / integration / contract / safety / packs / scenarios (PostgreSQL) | PASS |
| Migrations and PostgreSQL immutability | PASS |
| Frontend unit, lint, typecheck, build | PASS |
| Frontend E2E (MSW mocks) | PASS |
| Ruff format | FAIL (pre-existing) |
| mypy whole app | FAIL (pre-existing, stubs only) |
| Dependency scans | Python PASS; npm prod FAIL (2 moderate, accepted) |
| True concurrent-request tests (parallel HTTP against PostgreSQL) | **NOT RUN.** Existing suites cover row locking and stale-snapshot rejection sequentially only. |
| E2E against a real backend (live mode) | **NOT RUN.** The Playwright suite runs against MSW mocks only. |
| Frontend access-code prompt in a real browser | **NOT RUN.** Typechecked and linted only; E2E doesn't open the role switch. |
| Live deployment (Render/Vercel) configuration | **BLOCKED.** No access to the dashboards; `REVIEWER_ACCESS_CODE` and `APP_ENV` can't be verified from the repo. |
| n8n and Sarvam live integration | **NOT RUN.** Mocked tests only. |

## H. Deployment decision

**Not ready to deploy until the configuration below is in place. The code fixes are verified.**

Required before deploying this commit:
1. **Set `REVIEWER_ACCESS_CODE`** on the backend host to a long random value, and share it only with reviewers. Without it, the Review Center refuses everyone, which is safe but breaks the reviewer demo.
2. **Confirm `APP_ENV` is not `local` or `ci`** in production (the entrypoint suggests `demo`). If it were `local`/`ci`, the D1 and D2 gates would be open and the `X-Session-Id` bypass enabled.
3. **Leave `ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE` unset** (or false) in production.
4. Accept that reviewer sessions promoted before this deploy lose access and need to re-enter the code. That is intended.

Recommended before treating this as production (not a demo):
- Run concurrent-request tests against PostgreSQL (parallel `apply_action` and review claim/resolve).
- Run the E2E suite in live mode against a staging backend, including the reviewer flow.
- Replace the shared reviewer code with real staff authentication.
- Add rate limiting to `/chat`, `/translate` and the voice endpoint.
- Add retry or a dead-letter record for n8n dispatch failures.
- Plan the `react-router` v7 and `vite`/`vitest` upgrades.

## I. Changed files

| File | Purpose |
|---|---|
| `backend/app/security/reviewer.py` | D1: access-code check, HMAC-bound reviewer grant, grant check in `verify_reviewer` |
| `backend/app/api/v1/review.py` | D1: enforce `authorize_role_switch` |
| `backend/app/schemas/review.py` | D1: optional `access_code` (max 256) |
| `backend/app/config.py` | `REVIEWER_ACCESS_CODE`, `ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE` |
| `backend/.env.example` | Documents `REVIEWER_ACCESS_CODE` |
| `backend/app/services/journey_service.py` | D2 evidence gate, D3 idempotency scoping, D6 forged-ambiguity rejection, D7 open-ambiguity check |
| `backend/tests/integration/test_reviewer_role_authorization.py` | New, 14 tests |
| `backend/tests/integration/test_idempotency_scoping.py` | New, 4 tests |
| `backend/tests/integration/test_evidence_required_for_evidence_actions.py` | New, 5 tests |
| `backend/tests/integration/test_evidence_action_integrity.py` | +1 test (D6/D7) |
| `contract/openapi.yaml` | `access_code` field and 403 response on `/review/role` |
| `frontend/src/api/types.gen.ts` | Regenerated from the contract |
| `frontend/src/api/hooks/useReview.ts` | Role switch sends `access_code` |
| `frontend/src/components/Header.tsx` | Prompts for the reviewer access code |
| `README.md` | New settings, updated reviewer limitation, verified test table |
| `AUDIT_FINAL_REPORT.md` | This report |
