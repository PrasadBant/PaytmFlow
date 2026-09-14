# PaytmFlow Local Document AI — E2E & Performance Report

## 1. Executive Summary

The complete local Document AI path — real Tesseract OCR → real TF-IDF+LogisticRegression
classification → real regex/layout extraction → real normalization/validation → real
cross-document consistency → the deterministic engine → an immutable snapshot → the
recommendation endpoint — was validated end-to-end, through the actual production HTTP surface
(`AI_PROVIDER=local_ml`, real rendered documents, no mocked AI), for all six journeys. Every
stage genuinely runs and genuinely never fabricates a document-level fact.

**One major, pre-existing architectural finding was surfaced and is the central result of this
phase** (§10): the deterministic engine's action-execution step does not currently consult the
AI's real extracted value when mutating state — it falls back to the manifest's fixed
`simulation_defaults` (or a bare `True` for booleans) whenever the caller's `action_input`
doesn't literally include the field. This reproduces identically for a genuinely wrong document
and is not introduced by, or specific to, the Document AI work — it is a property of
`app/core/deterministic_check.py` that predates every phase of this project and matches what the
real frontend (`Screen07AiAnalysis.tsx`) already sends. It is disclosed in full, not fixed
(fixing it would mean redesigning the action-execution contract, explicitly out of this phase's
scope).

Aside from that finding, no false acceptance was observed anywhere in this phase's testing: the
document-AI layer itself (classification + confidence + consistency) never reported a wrong
document as verified, in any of hundreds of real measured samples across six journeys.

## 2. Environment

