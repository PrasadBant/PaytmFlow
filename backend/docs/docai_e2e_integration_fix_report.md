# PaytmFlow — Document AI Integration Integrity Fix

## 1. Root Cause

Traced precisely, not guessed (Part 1):

1. `POST /journeys/{id}/evidence` → `EvidenceReconciliationService.submit_evidence`
   (`app/evidence/reconcile.py`) runs the real OCR → classification → extraction →
   normalization → consistency pipeline, computes `is_verified` (AI-verified AND confidence ≥
   manifest threshold AND no conflicts), and persists an `EvidenceModel` row
   (`app/db/models.py`) — **before this fix, that row stored the file, `extracted_text`,
   `extracted_data`, and `confidence`, but NEVER the verification decision or the AI's real
   `raw_values`.** The wire response (`EvidenceResponse`) DOES carry `interpretation.verified`/
   `detected`, but that response is never looked at again once returned.
2. `POST /journeys/{id}/actions` → `JourneyService.apply_action`
   (`app/services/journey_service.py`) → `deterministic_check()`
   (`app/core/deterministic_check.py`) — the sole mutation choke point. Its `new_values`
   computation read ONLY the client-supplied `action_input` dict. Since the real frontend
   (`Screen07AiAnalysis.tsx`) sends `input: {"evidence_id": evidenceResponse.evidence_id}` —
   nothing else — no `action_spec.satisfies` field key was ever present in `action_input`, so
   execution always fell through to `manifest.simulation_defaults[field]` (money/text fields)
   or a bare `True` (boolean fields), **regardless of what document was uploaded, what the AI
   determined, or whether any evidence was uploaded at all.**

The bug existed because the evidence-upload step computed a real, honest verification decision
but never persisted it anywhere durable, and the action-execution step had no way to retrieve
it even if it had wanted to — the two request/response cycles were completely disconnected.

## 2. Fix

The smallest generic architectural fix, in three parts:

