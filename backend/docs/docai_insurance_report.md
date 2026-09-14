# PaytmFlow Document Intelligence — INSURANCE Pack

First non-Lending journey on the shared local Document AI architecture. Everything below is
measured against this run's actual generated dataset/trained artifacts - nothing invented.

## 1. Manifest audit

| Document type | Why required | Fields to extract | Validation | Existing support (before this phase) | Missing support |
|---|---|---|---|---|---|
| `MEDICAL_DISCHARGE_SUMMARY` | Satisfies `submit_ped_records` → `ped_declaration_submitted` (BOOLEAN) | Doc-type classification (primary); auxiliary name/document_date for consistency | Confidence ≥ 0.85 | None | Everything (classifier, extractor, dataset) |
| `HEALTH_CHECKUP_REPORT` | Same target field, alternate evidence | Same | Confidence ≥ 0.80 | None | Same |
| `PREVIOUS_POLICY_COPY` | Same target field, alternate evidence | Same | Confidence ≥ 0.80 | None | Same |

Full action inventory: **FORM** `submit_medical_declaration`, `submit_ped_exemption`,
`schedule_tele_mer` (→ SCHEDULING via existing classifier), `setup_insurance_mandate` (→
CONSENT via `MANDATE`), `accept_insurance_policy` (→ CONSENT via `^ACCEPT_`). **EVIDENCE**:
`submit_ped_records` only. **CLARIFICATION**: none as a direct action kind; 2 `ambiguity_rules`
(`AMB_PRE_EXISTING_ILLNESS`, `AMB_SMOKING_STATUS`). **No video-verification action exists** -
none was invented. `consequence_preview` uses the unchanged deterministic `app/core/simulate.py`.

**Structural difference from Lending, found by tracing the manifest rather than assumed**: all
3 Insurance evidence doc types map to the SAME BOOLEAN target field, not separate MONEY/TEXT
fields. This broke an unexamined assumption in the original (Lending-only) code - see §9.

## 2. Reusability audit (mission task 2)