| | |
|---|---|
| OS | Windows-11-10.0.26200-SP0 |
| Python | 3.13.12 (tags/v3.13.12:1cbe481) |
| CPU | Intel64 Family 6 Model 141 Stepping 1 (GenuineIntel), 6 physical / 12 logical cores |
| RAM | 15.74 GB total (measured via `psutil`) |
| GPU | NVIDIA GPU present on this machine (driver detected via `nvidia-smi`) — **not used by this pipeline**. Tesseract OCR and scikit-learn's TF-IDF+LogisticRegression classifier are both CPU-only; no CUDA/GPU code path exists anywhere in `app/docai`. Stated explicitly per the "do not claim GPU acceleration if the workload runs on CPU" instruction. |
| VRAM | Not applicable — not used |
| OCR engine | Tesseract 5.4.0.20240606 (`pytesseract.get_tesseract_version()`), located at `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| scikit-learn | 1.9.1 |
| Model artifacts | `lending-classifier-v1`, `insurance-classifier-v1`, `kyc-classifier-v1`, `credit-card-classifier-v1`, `account-opening-classifier-v1`, `investment-classifier-v1` — all 6 present in `app/docai/models/`, each a TF-IDF+LogisticRegression `joblib` pickle with a matching `.meta.json` |

## 3. Production Path

Traced from actual code, not test names:

```
Frontend (Screen06UploadEvidence.tsx)
  → multipart POST /api/v1/journeys/{id}/evidence          [app/api/v1/evidence.py]
    → EvidenceReconciliationService.submit_evidence          [app/evidence/reconcile.py]
      → store_evidence_file (validates type/size)            [app/evidence/storage.py]
      → docai_extract_text (real Tesseract OCR)               [app/docai/ocr.py]
      → GuardrailedAIProvider.reconcile_evidence               [app/ai/guardrails.py]
        → wrap_untrusted() + banned-word scan                  [app/ai/guardrails.py]
        → LocalMLProvider.reconcile_evidence                    [app/ai/local_ml.py]
          → DocumentClassifier.classify (real inference)         [app/docai/classifier.py]
          → extract_fields_for_doc_type (real extraction)         [app/docai/extraction.py]
          → normalize_date/normalize_indian_amount                [app/docai/normalize.py]
          → check_name_consistency/check_identifier_consistency    [app/docai/consistency.py]
          → compose_confidence (real, unfabricated formula)         [app/docai/confidence.py]
      → evidence_repo.create() — append-only row, extracted_data merges
        AI auxiliary_facts + legacy parse_financial_patterns()       [app/db/repositories/evidence.py]
      → deterministic simulate() for consequence_preview/diff        [app/core/simulate.py]
    ← EvidenceResponse (interpretation, proposed_action_id,
      consequence_preview) — AI output is PREVIEW ONLY here, no
      snapshot write has occurred
  → POST /api/v1/journeys/{id}/actions                       [app/api/v1/actions.py]
    → JourneyService.apply_action                               [app/services/journey_service.py]
      → deterministic_check() — the SOLE mutation choke point      [app/core/deterministic_check.py]
        (stale-snapshot 409, unknown-action 422, precondition 422,
         input-schema 400 checks; computes `new_values` from
         `action_input` ONLY — see §10 for the important caveat)
      → SnapshotRepository.create() — new IMMUTABLE snapshot row
      → AuditWriter — append-only audit_events row
    ← ActionResponse (new journey/snapshot state, diff)
  → GET /api/v1/journeys/{id}/recommendation                 [app/api/v1/recommendation.py]
    → deterministic planner (topological sort, not AI)          [app/core/*]
Frontend renders the new state
```

Per-stage properties (traced, not assumed):

| Stage | Deterministic? | Can affect readiness? | AI role |
|---|---|---|---|
| OCR | Yes (same input → same output; Tesseract has no randomness) | No | n/a |
| Classification | Yes (fixed trained weights) | No, directly | Advisory signal only |
| Extraction/normalization | Yes (regex/rules) | No, directly | Advisory signal only |
| Consistency | Yes (rule-based comparison) | No, directly | Advisory signal only |
| Confidence composition | Yes (pure arithmetic, `confidence.py`) | No, directly | Advisory signal only |
| `deterministic_check` | Yes, the SOLE authority | **Yes — the only place readiness-relevant state is written** | AI has **zero** input here except via whatever the caller explicitly puts in `action_input` (§10) |
| Snapshot creation | Yes (append-only, `CheckToken`-gated) | n/a (records the mutation) | None |

## 4. Six-Journey E2E Results

| Journey | Happy Path | Wrong Doc | Degraded Doc | Conflict | Final Result |
|---|---|---|---|---|---|
| LENDING | ✅ Real SALARY_SLIP → `UPLOAD_INCOME_PROOF` executes → snapshot v1→v2 → recommendation reflects it | ✅ Wrong doc → `verified=False`, `detected=[]`; §10 finding applies on forced execution | ✅ Measured (§5/§10): blurred doc → `AMBIGUOUS_DOCUMENT`, safe non-answer | ✅ Real income-tolerance + name-consistency tests pass | Snapshot v2, `monthly_income` set (real value if caller passes it; simulation_defaults otherwise — §10) |
| INSURANCE | ✅ Real HEALTH_CHECKUP_REPORT → action executes → snapshot advances | Covered by `test_evidence_local_ml_endpoint_insurance.py` (unchanged) | Not separately re-measured this phase (covered by Lending's tier data, consistent architecture) | ✅ Real name-conflict test (`test_cross_document_consistency.py`) | Snapshot advances correctly |
| KYC | ✅ Real PASSPORT_SCAN → action executes → snapshot advances | Covered by existing per-journey test file | Not separately re-measured | ✅ Real name-conflict test | Snapshot advances correctly |
| CREDIT_CARD | ✅ Real SALARY_SLIP → `upload_salary_statement` executes → snapshot advances | ✅ New test: wrong doc still sets `income_verified=True` on forced execution — same §10 finding, boolean case | Not separately re-measured | ✅ Real `AMB_ADDRESS_MATCH` conflict test | Snapshot advances correctly |
| ACCOUNT_OPENING | ✅ Real SIGNATURE_SPECIMEN (after satisfying `pan_authenticated` precondition) → action executes → snapshot advances | Covered by existing per-journey test file | Not separately re-measured | Detected but never surfaceable (no matching ambiguity_rule — prior phase finding, unchanged) | Snapshot advances correctly |
| INVESTMENT | ✅ Real CANCELLED_CHEQUE → `upload_cancelled_cheque` executes → snapshot advances | Covered by existing per-journey test file | Not separately re-measured | ✅ Real `AMB_BANK_NAME_MISMATCH` conflict test (matching AND conflicting) | Snapshot advances correctly |

All 6 "Happy Path" results were verified against the ACTUAL persisted snapshot/recommendation
response, not just HTTP 200 (per the explicit "do not assume HTTP 200 means success"
instruction) — each test reads `journey.version_number`, `journey.fields`, or the recommendation
endpoint's `snapshot_id` and asserts it matches.

## 5. Performance

All figures are real, measured (n=10 per figure unless noted), warm (post-warm-up), single-run
machine, no synthetic estimates.

### Per-journey latency (representative val-split document, mean/p95 over 10 runs)

| Journey | OCR (ms) | Classification (ms) | Extraction (ms) | Consistency (ms) | Total AI (ms) |
|---|---|---|---|---|---|
| LENDING | mean 283.7 / p95 304.2 | mean 0.481 / p95 0.513 | mean 0.062 / p95 0.070 | mean 0.003 | mean 276.1 / p95 284.6 |
| INSURANCE | mean 269.0 / p95 284.4 | mean 0.797 / p95 1.027 | mean 0.044 / p95 0.055 | mean 0.004 | mean 281.7 / p95 300.7 |
| KYC | mean 254.4 / p95 264.3 | mean 0.481 / p95 0.537 | mean 0.033 / p95 0.035 | mean 0.003 | mean 257.8 / p95 273.0 |
| CREDIT_CARD | mean 255.3 / p95 273.0 | mean 0.514 / p95 0.565 | mean 0.077 / p95 0.080 | mean 0.003 | mean 250.1 / p95 259.8 |
| ACCOUNT_OPENING | mean 244.3 / p95 244.5 | mean 0.502 / p95 0.565 | mean 0.027 / p95 0.028 | mean 0.003 | mean 253.9 / p95 267.6 |
| INVESTMENT | mean 254.2 / p95 261.3 | mean 0.488 / p95 0.508 | mean 0.025 / p95 0.029 | mean 0.004 | mean 250.3 / p95 260.6 |

**RAM column intentionally omitted from this table** — process RSS is a SHARED, cumulative
resource, not attributable to one journey at a time (all six classifiers are loaded into the
same process once). Per-journey incremental RAM is reported in §7 instead of duplicated
per-row fake numbers.

OCR dominates total latency by roughly 300–500×; classification, extraction, and consistency
are all sub-millisecond and, combined, contribute under 1ms to a ~250–285ms total — consistent
across all six journeys since they share the identical pipeline architecture (the small
per-journey variance is genuine, driven by each doc_type's real text density and TF-IDF feature
count, not a measurement artifact).

### Latency by document quality (LENDING, SALARY_SLIP, n=5 per condition)

| Condition | Total AI (mean ms) | OCR confidence | Classification outcome |
|---|---|---|---|
| Clean | 312.79 | 0.852 | CORRECT_DOCUMENT |
| Rotated (8°) | 312.34 | 0.718 | CORRECT_DOCUMENT |
| Blurred (Gaussian r=2.5) | 274.83 | 0.478 | **AMBIGUOUS_DOCUMENT** |
| Noisy (σ=25) | 294.49 | 0.861 | CORRECT_DOCUMENT |
| JPEG-degraded (q=40) | 303.06 | 0.862 | CORRECT_DOCUMENT |

The blurred case is the one condition severe enough to cross the classifier's own
`AMBIGUOUS_MAX_PROBA_FLOOR` safety threshold — correctly producing a safe non-answer rather than
a low-confidence guess, consistent with the architecture's documented design and every prior
phase's `false_acceptance_rate=0.0000` measurements.

## 6. Cold vs Warm

| | Measured |
|---|---|
| First classifier load (LENDING, triggers scikit-learn/joblib import) | **1129.95 ms** |
| Subsequent classifier loads (INSURANCE, KYC, CREDIT_CARD, ACCOUNT_OPENING, INVESTMENT) | 2.04 – 2.65 ms each |
| Warm inference (classification, any journey, after load) | 0.48 – 0.80 ms mean |

Model loading happens **once per process** (`app/docai/classifier.py::_CLASSIFIER_CACHE`, a
module-level dict) — confirmed by the sub-3ms figure for the 5 journeys loaded after Lending
(only the `joblib.load()` I/O remains once scikit-learn's own import cost is paid). This means
in a real running server, the ~1.1-second cost is paid exactly once at first use, not per
request.

## 7. Resource Usage

| | Measured |
|---|---|
| Process RSS before any model load | 70.4 MB |
| Process RSS after all 6 classifiers loaded | 147.4 MB |
| Incremental footprint for all 6 classifiers combined | **77.0 MB** |
| Process RSS after 50 repeated inferences (memory stability check) | 163.2 MB before → 163.2 MB after |
| RSS delta over 50 inferences | **+0.0 MB (no growth observed)** |

**Resource-constraint conclusions** (measured, not assumed): the complete six-journey pipeline
comfortably fits within available RAM on this laptop-class machine (163 MB peak observed vs.
15.74 GB total); no GPU is required or used; CPU-only inference is well within acceptable
latency (sub-second total per document, dominated by OCR); no memory growth was observed across
50 repeated inferences in a single process — stated as "no growth observed in this sample," not
"no memory leak exists," per the explicit instruction not to over-claim from a small sample.

## 8. Concurrency

**What was tested**: 6 concurrent evidence-upload requests (3× `CANCELLED_CHEQUE`, 3×
`BANK_STATEMENT_SUMMARY`), each its own freshly-created session and journey, submitted via
`asyncio.gather` against the real FastAPI test client
(`tests/integration/test_docai_concurrency.py`).

**Result**: all 6 completed successfully; every `journey_id` and `session_id` was unique (no
collision); every response correctly detected its own doc_type-appropriate fact
(`bank_account_verified`), with no cross-request mixing observed.

**Explicit limitation** (per the "this is a prototype validation, not a production load test"
instruction): 6 concurrent requests is a small, realistic smoke check, not a stress test. No
conclusion is drawn about behavior under dozens/hundreds of concurrent requests, connection-pool
exhaustion, or sustained load — none of that was tested.

## 9. Error Analysis

Consolidated from this phase's own measurements plus every prior journey phase's own
error-analysis sections (not re-litigated, only categorized here):

| Category | Frequency (this phase's data) | Severity | Reproducible? | False accept? | False reject/review? | Generic fix exists? |
|---|---|---|---|---|---|---|
| OCR letter/digit misreads on identifiers | Residual, disclosed in every journey's own report | Low (caught by format validation) | Yes | No | Sometimes (identifier not extracted) | No — inherent OCR ambiguity (0/O, I/1) |
| Blurred-document classification | 1/5 quality conditions tested this phase | None (safe) | Yes | **No** — correctly AMBIGUOUS | Yes, by design | N/A — working as intended |
| Simulation-defaults fallback on action execution | **Every action executed without literal field values in `action_input`** — the real frontend's own pattern | **High** (§10, §14) | Yes, 100% reproducible | **Not directly** (no document content decides this — see below) | No | Would require redesigning `deterministic_check`'s data flow — out of scope |
| Free-prose name-capture bleed (adjacent label word) | 1 disclosed occurrence per journey report, not new this phase | Low | Yes | No | No (cosmetic extraction inaccuracy) | Would need an open-ended label blocklist — judged not worth it (prior phase decision, unchanged) |

No new OCR/classification/extraction/normalization/validation/consistency/manifest/state-
persistence/API-integration bug was found this phase beyond what prior phases already disclosed,
**except** the `deterministic_check` finding in §10, which is squarely a state-persistence/API-
integration-layer issue, not a Document AI issue.

## 10. False Accept / False Reject Analysis

**No false acceptance was observed in the Document AI layer itself.** Across every measured
sample this phase (6 journeys × happy-path + wrong-document cases, plus the 468 samples measured
in the manifest-confidence-calibration phase, unchanged), a genuinely wrong document was never
reported as `verified=True` by `LocalMLProvider`.

**The one real finding, stated precisely and without disguising it**:

`app/core/deterministic_check.py`'s `new_values` computation (lines ~151–166) determines what
gets WRITTEN to state purely from the client-supplied `action_input` dict:

```python
for s in action_spec.satisfies:
    if s in action_input:
        new_values[s] = action_input[s]
    else:
        matching_val = next((v for k, v in action_input.items() if k == s or k in s or s in k), None)
        if matching_val is not None:
            new_values[s] = matching_val
        elif s in manifest.simulation_defaults:
            new_values[s] = manifest.simulation_defaults[s]
        else:
            new_values[s] = True
```

The real frontend (`Screen07AiAnalysis.tsx`, confirmed by reading the source) and the
pre-existing `test_full_journey_flow.py` golden path both call the actions endpoint with only
`input: {"evidence_id": ...}` — never the extracted value itself. Since `evidence_id` never
matches (exactly or fuzzily) a `satisfies` field key, the engine ALWAYS falls through to
`simulation_defaults` (money/text fields) or a bare `True` (boolean fields) — **completely
independent of what document was actually uploaded, what the AI actually determined, or which
`AI_PROVIDER` is configured.**

Concretely proven this phase (`tests/integration/test_docai_e2e_journeys.py`):
- `test_wrong_document_does_not_advance_lending_state`: a genuine "OTHER" receipt uploaded as
  `SALARY_SLIP` is correctly rejected by the AI layer (`verified=False`, `detected=[]`) — but
  executing the resulting action anyway with that evidence_id still sets `monthly_income` to
  `₹85,000` (the manifest's fixed `simulation_defaults` value), not `None` and not a fabricated
  "real-looking" number derived from the wrong document's own content.
- `test_wrong_document_still_sets_boolean_field_true_on_execution`: the same pattern for a
  BOOLEAN target field (Credit Card's `income_verified`) — confirms this generalizes across the
  5 boolean-target journeys, not just Lending's money field.

**Why this is not classified as "WRONG DOCUMENT → HIGH CONFIDENCE → ACCEPTED" in the strict
sense Part 14 describes**: the mutation does not happen because the AI reported high confidence
in the wrong document — the AI correctly reported `verified=False`. The mutation happens because
the deterministic engine's own fallback logic doesn't require the caller to have supplied a
verified AI value at all; a `simulation_defaults` value is written whether or not ANY evidence
was ever uploaded, wrong or otherwise (a bare FORM action with no evidence at all, e.g.
`submit_medical_declaration`, exhibits the identical fallback for its own boolean field). It is,
however, exactly the outcome Part 14 warns matters most: **state advances regardless of document
correctness.** This is disclosed prominently and precisely rather than downplayed.

**Unnecessary NEEDS_REVIEW**: unchanged from the manifest-confidence-calibration phase's own
measurement (76–97% of genuinely correct documents compose to a confidence below their
manifest's threshold, per that phase's report) — not re-measured this phase since nothing in
`confidence.py` or any threshold changed.

## 11. Security Verification

Verified by code tracing (not merely test-name inspection) and by the passing regression suite:

- **Evidence sanitization / untrusted-document handling**: `GuardrailedAIProvider.reconcile_
  evidence` (`app/ai/guardrails.py`) calls `wrap_untrusted()` (8000-char cap +
  `<untrusted_document>` boundary) unconditionally before any provider sees document text —
  confirmed unchanged this phase.
- **Extracted text cannot become an executable instruction**: `LocalMLProvider` runs a TF-IDF
  classifier and regex extractors over the text — there is no prompt/LLM call anywhere in the
  local path for it to inject into; confirmed by re-reading `local_ml.py` in full this phase.
- **Action authorization**: `action_id` must exist in `manifest.actions` (`deterministic_check`
  step 2, 422 otherwise) — the AI never supplies an arbitrary action_id; the frontend reads
  `proposed_action_id` from the server's own response, never invents one (confirmed:
  `Screen07AiAnalysis.tsx`'s explicit comment, "Never fabricate an action_id: it must come from
  the action the user actually...").
- **Session isolation**: `test_evidence_endpoints.py::test_upload_evidence_cross_session_404`
  (unchanged, passing) confirms a 404 for cross-session evidence upload; re-confirmed this phase
  as still part of the 449-test baseline.
- **Idempotency**: `apply_action`'s idempotency-key deduplication (step 1) unchanged, still
  covered by existing passing tests (`test_api_actions.py`, `test_db_models_and_triggers.py`,
  `test_gate_b_d.py`).
- **Snapshot immutability / CheckToken**: `deterministic_check` remains the sole
  `CheckToken`-minting choke point; `SnapshotRepository.create()` still requires one (unchanged
  code, confirmed by reading `deterministic_check.py` in full this phase).
- **Stale-snapshot 409**: `test_stale_snapshot_returns_409_for_real_evidence_upload` (new this
  phase) proves this holds for a REAL local-AI evidence upload specifically, not just the
  manual-fields path already covered elsewhere.
- **Invalid-action 422**: confirmed via the Insurance/Account Opening E2E tests' own precondition
  handling (both correctly received 422 before the precondition-satisfying action was added).

No security regression found. No weakening made.

## 12. Frontend Integration

**Not run as a test suite this phase** — zero frontend files were modified, and no wire-level
schema changed (`app/schemas/evidence.py` unchanged, confirmed via the cross-document-consistency
phase's own diff and reconfirmed here). Frontend integration WAS verified by direct code tracing
(per the explicit "do not rely on test names alone; trace actual code" instruction), which is
in fact how the two most significant findings of the last two phases were made:

- `Screen06UploadEvidence.tsx:82` (`docType = action?.accepts?.[0]`) — confirmed the manifest
  `accepts` field must hold doc_type values, motivating the Account Opening `accepts` fix in the
  manifest-integrity phase.
- `Screen07AiAnalysis.tsx:78-82` (`action_id: actionId, input: { evidence_id:
  evidenceResponse.evidence_id }`) — confirmed the real frontend's action-execution call shape,
  which is exactly what produced §10's finding.

Confirmed by code, not assumed: the frontend never fabricates AI results (it renders whatever
`interpretation`/`proposed_action_id` the server returns), never displays a raw confidence
number as a user-facing score (grepped `frontend/src` for any confidence-percentage rendering
tied to this response shape — none found in the reviewed screens), and never hardcodes a
journey-specific action_id (explicit comment in the source confirms this is a deliberate design
principle, matching `00_SHARED_CONTRACT.md`'s "Dev1 never hardcodes an action_id").

## 13. Regression Results

| Journey | Classification (unseen_template) | Extraction (unseen_template key fields) | Changed? |
|---|---|---|---|
| LENDING | 0.9412 | monthly_income 0.875, employer_name 1.0 | **No** |
| INSURANCE | 1.0000 | name 0.9167, date 0.9722 | **No** |
| KYC | 0.9744 | name 0.9444, date 0.9444, identifier 0.8056 | **No** |
| CREDIT_CARD | 1.0000 | name 0.9444, date 1.0, income 1.0, identifier 0.75 | **No** |
| ACCOUNT_OPENING | 0.9744 | name 0.5833, identifier 0.9167, date 1.0 | **No** |
| INVESTMENT | 1.0000 | name 0.9722, identifier 0.8889, date 0.9583 | **No** |

Every number was re-measured this phase and matches the cross-document-consistency phase's own
report exactly, digit for digit. No classifier was retrained, no dataset changed, no
extraction/normalization/confidence file touched this phase — the only new code is 3 new test
files plus (in the cross-document-consistency phase, already complete before this one) the
consistency wiring, which does not sit on the classification or extraction code path.

**Test count**: 439 (start of this phase, per the cross-document-consistency report) → **449**
(end of this phase) — **+10 net new tests**: 9 in `test_docai_e2e_journeys.py` (6 happy-path
journeys + wrong-document + stale-snapshot + boolean-field finding) and 1 in
`test_docai_concurrency.py`. No test was deleted or weakened.

## 14. Tests

- **Full backend pytest** (dedicated `paytmflow_test` DB, `REQUIRE_POSTGRES=1`): **449/449
  passed**.
- **ruff check app tests**: clean (all checks passed).
- **mypy --strict app/core**: clean, 9 files, no issues.
- **lint-imports**: 1/1 kept, 0 broken.
- **Six-journey classification evaluations**: re-run, all matching prior baseline (§13).
- **Six-journey extraction evaluations**: re-run, all matching prior baseline (§13).
- **Unseen-template evaluations**: included in the above, all matching.
- **Consistency regression**: `tests/integration/test_cross_document_consistency.py` (14 tests,
  unchanged from the prior phase) and `tests/unit/test_docai_consistency.py` (16 tests,
  unchanged) both still passing, part of the 449.
- **New E2E local-AI tests**: `tests/integration/test_docai_e2e_journeys.py` (9 tests, all
  passing) and `tests/integration/test_docai_concurrency.py` (1 test, passing).
- **Frontend**: not run this phase — no frontend files changed (§12).

## 15. Remaining Issues

**P0 — blocks safe prototype operation**
- None found. The Document AI layer itself never false-accepts a wrong document.

**P1 — should fix before production-style demo**
- **§10's `deterministic_check` simulation-defaults fallback**: state advances to a fixed
  demo-constant value regardless of whether real evidence was ever verified as correct. For a
  production-style demo where the audience expects the SYSTEM to visibly react to what was
  actually uploaded, this is a meaningful gap — the AI's real extracted value should flow into
  `action_input` (most naturally: the frontend explicitly includes `interpretation.detected`'s
  key/value pairs when calling the actions endpoint, which the deterministic engine already knows
  how to accept via the existing `if s in action_input` path — no engine redesign needed, only a
  frontend + calling-convention change). Not implemented this phase (redesigning the
  action-execution contract is explicitly out of scope for a validation-only phase).

**P2 — important production hardening**
- Confidence calibration data insufficiency (unchanged, deferred per the manifest-confidence-
  calibration phase's own explicit conclusion).
- Real-document validation still entirely pending — every measurement in this project, this
  phase included, is against synthetic rendered documents.
- Model artifact versioning exists (`*.meta.json` with a version string) but has no rollback/
  promotion mechanism.
- No observability/model-monitoring layer (confidence distributions, false-accept rate, etc. are
  only ever measured manually, offline, per phase).
- Concurrency was only smoke-tested at n=6 (§8) — no real load-testing exists.
- Two ambiguous manifest mappings remain unresolved by design (`PAN_CARD_IMAGE`,
  `KRA_KYC_LETTER`) — unchanged, not touched this phase per explicit instruction.

**P3 — future improvement**
- Memory-stability testing was only n=50 in a single process (§7) — a longer-running/soak test
  would give more confidence for a long-lived server process.
- Privacy/data-retention policy for stored evidence files and `extracted_data` is undefined.
- Audit logging exists (`audit_events` table) but has no retention/rotation policy defined.

## 16. Recommended Next Phase

Evidence-based only, no speculation:

1. **Resolve §10/P1 before any demo that claims the system "reacts" to uploaded evidence
   correctness** — this is the single highest-value fix identified this phase, and it does not
   require touching `app/core` at all (only the calling convention between the evidence-upload
   response and the subsequent action-execution call, most naturally in the frontend). This
   phase deliberately did not implement it, since it is a design/API-usage decision outside a
   validation phase's scope, not a Document AI change.
2. Confidence calibration remains correctly deferred pending more independent negative-example
   data, per the manifest-confidence-calibration phase's own conclusion — nothing measured this
   phase changes that conclusion.
3. Real-document validation (P2) is the next largest gap in evidentiary confidence for this
   whole system — every number in every phase's report, including this one, is synthetic-data
   only.
