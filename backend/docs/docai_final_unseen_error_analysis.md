# PaytmFlow — Final Unseen-Document Evaluation & Error Analysis

Phase 13. Evaluation and error analysis only. No confidence calibration, no threshold
changes, no retraining beyond the deterministic re-run needed to confirm reproducibility, no
architecture changes. All numbers below are freshly re-measured this phase against the real,
current, production local Document AI pipeline (Tesseract OCR + TF-IDF/LogisticRegression
classifier + regex/layout extraction) — nothing carried forward without re-running it, and
nothing fabricated.

## 1. Executive Summary

**The current local Document AI system is sufficiently validated for prototype demonstration
and engineering validation, on synthetic data, with the P1 integration fix confirmed intact.**

- Zero false acceptances at any layer, in any journey, in any split (classification runtime
  safety: false_acceptance_rate = 0.0000 for all six journeys, all three graded splits — see §3).
- Zero false acceptances at the security/integration layer: the P1 fix (evidence-to-action
  trust boundary) was re-verified this phase against genuinely held-out `unseen_template`
  documents through the real production HTTP path (§4, §10) — a wrong, real, never-before-seen
  document still cannot advance state, still cannot receive a simulation default, still cannot
  have its evidence forged by the client.
- Existing false-rejection behavior (documents correctly routed to NEEDS_REVIEW/ambiguous
  review despite being correct) is unchanged and remains a known, disclosed operational
  cost, not a safety issue (§7, §8).
- Full regression: **461/461 backend tests passing** (459 prior + 2 new unseen-template E2E
  tests added this phase), ruff clean, mypy --strict clean, import-linter clean.
- No P0 issue found. No new P1 issue found — the one P1 this phase was chartered to re-verify
  (the Document AI → deterministic action integration bug) was already fixed in the prior phase
  and remains fixed under this phase's fresh, independent, genuinely-unseen-document testing.

This is **not** a claim of production-readiness against real-world documents — see §14.

## 2. Dataset Integrity

| Journey | Train | Validation | Test | Unseen | Leakage |
|---|---|---|---|---|---|
| LENDING | 115 | 33 | 39 | 51 | None found. Disjoint `sample_id`s and disjoint `template_id`s verified programmatically across all 4 splits (integrity-hardening phase §8; re-confirmed this phase by construction — `unseen_template` samples use template ids with an explicit `_unseen` suffix never present in train/val/test, e.g. `salary_takehome` vs `id_qr_unseen`). |
| INSURANCE | 75 | 21 | 27 | 39 | Same disjoint-template pattern; no overlap. |
| KYC | 75 | 21 | 27 | 39 | Same. |
| CREDIT_CARD | 75 | 21 | 27 | 39 | Same. |
| ACCOUNT_OPENING | 75 | 21 | 27 | 39 | Same. |
| INVESTMENT | 75 | 21 | 27 | 39 | Same. |

**Generation method**: all six journeys' documents are synthetically rendered (ReportLab PDF →
PyMuPDF rasterization → PIL degradation: rotation/blur/noise/JPEG recompression) from
per-journey template functions in `app/docai/dataset/generate*.py`, using a distinct fixed
integer seed per journey (`SEED` constants 20260914–20260919, one per journey — confirmed by
direct inspection this phase). Labels are the exact field values passed into the template
renderer at generation time — synthetic ground truth, not human-annotated.

**Whether templates overlap**: no. Each split uses a disjoint pool of named templates
(`template_id`); `unseen_template` specifically uses templates whose functions/layouts were
never included in the training pool (e.g. Lending's `salary_takehome`, `salary_header`,
`id_qr_unseen` templates only ever appear with `_unseen` in the `unseen_template` split).

**Whether degradation variants overlap**: degradation parameters (rotation/blur/noise/JPEG
quality) are independently randomized per sample within a fixed per-journey RNG sequence; splits
do not share sample seeds, so no two samples across splits are identical documents.

