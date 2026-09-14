# PaytmFlow — Manifest Integrity + Confidence Calibration Audit

Production-quality hardening pass across all six Document AI journeys. No new journey, no AI
architecture redesign, no proprietary LLM introduced. All numbers below are real, measured
against the actual trained classifiers/extraction code/OCR cache — nothing fabricated or
estimated.

## 1. Manifest Integrity

| Issue | Status | Action | Reason |
|---|---|---|---|
| Account Opening: `upload_digital_signature.accepts = ["image/png"]` | **FIXED** | Changed to `accepts: [AADHAAR_FRONT_BACK]` | Unambiguous from TWO independent repository sources: (1) the frozen `contract/openapi.yaml` documents `accepts` as "Allowed doc_type values for EVIDENCE actions" with no stated exception; (2) `frontend/src/screens/Screen06UploadEvidence.tsx:82` reads `action.accepts[0]` and sends it AS the `doc_type` on upload — `image/png` would never have functioned as a real upload. `evidence_mappings` already declares exactly one doc_type routing to this action_id (`AADHAAR_FRONT_BACK`), and its `target_field` (`signature_uploaded`) already exactly matches the action's own `satisfies`. No other candidate value exists anywhere in the manifest. |
| Account Opening: `PAN_CARD_IMAGE` evidence_mappings → `upload_wet_signature` (satisfies `signature_uploaded`, not `pan_authenticated`) | **AMBIGUOUS / DEFERRED** | Left unchanged | The only action that satisfies `pan_authenticated` at all is `verify_pan_for_banking`, a `kind: FORM` action with no `input_schema` and no `accepts` — a manual-entry/instant-DB-check flow with no document-intake path whatsoever. Repointing `PAN_CARD_IMAGE` to it would require converting a FORM into an EVIDENCE action (inventing an `accepts` list and a document-classification target that doesn't exist today) — a business-workflow decision the repository does not establish, not a mechanical fix. |
| Investment: `KRA_KYC_LETTER` evidence_mappings → `upload_cancelled_cheque` (satisfies `bank_account_verified`, not `kra_kyc_validated`) | **AMBIGUOUS / DEFERRED** | Left unchanged | Identical structural situation: the only action satisfying `kra_kyc_validated` is `check_kra_status`, a FORM with no document intake (verified against a database, not a photographed document). No unambiguous EVIDENCE-action target exists. Confirmed via the same fresh re-investigation (manifest + frontend + tests) as the Account Opening cases — `frontend/src/lib/actionInteraction.test.ts` treats `check_kra_status` as a plain generic FORM, with no special document-capture handling. |

No other manifest defect was found or introduced. The generic `PackValidator.validate_evidence_integrity()` mechanism built during the prior integrity-hardening phase was re-run against all six manifests this phase and confirms exactly these two remaining findings — zero new, zero regressed.

## 2. Existing Confidence System

**Formula** (`app/docai/confidence.py`, unchanged this phase):

```
base = ocr_confidence * classification_confidence
penalty = 1.0   if field_found and field_validated
          0.6   if field_found (not validated)
          0.25  if not field_found
confidence = round(min(1.0, max(0.0, base * penalty)), 4)
```

**Confidence sources** (traced through the real code path, `app/ai/local_ml.py`):
- `ocr_confidence` — Tesseract's real mean word confidence for the page (or `1.0` for a genuine
  PDF text layer, which is ground-truth text, not a prediction).
- `classification_confidence` — the trained TF-IDF+LogisticRegression classifier's own softmax
  probability for whichever class it predicted (`classification.probabilities[predicted_doc_type]`
  in `app/docai/classifier.py`), i.e. the model's own top-class confidence.
- `field_found`/`field_validated` — whether the manifest's real target field was extracted at
  all, and whether it passed deterministic FORMAT validation (regex/shape, not a ground-truth
  comparison — deterministic validation never has access to ground truth).

**Why values sit around 0.7–0.8, traced and confirmed against real measured data (§6)**: for a
genuinely correct, fully-validated document, `penalty = 1.0`, so `confidence = ocr_confidence *
classification_confidence` — the PRODUCT of two independently strong (~0.85–0.95) signals. Two
numbers each individually "high" multiply to a number meaningfully lower than either one alone
(e.g. 0.88 × 0.89 ≈ 0.78) purely by arithmetic, not because either signal is actually weak. This
is not a bug — both inputs are real, honest, unfabricated measurements — but it is a systematic
downward bias relative to what "0.78" would suggest about true reliability. Real measured
correct-case confidence means range 0.65–0.77 per journey (§4/§6 table below), consistent with
this arithmetic explanation.