Reused **without any code change**: `app/docai/ocr.py`, `preprocessing.py`, `normalize.py`,
`confidence.py`, `consistency.py`, `classifier.py` (already journey-parameterized via
`get_classifier(journey_type)`). Generalized (Lending behavior preserved, verified identical
before/after - see §9): `train_classifier.py`, `evaluate_extraction.py`,
`build_ocr_cache.py`. Narrowly extended where genuinely necessary (not duplicated): 2 new
auxiliary extractors (`extract_document_date`, broadened `extract_name` label vocabulary) in
`extraction.py`; one architecture fix in `local_ml.py` for BOOLEAN target fields (§9). New,
Insurance-specific (correctly NOT shared): `dataset/generate_insurance.py` (document content
is inherently per-journey) and `train_classifier_insurance.py` (thin wrapper passing
Insurance's own paths into the shared training function).

## 3. Dataset (mission task 3)

Synthetic, from the real manifest's 3 evidence doc types only - no Lending content anywhere in
this dataset. 3 templates per doc type (2 for train/val/test, 1 reserved exclusively for
`unseen_template`), `OTHER` junk-document negative class, `UNREADABLE` control samples,
degradation (rotation, blur, noise, JPEG compression) applied identically to the Lending
generator's method. Indian names (Faker), ₹/Rs amounts, DD/MM/YYYY dates.

| split | documents |
|---|---|
| train | 75 |
| val | 21 |
| test | 27 |
| unseen_template | 39 |

**Verified**: 0 sample_id overlap across any split pair; 0 template leakage for all 3 real doc
types (the `OTHER` class's single template is reused across splits, same disclosed minor gap
as Lending's). No document/value hardcoded from Lending's fixtures.

Two real dataset-generation bugs found and fixed during this phase (before any number was
reported, not after establishing a baseline): the `policy_letterhead_unseen` template didn't
render a date at all despite ground truth requiring one (fixed by adding the missing line);
none of the template content was ever copied from Lending.

Reproduce: `uv run python -m app.docai.dataset.generate_insurance`, then build the OCR cache.

## 4. Document classification (mission task 4 - reused existing architecture, not retrained
from scratch as a new model)

| split | n | accuracy | macro F1 | macro precision | macro recall |
|---|---|---|---|---|---|
| val | 21 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| test | 21 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| **unseen_template** | 39 | **1.0000** | 1.0000 | 1.0000 | 1.0000 |

0 raw-argmax misclassifications across all 3 splits - genuinely better separation than
Lending's (94.12% unseen_template), plausibly because Insurance's 3 doc types (medical
discharge / health checkup / policy document) have more distinctive vocabulary from each
other than Lending's more similar-looking financial documents; not independently verified
beyond this observation.

Runtime-safety-aware (via `classify()`, what actually ships):

| split | n | correct_rate | false_rejection_rate | false_acceptance_rate | safe_non_answer_rate |
|---|---|---|---|---|---|
| val | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| test | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| unseen_template | 39 | 0.9231 | **0.0000** | **0.0000** | 0.0000 |

The `WRONG_DOCUMENT` outcomes making `correct_rate` < 1.0 are exclusively the `OTHER` junk
samples being correctly rejected (by design, not counted as false anything) - **0% false
rejection and 0% false acceptance across every split, including unseen templates.**

Model: identical TF-IDF(1,2-gram)+LogisticRegression mechanism as Lending, reused via
`train_classifier.py`'s now-parameterized `train_and_evaluate()`, not a separate architecture.

## 5. Field extraction (mission tasks 5-6)

Insurance's evidence_mappings target field is BOOLEAN - there is no money/text VALUE to
extract for the manifest's own workflow purposes (correct classification IS the fact). Scored
fields are therefore the 2 auxiliary facts that support cross-document consistency
(mission Step 8): `name`, `document_date`.

| Field | exact match | coverage | seen-template (val/test) | unseen-template | failure count |
|---|---|---|---|---|---|
| name | val 1.0000, test 1.0000, unseen 0.9167 | val 1.0000, test 1.0000, unseen 0.9444 | 1.0000 avg | 0.9167 | 3 (test:0, unseen:3) |
| document_date | val 0.8333, test 0.8889, unseen 0.8889 | val 0.8889, test 0.9444, unseen 0.9444 | ~0.86 avg | 0.8889 | 8 total across splits |

No document-type-specific breakdown beyond this - both fields are scored identically
regardless of which of the 3 doc types they came from (the extractors are label-anchored, not
per-doc-type-branched).

## 6. Error analysis (mission task 7) - every remaining failure traced, not guessed

| category | example | fixed this phase? |
|---|---|---|
| Reversed label word order ("Date of Report" vs coded "Report Date") | `checkup_summary` template | ✅ Fixed |
| Missing date label entirely (no "Date"-shaped label rendered at all) | `policy_schedule` ("Policy Period:"), `policy_certificate` ("Valid:") | ✅ Fixed (added as recognized labels) |
| Greedy date-value regex captured a two-date range as one bogus span | "18/12/2001 to 05/01/2021" → captured whole string | ✅ Fixed (non-greedy quantifier) |
| Label case mismatch ("insured:" vs "Insured:", "Certify" vs "certify") | `policy_certificate`, `discharge_letterhead_unseen` | ✅ Fixed (scoped case-insensitivity) |
| Eval-methodology bug (normalized ISO date compared against raw DD/MM/YYYY ground truth) | Every document_date sample initially "failed" despite correct extraction | ✅ Fixed (ground truth now normalized identically before comparison) |
| Real dataset-generation bug (ground truth required a date the template never rendered) | `policy_letterhead_unseen` | ✅ Fixed (template updated, dataset regenerated) |
| OCR mid-digit whitespace insertion ("1 976" for "1976") | 2 unseen/val samples | Residual - genuine OCR noise, not a label/logic bug |
| OCR digit misread inside a date ("2tt11975", "41/08/1991") | 2 samples | Residual - genuine OCR noise |
| OCR-confused label word not yet in the fuzzy vocabulary ("Periog" for "Period") | 1 sample | Residual - date labels don't yet use the same fuzzy-OCR-tolerance mechanism as employer suffixes; a disclosed, scoped-out extension, not attempted this phase |
| OCR dropped a letter in a name ("Wiliams" for "Williams") | 1 unseen sample | Residual - genuine OCR noise |
| "No labeled name found" (unseen prose templates) | 3 samples | Residual - free-prose wording variation beyond the "certify that" pattern already added |

None of these were silently compensated for with a hardcoded rule - every fix above is a
generalizable label-vocabulary/regex correction, not a fixture-specific patch, and every
residual is disclosed rather than hidden.

## 7. Cross-document consistency (mission task 8)

The consistency **mechanism** (`app/docai/consistency.py`'s `check_name_consistency`) is real,
deterministic, and already unit-tested (from the Lending phase) - it is not re-implemented or
duplicated for Insurance. **However, it is not yet wired end-to-end for Insurance**: the
current architecture's `existing_fields` (what `LocalMLProvider` compares a new extraction
against) is populated only from the journey's `state_schema` fields, and Insurance's
`state_schema` has no field that persists a previously-extracted name or date across evidence
uploads - `kyc_verified` is a bare boolean with no captured value. Wiring true cross-document
name consistency for Insurance would require extending what gets persisted between evidence
submissions, which is a real, disclosed, out-of-scope-this-phase architecture change, not
something invented or silently skipped. The manifest itself declares no nominee/address field
for Insurance, so no consistency rule was invented for those (per the explicit instruction not
to invent unsupported rules).

## 8. Confidence (mission task 9)

Unchanged mechanism from Lending, explicitly heuristic (OCR confidence × classification
probability × extraction-validation outcome), not statistically calibrated. Low-confidence
extraction correctly flows into `requires_review=True` via the existing, unchanged
`EvidenceReconciliationService` threshold gate - verified live (see §9).

## 9. Real defects found and fixed while building Insurance (not hypothetical)

1. **BOOLEAN-target-field gap in `LocalMLProvider`** (the core architectural fix this phase).
   Traced from the manifest: Lending's evidence_mappings only ever targets MONEY/TEXT fields,
   so `LocalMLProvider.reconcile_evidence` never had to handle a target field with no
   money/text value - it required `any_target_field_extracted` (money/text found) to ever
   report `verified=True`, meaning EVERY correctly-classified Insurance document would have
   been reported unverified forever. Fixed: after successful classification, the target
   field's type is looked up from the manifest; if BOOLEAN, the classification result itself
   satisfies it (`raw_values[target_field] = True`), never fabricated - it's exactly the fact
   that was measured. Verified via `test_correct_medical_document_satisfies_boolean_target_field`
   and `test_alternate_accepted_doc_type_also_satisfies_same_boolean_field`.
2. **Manifest authoring bug**: `submit_ped_records.accepts` listed MIME types
   (`application/pdf`, `image/jpeg`, `image/png`) instead of doc_type values - the frozen
   OpenAPI contract explicitly documents `accepts` as "Allowed doc_type values for EVIDENCE
   actions" (`contract/openapi.yaml` line 568), and Lending's own manifest correctly uses
   doc_type values. This silently broke `consequence_preview`/`diff_preview` computation for
   every Insurance evidence upload (the `proposed_action` lookup in
   `app/evidence/reconcile.py` matches `doc_type` against `accepts`, found nothing, and
   silently produced `consequence_preview=None`) - found only by testing a real upload through
   the actual HTTP endpoint, not from unit-level checks. Not previously caught because no pack
   validator rule cross-checks `evidence_mappings.doc_type` against any action's `accepts`
   list (confirmed by reading `app/packs/validator.py`). **Fixed**: `insurance.yaml`'s
   `accepts` now lists `[MEDICAL_DISCHARGE_SUMMARY, HEALTH_CHECKUP_REPORT,
   PREVIOUS_POLICY_COPY]`, matching the contract and Lending's convention. Verified via
   `tests/packs/` (93/93 still pass) and the HTTP-level test now asserting
   `consequence_preview is not None`.
3. **Cross-journey confidence-threshold finding (significant, disclosed, NOT "fixed" this
   phase)**: composed confidence for a genuinely correct, well-classified Insurance document
   measured 0.72 against `MEDICAL_DISCHARGE_SUMMARY`'s manifest `confidence_threshold` of
   0.85 - meaning `EvidenceReconciliationService` correctly routes it to
   `requires_review=True` rather than auto-accepting, even though it's right. **Confirmed
   this is not Insurance-specific**: the identical pattern reproduces on LENDING (a real
   SALARY_SLIP test document measured composed confidence 0.6621 against its own 0.85
   threshold). Root cause: every manifest's `confidence_threshold` values were evidently set
   against `MockAI`'s old confidence formula (`min(0.98, threshold + 0.07)` - by
   construction, always just barely above its own threshold), not against a real classifier's
   honestly lower, genuinely uncertain probability output. **Not "fixed" by inflating
   confidence** - that would violate the never-fabricate-confidence rule. Disclosed as a real,
   substantive, cross-journey limitation; the correct current behavior (safe fallback to
   review, not a wrong auto-accept) is itself verified by test
   (`test_real_medical_document_upload_through_http_endpoint_with_local_ml` now asserts
   `requires_review is True` honestly, rather than an incorrect `verified is True`).