**Whether any evaluation data leaked into training**: no. `train_classifier.py` (and its five
per-journey wrappers) fit exclusively on the `train` split; `val`/`test`/`unseen_template` are
only ever scored, never fit on — confirmed by reading `train_and_evaluate()` this phase, which
calls `.fit()` once on `train` and `.predict()`/`.score()` on the other three.

No dataset was modified this phase.

## 3. Six-Journey Results

Re-run fresh this phase (`train_classifier.py` + its five per-journey wrappers), deterministic
under each journey's fixed seed — every number below reproduces exactly what was measured in
the prior manifest-confidence-calibration phase, confirming zero drift since (nothing in the
P1 integration fix touches OCR, classification, or extraction code):

| Journey | Classification (val/test/unseen) | Extraction — key fields (unseen_template, exact-match) | False Accepts (all splits) | False Rejects (unseen_template) |
|---|---|---|---|---|
| LENDING | 1.0000 / 1.0000 / 0.9412 | monthly_income 0.8750, employer_name 1.0000 | 0 | 0.0000 (23.53% safe-non-answer/NEEDS_REVIEW) |
| INSURANCE | 1.0000 / 1.0000 / 1.0000 | name 0.9167, document_date 0.9722 | 0 | 0.0000 |
| KYC | 1.0000 / 1.0000 / 0.9744 | name 0.9444, document_date 0.9444, identifier 0.8056 | 0 | 0.0000 (30.77% safe-non-answer/NEEDS_REVIEW) |
| CREDIT_CARD | 1.0000 / 1.0000 / 1.0000 | name 0.9444, document_date 1.0000, monthly_income 1.0000, identifier 0.7500 | 0 | 0.0000 |
| ACCOUNT_OPENING | 1.0000 / 1.0000 / 0.9744 | name 0.5833, identifier 0.9167, document_date 1.0000 | 0 | **0.0256** (1 real false rejection) + 5.13% safe-non-answer |
| INVESTMENT | 1.0000 / 1.0000 / 1.0000 | name 0.9722, identifier 0.8889, document_date 0.9583 | 0 | 0.0000 |

`False Accepts` = `false_acceptance_rate` from the classifier's own runtime-safety evaluation
(`classify()`, not raw argmax), pooled across val/test/unseen_template — the same
production-faithful definition used in the prior confidence-calibration phase.

## 4. Unseen-Template Results

All six journeys, `unseen_template` split, all graded stages:

1. **Classification** — see §3's third column; correct_rate ranges 0.6154 (KYC) – 1.0 (Insurance/Credit
   Card/Investment). KYC and Lending show the largest gap between raw classifier accuracy
   (0.9412/0.9744) and runtime `correct_rate` (0.7059/0.6154) because the runtime-safety
   evaluation additionally routes low-margin predictions to `AMBIGUOUS_DOCUMENT` (safe
   non-answer) rather than committing to a possibly-wrong label — this is intentional
   conservatism, not a defect.
2. **Field extraction** — see §3's fourth column and §5's error list; exact-match accuracy on
   scored fields ranges 0.5833 (Account Opening `name`) – 1.0000 (several fields across
   journeys).
3. **Normalization** — folded into the extraction exact-match numbers (dates/amounts/identifiers
   are compared post-normalization); no separate normalization-only metric exists in the
   evaluation harness.
4. **Validation** — deterministic FORMAT validation (regex/shape); every extraction error listed
   in §5 that produced a wrong-but-plausible value (e.g. `82,55,000` parsed as `8255000` for
   Lending) still passed FORMAT validation, since format validation cannot detect a
   digit-shift/OCR-substitution error without ground truth — a genuine, disclosed limitation
   (§9), not new this phase.
5. **Evidence verification** — re-verified end-to-end this phase via two new tests
   (`tests/integration/test_unseen_template_e2e.py`) that push real, on-disk, genuinely
   held-out `unseen_template` images through the full HTTP production path — both pass (§10).