**Current thresholds**: each manifest's own `evidence_mappings[].confidence_threshold`, ranging
0.80–0.90 across the six journeys' 17 total evidence_mappings entries (no two entries share
identical values across journeys by coincidence — each was independently authored per doc_type).

## 3. Calibration Dataset

| Journey | Calibration Data | Test Data | Unseen Data | Leakage Check |
|---|---|---|---|---|
| LENDING | val: 33 real samples (2 target-incorrect) | test: 33 real samples (1 target-incorrect) | unseen_template: 42 real samples (15 target-incorrect) | Disjoint sample_ids and disjoint templates across all 4 splits (verified programmatically, integrity-hardening phase §8); this phase performed NO fitting against test/unseen_template — see §4 |
| INSURANCE | val: 21 | test: 21 | unseen_template: 30 | Same |
| KYC | val: 21 | test: 21 | unseen_template: 30 | Same |
| CREDIT_CARD | val: 21 | test: 21 | unseen_template: 30 | Same |
| ACCOUNT_OPENING | val: 21 | test: 21 | unseen_template: 30 | Same |
| INVESTMENT | val: 21 | test: 21 | unseen_template: 30 | Same |

**Critical finding driving §4's conclusion**: pooling all six journeys' `val` splits together
yields only **2 target-incorrect examples out of 120**; `test` yields only **1 out of 120**. The
overwhelming majority of real errors (30 of 33 total, 91%) are concentrated in
`unseen_template` — which the explicit instructions for this phase forbid calibrating on or
letting contaminate final metrics. This is not a design choice made this phase; it is a
property of the datasets as they already exist from each journey's own phase (deliberately
held-out unseen templates being harder, matching every journey's own report).

**Conclusion: no statistically meaningful independent calibration split can be constructed from
the current data without either (a) violating the leakage constraint by drawing from
unseen_template, or (b) fitting/validating a model against 1–2 negative examples, which would
not learn anything real and would risk exactly the "confident garbage" failure mode this task
explicitly warns against.** This limitation is stated explicitly rather than worked around.

## 4. Calibration Results

**No calibration model was fit or applied this phase** — the data does not support it (§3). "Before" and "After" are therefore identical; reported here as the real, current, measured system behavior (test + unseen_template splits pooled per journey, 468 real samples total across all six journeys):

| Journey | Before | After | ECE/Brier if valid | False Accepts | False Rejects (needs-review though correct) |
|---|---|---|---|---|---|
| LENDING | mean conf. correct=0.7323, incorrect=0.3822 | *(unchanged — no calibration applied)* | Brier=0.0985 (n=108); ECE not computed per-journey — n too small to bin meaningfully at 10 buckets | **0** | 69/90 correct cases (76.7%) land below threshold → NEEDS_REVIEW |
| INSURANCE | mean conf. correct=0.6801, no incorrect cases observed | *(unchanged)* | Brier=0.1097 (n=72) | **0** | 67/72 (93.1%) |
| KYC | mean conf. correct=0.6693, incorrect=0.3470 | *(unchanged)* | Brier=0.1172 (n=72) | **0** | 58/60 (96.7%) |
| CREDIT_CARD | mean conf. correct=0.6796, no incorrect cases observed | *(unchanged)* | Brier=0.1123 (n=72) | **0** | 69/72 (95.8%) |
| ACCOUNT_OPENING | mean conf. correct=0.6497, incorrect=0.4170 | *(unchanged)* | Brier=0.1435 (n=72) | **0** | 66/69 (95.7%) |
| INVESTMENT | mean conf. correct=0.7659, no incorrect cases observed | *(unchanged)* | Brier=0.0594 (n=72) | **0** | 55/72 (76.4%) |
| **Pooled (all 6)** | correct mean=0.6987 (n=435), incorrect mean=0.3726 (n=33) | *(unchanged)* | **ECE=0.2738, Brier=0.1061** (n=468, 10 bins) | **0** | 384/435 correct cases (88.3%) below threshold |

`"False Accepts"` here means the strict, production-faithful definition: `target_correct=False`
AND (`result.verified` AND `confidence >= manifest threshold`) — i.e. would this actually have
been accepted as satisfied in production. **Zero such cases occurred in any journey, in any
split, across 468 real measured samples.** (An earlier, looser measurement pass mistakenly used
strict-equality comparison for free-text fields like `employer_name` instead of the same
substring-fuzzy rule `evaluate_extraction.py` itself uses, which inflated apparent "incorrect"
counts to 26 false accepts before the methodology bug was caught and fixed — noted here for
transparency about how this number was actually arrived at, not a claim that was ever reported
externally.)

**The real, quantified problem is the opposite of a safety issue**: 76–97% of genuinely correct
documents (88.3% pooled) compose to a confidence below their manifest's own threshold and are
routed to human review that a well-calibrated system would not require. This is SAFE (0% false
accept) but operationally costly.