## 10. Inference latency / resource usage

Not separately re-profiled this phase (same TF-IDF+LogisticRegression + regex mechanism as
Lending, already measured there at sub-millisecond classification/extraction and ~0.27s/doc
Tesseract OCR - no reason to expect materially different per-document cost given the identical
code path and comparable document sizes). Model artifact: `insurance_classifier.joblib`
(same order of magnitude as Lending's, not separately measured in bytes this phase). Training
time: seconds (not precisely timed this run - "not measured" rather than a guess). RAM/VRAM:
not measured this phase (GPU not used; CPU RAM not profiled for this specific run).

## 11. Before/after (this is Insurance's first pass - "before" = 0/no support existed)

| Metric | Before | After |
|---|---|---|
| INSURANCE classifier accuracy (val/test/unseen) | none existed | 1.0000 / 1.0000 / 1.0000 |
| INSURANCE false accept/reject rate | none existed | 0% / 0% across all splits |
| INSURANCE `name` extraction (val/test/unseen) | none existed | 1.0000 / 1.0000 / 0.9167 |
| INSURANCE `document_date` extraction (val/test/unseen) | none existed | 0.8333 / 0.8889 / 0.8889 |
| Boolean evidence documents verifiable at all | No (architectural gap) | Yes |
| `consequence_preview` for Insurance evidence uploads | Always None (manifest bug) | Populated correctly |

## 12. Remaining limitations (honest, not hidden)

- Cross-document name/date consistency mechanism exists but isn't wired end-to-end for
  Insurance (§7) - the manifest's own state_schema has no field to persist an auxiliary value
  between uploads.
- Date-label vocabulary isn't yet fuzzy-OCR-tolerant the way the employer-suffix vocabulary is
  (1 disclosed residual failure from this gap).
- Confidence-threshold mismatch (§9.3) is real and unresolved, reproducible on both journeys
  built so far.
- Latency/RAM/VRAM not independently re-measured for Insurance this phase.
- `OTHER` negative class has no dedicated unseen-template variant (same minor, disclosed gap
  as Lending).

## 13. Files changed

New: `app/docai/dataset/generate_insurance.py`, `app/docai/train_classifier_insurance.py`,
`tests/integration/test_local_ml_provider_insurance.py`,
`tests/integration/test_evidence_local_ml_endpoint_insurance.py`,
`docs/docai_insurance_report.md`, `data/docai/insurance/` (dataset + reports, small files
committed, bulk PDFs/JPGs gitignored per the existing pattern).
Modified: `app/ai/local_ml.py` (boolean-target-field handling + updated scope docstring),
`app/docai/extraction.py` (auxiliary `extract_document_date`, broadened name-label
vocabulary, case-insensitivity fixes), `app/docai/__init__.py` (scope note),
`app/docai/train_classifier.py` / `evaluate_extraction.py` / `dataset/build_ocr_cache.py`
(generalized to accept journey_type/dataset_root parameters, Lending behavior verified
unchanged), `app/packs/manifests/insurance.yaml` (`accepts` fix, §9.2),
`tests/unit/test_docai_extraction.py` (new date-extraction tests + updated key-set
assertions), `tests/integration/test_local_ml_provider.py` (1 test updated to target KYC
instead of INSURANCE, since Insurance now has real coverage - not weakened, corrected).

## 14. Tests passed

- Full backend pytest (dedicated `paytmflow_test` DB): **360/360 passed** (352 prior + 8 new
  Insurance-specific: 4 provider-level, 2 HTTP-level, 2 date-extraction unit tests).
- `ruff check app tests`: clean.
- `mypy --strict app/core`: clean, 9 files, unchanged.
- `lint-imports`: 1/1 contract kept, 0 broken.
- `tests/packs/`, `tests/contract/`, `tests/scenarios/`: 93/93 passed after the manifest fix.
- Frontend: not re-run this phase - zero frontend files were touched (the architecture is
  journey-agnostic by design, already verified working for Insurance's existing UI/fixtures
  in earlier session phases); stated honestly rather than re-claimed without verification.