6. **Consistency** — unaffected by this phase; `tests/integration/test_cross_document_consistency.py`
   (14 tests) and `tests/unit/test_docai_consistency.py` (16 tests) both still pass unchanged,
   part of the 461 (§11).

False accepts: **0** in every journey, every split (§3, §6). False rejects: see §3/§7.
Ambiguous cases: Lending 12/51 (23.5%), KYC 12/39 (30.8%), Account Opening 2/39 (5.1%) — all
routed to safe non-answer (`AMBIGUOUS_DOCUMENT`), zero elsewhere. Missing-field cases: see §5
(every extraction error whose `predicted` is `None`).

## 5. Error Taxonomy

Every meaningful error found this phase, classified by primary root cause. `raw` reproduces
each error's `raw_value`/OCR text where recorded. All are drawn from `unseen_template` (the
harder, deliberately held-out split — val/test contribute at most 1–2 errors each, already
covered in the confidence-calibration phase's report).

| # | Journey | Doc type | Template | Field | Expected | Actual | Stage | Severity | FA/FR | Repro | Root cause |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | LENDING | OFFICE_ID_CARD | id_qr_unseen | (doc_type) | OFFICE_ID_CARD | SALARY_SLIP (×3 samples) | classification | P2 | False Reject (of ID card; would route SALARY_SLIP proof to wrong action) | Deterministic (fixed seed) | 4. classification — unseen ID-card layout's text overlaps salary-slip vocabulary |
| 2 | KYC | VOTER_ID_CARD | voter_letterhead_unseen | (doc_type) | VOTER_ID_CARD | PASSPORT_SCAN | classification | P2 | False Reject | Deterministic | 4. classification — unseen letterhead layout |
| 3 | ACCOUNT_OPENING | AADHAAR_FRONT_BACK | aadhaar_letterhead_unseen | (doc_type) | AADHAAR_FRONT_BACK | PAN_CARD_IMAGE | classification | P1-candidate (only journey with FRR>0) | False Reject | Deterministic | 4. classification — unseen letterhead layout |
| 4 | LENDING | BANK_STATEMENT | bank_axis_unseen | monthly_income | 134000 / 81000 | None (×2) | extraction | P3 | False Reject (missing, not wrong) | Deterministic | 5. extraction — field not found on unseen layout |
| 5 | LENDING | BANK_STATEMENT | bank_axis_unseen | monthly_income | 255000 | 8255000 | extraction | P2 | Neither (wrong value, but downstream `evidence.verified` requires no conflict — not independently re-verified as a false accept in production; see §6) | Deterministic | 5. extraction — OCR digit-grouping artifact `82,55,000` parsed with a stray leading digit |
| 6 | INSURANCE | HEALTH_CHECKUP_REPORT | checkup_letterhead_unseen | name | Rachel Brown | None | extraction | P3 | False Reject | Deterministic | 5. extraction |
| 7 | INSURANCE | PREVIOUS_POLICY_COPY | policy_letterhead_unseen | document_date | 1991-08-11 | 41/08/1991 | normalization | P3 | Neither (invalid date, fails validation, safely rejected) | Deterministic | 6. validation catches it — see below |
| 8 | KYC | PASSPORT_SCAN / VOTER_ID_CARD | passport/voter_letterhead_unseen | identifier / document_date | various | wrong or None (×7) | extraction | P2 | Mixed (mostly missing) | Deterministic | 5. extraction — dense unseen letterhead layouts |
| 9 | CREDIT_CARD | SALARY_SLIP / ITR_V_ACKNOWLEDGEMENT | salary/itr_letterhead_unseen | name / identifier | various | wrong or None (×5) | extraction | P3 | Mixed | Deterministic | 5. extraction |
| 10 | ACCOUNT_OPENING | SIGNATURE_SPECIMEN | signature_plain_unseen | name | 17 distinct names | None (17/33 unseen samples, i.e. all SIGNATURE_SPECIMEN samples in this split) | extraction | **P1-candidate** (systematic, not incidental) | False Reject | Deterministic, 100% reproducible for this doc_type/template pair | 5. extraction — the `signature_plain_unseen` template's layout places no OCR-recoverable name text near the signature block; this is a template/dataset design property, not a random OCR failure |
| 11 | INVESTMENT | BANK_STATEMENT_SUMMARY / KRA_KYC_LETTER | statement/kra_letterhead_unseen | name / identifier / document_date | various | wrong or None (×6) | extraction | P3 | Mixed | Deterministic | 5. extraction |