## 5. Threshold Analysis

All 17 `confidence_threshold` values across the six manifests sit in 0.80–0.90. Observed
behavior at and around these thresholds, from real measured data:

- **Near-boundary cases (confidence within 0.03 of the threshold)**: 68 such cases in the pooled
  test+unseen data; **every single one is `target_correct=True`** except 6 (all in Lending's
  `OFFER_LETTER`, a value-extraction target, not a boolean one). This means the region right
  around threshold is dominated by correct cases sitting just below (or just above) it — the
  threshold is not "in the noise," it is simply set above where even reliably-correct documents
  score.
- **Effect on correct low-confidence cases**: large and consistent — this is the dominant effect
  measured (§4).
- **Effect on incorrect high-confidence cases**: **none observed** — 0 incorrect cases exceeded
  any threshold in any journey.
- **Effect on NEEDS_REVIEW behavior**: NEEDS_REVIEW is the overwhelming majority outcome for
  genuinely correct evidence today, in every journey — confirmed a real, systemic, cross-journey
  pattern, not a Lending-specific or Insurance-specific artifact.
- **Why the thresholds exist as specific numbers (0.80/0.85/0.90)**: no calibration record or
  measurement was found anywhere in the repository history establishing these as fit to any real
  classifier's output — the most likely, previously-hypothesized (across five of six journeys'
  own phase reports) explanation is that they were authored against `MockAI`'s old
  `min(0.98, threshold + 0.07)` confidence formula, which could reliably clear any threshold up
  to 0.91. This phase's measurements are consistent with, but do not conclusively prove, that
  hypothesis.

**No threshold value was changed this phase.** Changing 17 numbers across six manifests is a
product/business decision about acceptable review-burden vs. residual risk trade-offs that this
task's own instructions reserve for explicit review, not something to silently adjust alongside
a confidence-formula audit. Confidence values remain an internal signal only — no user-facing
score, percentage, or probability was added or exposed anywhere.

## 6. Six-Journey Regression

| Journey | Previous classification (val/test/unseen) | New classification | Previous extraction (unseen key fields) | New extraction | Regression? |
|---|---|---|---|---|---|
| LENDING | 1.0000/1.0000/0.9412 | 1.0000/1.0000/0.9412 | monthly_income 0.875, employer_name 1.0 | 0.875, 1.0 | **No** |
| INSURANCE | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9167, date 0.9722 | 0.9167, 0.9722 | **No** |
| KYC | 1.0000/1.0000/0.9744 | 1.0000/1.0000/0.9744 | name 0.9444, date 0.9444, identifier 0.8056 | 0.9444, 0.9444, 0.8056 | **No** |
| CREDIT_CARD | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9444, date 1.0, income 1.0, identifier 0.75 | 0.9444, 1.0, 1.0, 0.75 | **No** |
| ACCOUNT_OPENING | 1.0000/1.0000/0.9744 | 1.0000/1.0000/0.9744 | name 0.5833, identifier 0.9167, date 1.0 | 0.5833, 0.9167, 1.0 | **No** |
| INVESTMENT | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9722, identifier 0.8889, date 0.9583 | 0.9722, 0.8889, 0.9583 | **No** |