1. **Persist the real result** (`app/db/models.py`, `app/db/repositories/evidence.py`,
   `app/evidence/reconcile.py`): `EvidenceModel` gained two columns — `verified: bool` and
   `raw_values: JSON`. `verified` is set from a NEW, narrower boolean,
   `evidence_is_genuine = ai_res.verified and not has_conflicts` — deliberately NOT the fuller
   `is_verified` used for the upload response, because `is_verified` additionally requires
   confidence ≥ the manifest threshold, which the confidence-audit phase already measured is
   systematically NOT cleared by genuinely correct documents in 5 of 6 journeys (a separate,
   explicitly-deferred calibration problem this task's own instructions forbid touching).
   Gating action execution on that same uncalibrated number would have made real evidence
   actions unable to succeed for most journeys — see §3.
2. **Resolve it server-side at action-execution time** (`app/services/journey_service.py`):
   before calling `deterministic_check`, `apply_action` now looks up
   `action_input["evidence_id"]` against the `evidence` table (a real DB query — this cannot
   happen inside `app/core`, which must stay pure per CLAUDE.md rule 1), confirms the row
   belongs to the current journey (cross-journey/cross-session safety), and builds a small,
   frozen `ResolvedEvidence(doc_type, verified, values)` record.
3. **Consume ONLY the resolved record for EVIDENCE actions**
   (`app/core/deterministic_check.py`): a new, still-pure function parameter,
   `resolved_evidence: ResolvedEvidence | None`. When present and the action is `kind ==
   EVIDENCE`: the evidence's doc_type must be in the action's own `accepts` list, and
   `resolved_evidence.verified` must be `True` — otherwise the check raises
   `DeterministicCheckError(code=EVIDENCE_CONFLICT)` (422, reusing an ErrorCode already reserved
   in the frozen contract but never previously used). When both hold, `new_values` for that
   action's `satisfies` fields come EXCLUSIVELY from `resolved_evidence.values` — never
   `action_input`, never `simulation_defaults`, never a bare `True`. FORM/CLARIFICATION actions,
   and any EVIDENCE action executed with no `evidence_id` at all, are completely untouched —
   identical behavior to before.

No API contract change was needed: `POST /actions` still accepts exactly
`{action_id, expected_snapshot_id, idempotency_key, input}`, and `input: {"evidence_id": ...}`
remains the only thing the frontend needs to send (already the case — confirmed by reading
`Screen07AiAnalysis.tsx`, unchanged this phase). `EVIDENCE_CONFLICT` was already a declared
`ErrorCode` in `contract/openapi.yaml`, simply never used until now.

## 3. Before vs After

**WRONG DOCUMENT** (`tests/integration/test_docai_e2e_journeys.py::
test_wrong_document_does_not_advance_lending_state`, the exact scenario from the E2E phase):

| | Before | After |
|---|---|---|
| Evidence upload | `verified=False`, `detected=[]` | Unchanged |
| Action execution (`{"evidence_id": ...}` only) | **HTTP 200**, `monthly_income = 85000` (simulation_defaults) | **HTTP 422**, `EVIDENCE_CONFLICT` — no snapshot created, `monthly_income` stays `null` |
| Same, boolean field (Credit Card `income_verified`) | **HTTP 200**, `income_verified = True` | **HTTP 422**, `EVIDENCE_CONFLICT`, field stays unsatisfied |

**VALID DOCUMENT** (`test_lending_e2e_real_evidence_advances_state`, deliberately using a real
income figure, ₹208,000, that does NOT coincidentally match `simulation_defaults`' ₹85,000):

| | Before | After |
|---|---|---|
| Evidence upload | `verified` per confidence threshold (often `False` even when correct — a separate, known issue); `detected` includes the real `monthly_income` | Unchanged |
| Action execution | HTTP 200, but `monthly_income` set to the FIXED `85000` regardless of the document | HTTP 200, `monthly_income` set to the REAL extracted `208000` — proven by the test asserting `income_field["value"] == fields["net_amt"]` and `!= 85000` |

## 4. Evidence Trust Boundary

Stated exactly, per field:

| Source | Trusted for state mutation? | Where |
|---|---|---|
| Client-supplied `evidence_id` | Trusted only as a REFERENCE (a lookup key) — never as a value carrier | `action_input.get("evidence_id")` |
| Client-supplied direct field values (e.g. `{"monthly_income": 999999}` sent alongside `evidence_id`) | **Never trusted** — ignored entirely once `resolved_evidence` is present for an EVIDENCE action | Proven by `test_client_forged_field_value_is_ignored` |
| Client-supplied `verified`/`detected` claims | **Never trusted** — the server re-derives everything from its own persisted `evidence.verified`/`raw_values` | Same test |
| Persisted `evidence.verified`/`raw_values` | **Trusted** — this IS the source of truth for EVIDENCE-action mutation | `ResolvedEvidence`, built server-side only |
| Document AI's `AIInterpretationResult` | Trusted, but ONLY at the moment `reconcile.py` computes and persists `evidence_is_genuine`/`raw_values` — never re-consulted live at action-execution time (no second AI call) | `app/evidence/reconcile.py` |
| Deterministic engine (`deterministic_check`) | **Sole authority** for whether a mutation is allowed to happen at all | `app/core/deterministic_check.py` |

AI remains advisory throughout: it never writes a snapshot, never mints a `CheckToken`, and its
output only ever reaches state through the ONE gate (`deterministic_check`) that also enforces
doc_type/action compatibility and the genuineness check.

## 5. Simulation Defaults Audit

Every production call site, found by repository-wide search (Part 10):

| Call site | Real evidence execution? | FORM action? | Reachable from a real failed evidence action? |
|---|---|---|---|
| `app/core/deterministic_check.py` line ~258 (`elif s in manifest.simulation_defaults`) | **No, not anymore** — only reached when `resolved_evidence` is `None`, i.e. no real `evidence_id` was resolved for an EVIDENCE-kind action | N/A (also the fallback for FORM/CLARIFICATION actions with no matching `action_input` key) | **No** — a real evidence_id, once resolved and found NOT verified, raises `EVIDENCE_CONFLICT` before this line is ever reached |
| `app/core/simulate.py` line 54 (`defaults = manifest.simulation_defaults or {}`) | No — this is `simulate()`, which powers the evidence-upload response's `consequence_preview`/`SimulationPreview` ONLY. It never creates a snapshot, never calls `deterministic_check`, and is explicitly a non-mutating PREVIEW shown before any action is executed. Legitimate, unchanged. | N/A | No — no mutation path runs through this function at all |
| 6 manifest YAML files' `simulation_defaults:` sections | Data only (declares the constants both functions above may read) | — | — |

**Guarantee now holds**: a REAL FAILED evidence action (wrong document, unverified, or
doc_type/action mismatch) can never reach the `simulation_defaults` fallback — it is rejected
with `EVIDENCE_CONFLICT` before `new_values` computation is ever attempted for that field.
`simulate()`'s own use of `simulation_defaults` remains a preview-only mechanism, never wired
to a real mutation, and was not touched.

## 6. Six-Journey Verification

| Journey | Evidence Integration | Wrong Doc Safe | Valid Doc Works |
|---|---|---|---|
| LENDING | ✅ `UPLOAD_INCOME_PROOF` resolves real evidence, sets real `monthly_income` | ✅ `test_wrong_document_does_not_advance_lending_state` | ✅ `test_lending_e2e_real_evidence_advances_state` (real ₹208,000, not ₹85,000) |
| INSURANCE | ✅ `submit_ped_records` (after `submit_medical_declaration` precondition) resolves real evidence | Covered by the shared, journey-agnostic fix (no journey-specific code) | ✅ `test_insurance_e2e_real_evidence_advances_state` |
| KYC | ✅ resolves real evidence for the OVD upload action | Covered by the shared fix | ✅ `test_kyc_e2e_real_evidence_advances_state` |
| CREDIT_CARD | ✅ `upload_salary_statement` resolves real evidence | ✅ `test_wrong_document_does_not_set_boolean_field_true_on_execution` | ✅ `test_credit_card_e2e_real_evidence_advances_state` |
| ACCOUNT_OPENING | ✅ `upload_wet_signature` (after `verify_pan_for_banking` precondition) resolves real evidence | Covered by the shared fix | ✅ `test_account_opening_e2e_real_evidence_advances_state` |
| INVESTMENT | ✅ `upload_cancelled_cheque` resolves real evidence | Covered by the shared fix | ✅ `test_investment_e2e_real_evidence_advances_state` |

The fix is 100% generic — `app/core/deterministic_check.py` and `app/services/journey_service.py`
contain zero `if journey_type == ...` branches; every journey above is exercised through the
identical shared code path. No journey has ONLY FORM actions (all six have at least one
EVIDENCE-kind action).

## 7. Security Tests

All in `tests/integration/test_evidence_action_integrity.py` (new, 10 tests) plus 2 in
`test_docai_e2e_journeys.py`:

| Case | Result |
|---|---|
| Cross-journey evidence (Journey A's evidence used on Journey B, same session) | **404** |
| Cross-session evidence (Session A's evidence used by Session B) | **404** |
| Unknown `evidence_id` | **404** |
| Malformed (non-UUID) `evidence_id` | **404** |
| Evidence/action mismatch (real, verified `SALARY_SLIP` evidence used for `UPLOAD_WORK_ID`, which only accepts `OFFICE_ID_CARD`) | **422 EVIDENCE_CONFLICT** |
| Client-forged field value (`{"evidence_id": "<real>", "monthly_income": 999999999, "verified": true}`) | **200**, but the forged value is discarded — the real, server-resolved `monthly_income` is what gets persisted |
| Wrong document (money field) | **422 EVIDENCE_CONFLICT**, no fabricated value |
| Wrong document (boolean field) | **422 EVIDENCE_CONFLICT**, field stays unsatisfied |
| Idempotency (identical `idempotency_key` submitted twice) | Both calls return the SAME response; snapshot version advances exactly once |
| Stale snapshot | **409** (unchanged) |
| Invalid action | **422** (unchanged) |
| FORM action with no `evidence_id` | Unaffected — still consumes `action_input` directly |

## 8. Regression

| Journey | Classification (unseen_template) | Extraction (unseen_template key fields) | Changed? |
|---|---|---|---|
| LENDING | 0.9412 | monthly_income 0.875, employer_name 1.0 | **No** |
| INSURANCE | 1.0000 | name 0.9167, date 0.9722 | **No** |
| KYC | 0.9744 | name 0.9444, date 0.9444, identifier 0.8056 | **No** |
| CREDIT_CARD | 1.0000 | name 0.9444, date 1.0, income 1.0, identifier 0.75 | **No** |
| ACCOUNT_OPENING | 0.9744 | name 0.5833, identifier 0.9167, date 1.0 | **No** |
| INVESTMENT | 1.0000 | name 0.9722, identifier 0.8889, date 0.9583 | **No** |

Every number matches the E2E + performance phase's own report exactly. This fix touches only
`app/core/deterministic_check.py`, `app/services/journey_service.py`,
`app/db/models.py`/`app/db/repositories/evidence.py`, and `app/evidence/reconcile.py` — none of
which sit on the OCR/classification/extraction/normalization code path.

## 9. Tests

- **Full backend pytest** (dedicated `paytmflow_test` DB, `REQUIRE_POSTGRES=1`): **459/459
  passed** (449 at the start of this phase → **+10 net new**: 10 in the new
  `test_evidence_action_integrity.py`; the pre-existing `test_docai_e2e_journeys.py` file was
  edited in place — 2 tests rewritten to assert the FIXED behavior instead of documenting the
  bug, 1 test strengthened to prove the real value is consumed — net 0 new tests there, 0
  deleted, 0 weakened).
- **ruff check app tests**: clean.
- **mypy --strict app/core**: clean, 9 files (the new `ResolvedEvidence` dataclass type-checks
  cleanly; `app/core` remains free of any `app.db`/`app.ai`/`app.api`/`app.services`/
  `app.evidence` import).
- **lint-imports**: 1/1 kept, 0 broken.
- **Six-journey classification/extraction**: re-run, all matching (§8).
- **Frontend**: not run — zero frontend files changed; `Screen07AiAnalysis.tsx`'s existing
  `input: {evidence_id}` call shape required no change (confirmed by reading the source; this
  was precisely the shape the fix was designed to keep compatible with).

## 10. Remaining Limitations

Honest, not hidden:

- **The confidence-threshold-vs-genuine-correctness gap remains** (deliberately, per this
  task's explicit instructions not to touch it): `evidence.verified` (used by this fix) is
  intentionally more permissive than `EvidenceInterpretation.verified` (the upload-response
  field, still confidence-threshold-gated). This means a document that the UI might show as
  "needs review" immediately after upload (because composed confidence sits below the manifest
  threshold — the confidence-calibration phase's own well-documented finding) can now still
  successfully satisfy its target field once the corresponding action is executed, AS LONG AS
  the AI genuinely classified it correctly and found no conflict. This is a deliberate,
  disclosed scope boundary of THIS fix (which is about wrong-document fabrication, not about
  the separate confidence-calibration question), not an oversight — but it does mean the
  review-vs-proceed signal shown at upload time and the actual executability of the action can
  diverge. Revisiting this boundary is explicitly reserved for the future confidence-calibration
  phase.
- **A migration was required** (`alembic/versions/002_evidence_verification_result.py`) and was
  applied to the dev Postgres database (`paytmflow`) as part of this fix, since `EvidenceModel`
  gained two required-shape columns; the dedicated `paytmflow_test` database used by the
  integration test suite is recreated fresh from `Base.metadata` on every run and needed no
  separate migration step.
- **Multi-target evidence actions**: this fix assumes each `resolved_evidence.values` dict maps
  cleanly onto the executing action's `satisfies` field keys (true for every EVIDENCE action
  across all six current manifests, all of which satisfy exactly one field). A hypothetical
  future action satisfying multiple fields from one evidence submission was not specifically
  tested, since no such action exists today.
- **The two intentionally-deferred ambiguous manifest mappings** (Account Opening's
  `PAN_CARD_IMAGE`, Investment's `KRA_KYC_LETTER`) are unaffected by and unchanged by this fix —
  their pre-existing "consequence_preview stays null" limitation is orthogonal to the bug fixed
  here (that limitation is about `proposed_action_id` resolution at evidence-upload time, not
  about what happens once an action IS executed).