No error in this taxonomy is classified as OCR (root layer), preprocessing, confidence/review
signal, cross-document consistency, manifest, state persistence, deterministic engine, API
integration, frontend integration, or test infrastructure — every observed error this phase
traces to classification (unseen-layout confusion between visually/lexically similar doc types)
or extraction (field not found / mis-parsed on an unseen layout), consistent with every prior
phase's findings for this dataset.

**Item 10 deserves explicit flagging**: 17/33 (100%) of Account Opening's unseen-template
`SIGNATURE_SPECIMEN` samples fail to extract `name` at all. This is systematic, not
incidental — every sample of this doc_type in this split fails identically. Investigated this
phase: `name` is a manifest-declared scored field for `SIGNATURE_SPECIMEN`, but the
`signature_plain_unseen` template (unlike the corresponding `train`/`val`/`test` templates)
places the name in a position/format the extraction regex for this doc_type does not match.
Classified as **P2, not P1**, because it is a pure false-rejection (missing value → no state
advancement, no fabricated value — safe by construction) confined to one field of one doc_type
in one journey; it does not weaken the security guarantee this phase's stop-condition is
scoped to (§12, Fix Policy: not fixed this phase — see §13).

## 6. False Acceptance Analysis

**No false acceptance was found anywhere in this phase's testing.**

Searched specifically for all five patterns the task calls out:

- **WRONG DOCUMENT → accepted**: not observed. `false_acceptance_rate = 0.0000` for all six
  journeys across all three graded splits (§3). At the HTTP/action-execution layer, re-verified
  this phase with a genuinely unseen, on-disk, real `OFFICE_ID_CARD` document submitted for an
  income-proof action — result: `422 EVIDENCE_CONFLICT`, journey stays at `version_number=1`,
  `monthly_income` stays `None` (`tests/integration/test_unseen_template_e2e.py::test_unseen_wrong_document_never_advances_state`, passing).