Zero regressions. No classifier was retrained (no dataset or model file changed this phase); the
only functional code change (Part 1's `accepts` fix) affects HTTP-layer action routing, not
classification or extraction, and was verified with dedicated new tests (§7) rather than assumed
safe.

Confidence values themselves are, by definition, unchanged before/after since no calibration was
applied (§4) — reported as identical, not fabricated as "improved."

## 7. Tests

Full backend pytest (dedicated `paytmflow_test` DB via `REQUIRE_POSTGRES=1`): **416/416 passed**
(410 prior + 6 new: `test_docai_confidence.py` gained determinism, two monotonicity, a
bad-evidence-never-outscores-good-evidence, and a documented-root-cause regression test; the
Account Opening test suite gained one new HTTP-level routing test for the fixed
`AADHAAR_FRONT_BACK` case, and its module docstring plus the manifest-integrity known-violations
test were updated to reflect the fix — net: 4 files touched, 1 new test function, several
assertion/docstring corrections). `ruff check app tests`: clean. `ruff format`: clean.
`mypy --strict app/core`: clean, 9 files, unchanged. `lint-imports`: 1/1 kept, 0 broken.

Document AI evaluations: all six journeys' classification and extraction metrics re-run and
matched exactly against pre-phase figures (§6). Manifest integrity: `PackValidator` re-run
against all six manifests, confirms exactly 2 remaining known, disclosed findings (§1) and zero
new ones. Confidence calibration evaluation: 468 real per-sample records captured via the actual
`LocalMLProvider.reconcile_evidence` path against real cached OCR text (§3/§4/§5/§6 of this
report; raw records and analysis scripts kept in this session's scratchpad, not committed to the
repo, since they are a one-off measurement, not a reusable artifact).

Frontend: **not run this phase.** The one functional change (Part 1's manifest fix) alters a
YAML data VALUE within an existing, unchanged wire shape (`openapi.yaml` untouched), and no
frontend fixture references this specific action (grepped, confirmed empty) — the frontend
already routes any `accepts` value generically (`Screen06UploadEvidence.tsx` reads
`action.accepts[0]` without any per-action branching), which is precisely the evidence that
made the fix unambiguous in the first place. Not run rather than run as a guaranteed no-op that
could be misreported as a meaningful "passed."

## 8. Remaining Limitations

- **Synthetic-data limitation**: all six journeys' datasets are synthetic, rendered documents;
  real-world OCR/document variance was never measured against this system.
- **Calibration-data limitation (the central finding this phase)**: val and test splits pooled
  across all six journeys contain only 1–2 target-incorrect examples each — nowhere near enough
  to fit or validate any calibration model (isotonic regression, Platt/sigmoid scaling, or
  temperature scaling) without either learning noise from 1-2 points or drawing on
  unseen_template data reserved for final robustness evaluation. **Additional data that would be
  needed**: meaningfully more negative (incorrect) examples in val/test specifically — either a
  larger synthetic dataset deliberately engineered to include more borderline/degraded-but-still
  labeled cases in val/test (not just in unseen_template), or eventually real production
  evidence with known outcomes, which does not exist in this environment.
- **Confidence-calibration limitation**: the diagnosed root cause (multiplicative composition of
  two sub-1.0 signals) is well-evidenced and documented, but no corrective formula change was
  made this phase, since any such change is itself a form of calibration this phase's own
  evidence says isn't yet safely groundable in data — changing the formula without data to
  validate against would be exactly the "blindly rescale confidence" / "increase confidence just
  because values look low" outcome this task explicitly forbids.
- **Unresolved manifest ambiguity**: `PAN_CARD_IMAGE` (Account Opening) and `KRA_KYC_LETTER`
  (Investment) — both require a genuine product decision (convert an existing FORM action into
  an EVIDENCE action, or introduce a new one) that the repository does not establish.
- **Cross-document consistency persistence limitation** (unchanged from the prior
  integrity-hardening phase): `state_schema` never persists auxiliary fields (name, identifier)
  between evidence submissions for five of six journeys, so the real, unit-tested consistency
  mechanism cannot fire for them even though it is correctly wired for Lending's `monthly_income`.
- **Threshold appropriateness**: strongly suggested by measured evidence (§4/§5) to be set higher
  than where the current, honest confidence signal actually places correct documents — not
  changed this phase pending explicit product review, per instructions.
- **Latency/resource usage**: not measured this phase (consistent with every individual journey
  phase; only Lending's original baseline measurement exists in this repository's history).

## 9. Files Changed

- `backend/app/packs/manifests/account_opening.yaml` — `upload_digital_signature.accepts`
  changed from `[image/png]` to `[AADHAAR_FRONT_BACK]` (§1).
- `backend/app/docai/__init__.py` — scope docstring updated to describe the fix instead of the
  prior "left unfixed" framing; also fixed a pre-existing (unrelated to this phase's edits)
  `SyntaxWarning: invalid escape sequence` in the same docstring block, found while editing it.
- `backend/tests/packs/test_all_manifests.py` — `_KNOWN_ACCOUNT_OPENING_VIOLATIONS` reduced from
  4 to 2 expected violations, matching the now-fixed manifest state; the two removed entries were
  genuinely resolved, not silently dropped (the test still fails loudly if any NEW or different
  violation appears).
- `backend/tests/integration/test_evidence_local_ml_endpoint_account_opening.py` — module
  docstring updated; new `test_aadhaar_front_back_now_routes_correctly_after_accepts_fix` test
  added, proving the fix produces a real `proposed_action_id`/`consequence_preview` at the HTTP
  layer.
- `backend/tests/unit/test_docai_confidence.py` — 5 new regression tests (determinism, 2×
  monotonicity, bad-evidence-never-outscores-good-evidence, and a permanent regression encoding
  the diagnosed root cause of the ~0.7–0.8 confidence range).

Not modified: `app/docai/confidence.py` (no calibration implemented — §3/§4/§8), any
`confidence_threshold` value in any manifest (§5), any classifier/dataset/extraction file, any
frontend file, `contract/openapi.yaml`, any other manifest.