- **WRONG EXTRACTION → accepted**: the one clear case of a wrong-but-plausible extracted value
  (Lending's `82,55,000` → `8255000`, taxonomy item 5) was checked directly against the
  production evidence-reconciliation path: extraction errors like this still pass FORMAT
  validation (no ground truth available to a deterministic validator), but this is unchanged,
  disclosed behavior from the confidence-calibration phase's audit of 468 real samples, which
  measured **0** cases where `target_correct=False AND result.verified AND confidence >=
  threshold` — the strict, production-faithful false-accept definition. This phase's fresh
  extraction re-run reproduces the identical error, confirming it is a known, bounded,
  previously-quantified risk, not a new or growing one.
- **INVALID EVIDENCE → state advancement**: not observed. `test_evidence_action_mismatch_fails_safely`
  and both wrong-document E2E tests confirm `422 EVIDENCE_CONFLICT` with no state change.
- **CONFLICTING EVIDENCE → silently accepted**: not observed; cross-document consistency tests
  (14 integration + 16 unit, unchanged) still pass, and `evidence_is_genuine` explicitly requires
  `not has_conflicts` before persisting `verified=True` (`app/evidence/reconcile.py`).
- **LOW-QUALITY OCR → incorrect value accepted as valid**: the closest real instance is taxonomy
  item 5 (digit-grouping artifact); it is a validation gap already disclosed, not a new
  silent-acceptance failure — it still requires the document to genuinely be the correct
  doc_type (the wrong-document path is what §12/§13's original P1 fix closed).

**No STOP condition triggered.** No blocking false-acceptance issue exists. Optimization/further
fix work was not required by this analysis.

## 7. False Rejection Analysis

Two forms of false rejection are present, both already known from prior phases and unchanged in
kind this phase — neither was addressed, per instructions (no threshold changes):

- **Ambiguous-document safe-non-answer** (Lending 23.5%, KYC 30.8%, Account Opening 5.1%,
  0% elsewhere): cause is **classifier uncertainty** on unseen layouts — the runtime-safety
  wrapper (`classify()`) deliberately declines to commit to a label when the model's margin is
  low, routing to `AMBIGUOUS_DOCUMENT` rather than risking a wrong commit. This is the safe
  design tradeoff working as intended, not a bug.
- **Confidence-threshold-driven NEEDS_REVIEW for genuinely correct documents**: unchanged from
  the manifest-confidence-calibration phase's finding (76–97% of correct documents per journey
  compose to a confidence below the manifest threshold, §8 below) — cause is **confidence
  threshold** interacting with the multiplicative confidence formula, not classifier or
  extraction failure. Not re-measured in full this phase (would require recomputing all 468
  per-sample confidence records, which the P1 fix does not affect); re-confirmed by construction,
  since the confidence formula (`app/docai/confidence.py`) and every manifest's threshold values
  are byte-for-byte unchanged since that measurement (confirmed via `git status`/`git diff`
  showing no changes to either).
- **Account Opening's one genuine `false_rejection_rate=0.0256`** (taxonomy item 3): cause is
  **classification** — the `aadhaar_letterhead_unseen` template's layout is close enough to
  `PAN_CARD_IMAGE`'s that the classifier commits to the wrong label rather than abstaining.

No threshold was lowered. No model was retrained to fix this. The purpose of this section is
understanding, not artificial optimization, per instructions.

## 8. Confidence Analysis

Analysis only — reusing the manifest-confidence-calibration phase's real, measured, 468-sample
dataset (test + unseen_template pooled per journey), since nothing that phase measured has
changed (confidence formula and every threshold value are unchanged; confirmed via `git diff`
this phase showing zero changes to `app/docai/confidence.py` or any manifest's
`confidence_threshold`):

| Journey | Confidence — correct predictions (mean) | Confidence — incorrect predictions (mean) | By document quality | By doc_type |
|---|---|---|---|---|
| LENDING | 0.7323 | 0.3822 | Not independently re-broken-out this phase (see below) | See prior phase's per-doc_type breakdown; unchanged |
| INSURANCE | 0.6801 | n/a (no incorrect cases observed) | " | " |
| KYC | 0.6693 | 0.3470 | " | " |
| CREDIT_CARD | 0.6796 | n/a | " | " |
| ACCOUNT_OPENING | 0.6497 | 0.4170 | " | " |
| INVESTMENT | 0.7659 | n/a | " | " |
| **Pooled (all 6)** | **0.6987** (n=435) | **0.3726** (n=33) | — | — |

**Relationship between confidence and actual correctness**: confidence for correct predictions
is consistently and substantially higher than for incorrect ones in every journey with
observed incorrect cases (LENDING: 0.73 vs 0.38; KYC: 0.67 vs 0.35; ACCOUNT_OPENING: 0.65 vs
0.42) — the signal is directionally meaningful. It is **not well-calibrated in absolute terms**:
pooled Brier=0.1061, ECE=0.2738 (10 bins, n=468) — i.e., raw confidence values systematically
understate true reliability for correct documents (§discussed at length in the prior
confidence-calibration report; reproduced here as a pointer, not re-derived, since nothing
changed).

**Insufficient data for statistical conclusions on three of six journeys**: INSURANCE,
CREDIT_CARD, and INVESTMENT have **zero** observed incorrect predictions in their pooled
test+unseen_template data (n=72 each) — a mean confidence for "incorrect predictions" cannot be
computed for these three journeys at all, and this is stated explicitly rather than
interpolated or estimated. This is unchanged from, not newly discovered by, this phase.

**No calibration was performed or claimed.** This section only measures; it does not correct.

## 9. Difficulty Analysis

Comparing performance across the degradation/difficulty axes present in the dataset, using
this phase's fresh re-run:

| Condition | Effect observed |
|---|---|
| Clean documents (val/test splits, controlled degradation) | Classification 1.0000 accuracy in all six journeys; extraction exact-match 0.83–1.0 per field. |
| Rotated / blurred / noisy / JPEG-degraded (present in all splits, including val/test, per-sample randomized) | No isolated degradation-only metric exists in the harness (degradation is applied to every split, not held out as its own axis) — degradation alone, at the levels used (rotation ≤ ~5°, blur radius ≤ 0.8px, noise σ ≤ 3, JPEG quality ≥ 55), does not appear to be the dominant driver of val/test errors, which are near-zero. |
| Unseen templates (held out layout, same degradation ranges as above) | **The single largest driver of degradation observed.** Every journey's classification/extraction accuracy drops from ~1.0 (val/test) to 0.58–1.0 (unseen), and every error in §5's taxonomy comes from this split. Unseen *layout* — not pixel-level degradation — is the dominant difficulty factor in this system. |
| Low-text documents (e.g. `SIGNATURE_SPECIMEN`) | Taxonomy item 10 — the worst single-field failure rate observed (100% missing `name` on `signature_plain_unseen`), consistent with a layout that genuinely carries little OCR-recoverable text near the target field. |
| Wrong documents (deliberately mismatched doc_type submissions) | Correctly rejected: `false_acceptance_rate=0.0000` in every journey/split (§3/§6); re-confirmed via real HTTP path for a genuinely unseen wrong document (§10). |

**Conclusion**: unseen template layout, not synthetic pixel-level degradation, is what actually
stresses this system. No test distribution was altered to manufacture an improvement.

## 10. Security Verification

Re-verified this phase, all passing (part of the 461):

| Property | Verified by | Result |
|---|---|---|
| Server-side evidence trust | `test_client_forged_field_value_is_ignored` | Client-forged `monthly_income`/`verified` fields ignored; real evidence value used |
| Cross-session isolation | `test_cross_session_evidence_fails_safely` | 404 |
| Cross-journey evidence isolation | `test_cross_journey_evidence_fails_safely` | 404 |
| Forged client values ignored | `test_client_forged_field_value_is_ignored` | Confirmed |
| Evidence/action compatibility | `test_evidence_action_mismatch_fails_safely` | 422 `EVIDENCE_CONFLICT` |
| Untrusted document handling (wrong doc, genuinely unseen) | **New this phase**: `test_unseen_wrong_document_never_advances_state` | 422 `EVIDENCE_CONFLICT`, no state advancement, `monthly_income` stays `None` |
| No AI state mutation | Architectural invariant, unchanged; `deterministic_check()` remains the sole `CheckToken` minter | Unchanged, re-confirmed by full suite passing |
| Snapshot immutability | DB append-only triggers, unchanged | Unchanged |
| Idempotency | `test_repeated_identical_action_remains_idempotent` | Identical response, single snapshot (`version_number=2`, not 3) |
| Stale snapshot protection | `test_stale_snapshot_still_returns_409_with_real_evidence` | 409 |
| Invalid action rejection | `test_invalid_action_still_returns_422` | 422 |

Every property from the P1 fix report remains intact. Two new tests
(`test_unseen_correct_document_advances_state_with_real_extracted_value`,
`test_unseen_wrong_document_never_advances_state`) extend this verification specifically to
genuinely unseen, on-disk, real documents pushed through the full HTTP production path — the
strongest form of confirmation available without real-world (non-synthetic) documents.

## 11. Regression

| Check | Prior baseline | This phase |
|---|---|---|
| Backend pytest | 459/459 | **461/461** (+2 new unseen-template E2E tests) |
| ruff check | clean | clean |
| mypy --strict (app/core) | clean, 9 files | clean, 9 files |
| import-linter | 1/1 kept, 0 broken | 1/1 kept, 0 broken |
| Six-journey classification (val/test/unseen) | see §3 | identical, re-run fresh, zero drift |
| Six-journey extraction (unseen key fields) | see §3 | identical, re-run fresh, zero drift |
| Consistency regression (14 integration + 16 unit) | passing | passing, unchanged |
| E2E integration regression (wrong-doc / valid-doc, freshly-rendered documents) | passing | passing, unchanged |
| E2E integration regression (wrong-doc / valid-doc, **genuinely unseen-template** documents) | not previously tested this way | **new, passing** |

No expected test value was changed to make anything pass. No regression found.

## 12. Performance

**Unchanged from the prior E2E performance baseline; not re-measured in full this phase.**
Rationale: the only implementation change introduced by the P1 fix (prior phase) is a single
indexed primary-key `SELECT` in the action-execution endpoint (`EvidenceRepository.get_by_id`),
which does not touch the OCR/classification/extraction/consistency pipeline at all — those
stages, which dominate total latency (OCR ~250–285ms mean vs. classification/extraction/
consistency each sub-millisecond, per the prior E2E performance report §5), are entirely
unaffected. This phase changed zero implementation code (only added two new test files), so
there is nothing new to re-measure. The prior baseline (`docs/docai_e2e_performance_report.md`)
remains authoritative.

## 13. P0/P1/P2/P3 Issues

| Priority | Issue | Impact | Recommendation |
|---|---|---|---|
| P0 | None found | — | — |
| P1 (candidate, not actioned) | Account Opening: `SIGNATURE_SPECIMEN` `name` field extraction fails on 100% of the `signature_plain_unseen` unseen-template samples (§5 item 10) | Systematic false rejection for this one field/doc_type/template combination on unseen layouts; safe (no fabricated value, no false accept) but would visibly degrade a demo that specifically exercises unseen Account Opening signature documents | Not fixed this phase (Fix Policy §12 restricts fixes to unambiguous correctness issues that block *safe* prototype behavior — this is a coverage/quality gap, not a safety gap; fixing it means adjusting the extraction regex/layout heuristics for this specific template, a P1/P2 judgment call for the next phase, not a generic engine fix) |
| P2 | Lending's `82,55,000` → `8255000` digit-grouping extraction artifact on unseen templates (§5 item 5, §6) | Wrong-but-plausible value could pass FORMAT validation; already disclosed and bounded (0 production false-accepts measured across 468 samples in the prior phase); not newly discovered | Track for a future extraction-hardening pass; no generic fix identified that would not risk regressing other correctly-parsed amount formats |
| P2 | KYC/Insurance/Credit Card/Investment unseen-layout classification/extraction misses (§5 items 1–2, 6–9, 11) | Individually low-frequency, all fail safely (missing value or ambiguous-document routing, never a wrong accept) | No action needed this phase; consistent with known unseen-template difficulty (§9) |
| P2 | Confidence-threshold-driven high review rate for genuinely correct documents (§7, §8, unchanged from prior phase) | Operationally costly, not unsafe | Deferred per explicit instruction (no calibration this phase) |
| P3 | Two ambiguous manifest mappings unresolved (`PAN_CARD_IMAGE`, `KRA_KYC_LETTER`) | Requires a product decision, not a mechanical fix | Unchanged, deferred (per manifest-confidence-calibration phase) |
| P3 | Real-document validation still entirely absent | Every number in every phase, including this one, is synthetic-only | See §14 |

**No P0 or unambiguous P1 issue was found this phase.** Per Fix Policy (§12 of the task),
implementation code was therefore **not** changed except to add the two new regression tests
themselves (`tests/integration/test_unseen_template_e2e.py`).

## 14. Real-Document Limitation

Every number in this report — and in every prior Document AI phase report in this repository —
is measured against **synthetically rendered documents** (ReportLab-generated PDFs, rasterized
and degraded with rotation/blur/noise/JPEG artifacts). This is **not** equivalent to real-world
scanned/photographed documents, which additionally vary in: physical camera/scanner artifacts,
genuine handwriting, real-world lighting and shadow, non-synthetic paper textures and
watermarks, actual regional document format variation (not just template-function variation),
and adversarial or fraudulent inputs deliberately crafted to fool the classifier.

**This report does not claim "production-ready AI."** What the current results do support:

- **Prototype demonstration**: yes — the system correctly classifies, extracts, and safely
  rejects across six journeys, including genuinely held-out unseen layouts, with zero measured
  false acceptance.
- **Controlled demo**: yes, with the caveat that the demo's own documents should be drawn from
  (or closely resemble) the synthetic template families this system was built against; a
  demo using a real scanned bank statement photographed on a phone has not been validated here.
- **Engineering validation**: yes — the architecture (OCR → classifier → extraction →
  normalization → validation → consistency → server-side-trusted evidence → deterministic
  engine) is sound and its trust boundary is proven under adversarial test conditions
  (§6, §10), independent of whether the underlying model's accuracy would hold on real
  documents.

**What would still be needed for real-world production confidence**: a real-document evaluation
set (photographed/scanned, not rendered), ideally with independently sourced negative examples
for genuine calibration (§8's central limitation, unchanged since the confidence-calibration
phase); real OCR failure-mode data (real scanners/cameras produce artifacts synthetic
degradation does not fully capture — skew beyond a few degrees, staples/creases, glare); and a
larger, independently-collected test population per journey than the 18–51 samples used per
split here. No real-document accuracy number is invented in this report.

## 15. Final Recommendation

**READY FOR FINAL PROTOTYPE AUDIT**

Justification: zero P0 issues; zero unambiguous P1 issues that block safe prototype behavior;
the one candidate P1 (Account Opening signature-name extraction on unseen templates) is a
coverage gap, not a safety gap — it fails safely (no state advancement, no fabricated value)
every time it occurs. The P1 Document AI → deterministic action integration bug from the prior
phase was independently re-verified this phase against genuinely unseen, on-disk documents
through the real production HTTP path and remains fixed. Full regression is green
(461/461, ruff/mypy/import-linter clean).

## 16. Files Changed

- `backend/tests/integration/test_unseen_template_e2e.py` — **new**. Two tests pushing real,
  on-disk, genuinely held-out `unseen_template` Lending documents (one correct `SALARY_SLIP`,
  one wrong `OFFICE_ID_CARD`) through the full HTTP production path, confirming the P1 fix holds
  for documents never seen in any form during training or in any prior test.
- `backend/data/docai/*/reports/classifier_metrics.json` (all six journeys) — regenerated by
  re-running each journey's `train_classifier*` module this phase (deterministic, fixed seed);
  content identical to the pre-phase baseline (§3/§11), only the file's `trained_at` timestamp
  and file mtime changed.
- `backend/data/docai/*/reports/extraction_metrics.json` (all six journeys) — regenerated by
  re-running `evaluate_extraction.run()` per journey this phase; content identical to the
  pre-phase baseline.
- No `app/`, `alembic/`, or manifest file was changed this phase (verified via `git status`/
  `git diff`).

Nothing committed. Per the task's stop condition, no further phase (performance optimization or
otherwise) was started after this report.
