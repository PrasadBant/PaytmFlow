# PaytmFlow Document Intelligence — KYC Pack

Third journey (after Lending, Insurance) on the shared local Document AI architecture.
Everything below is measured against this run's actual generated dataset/trained artifacts.

## 1. Manifest audit

| Document type | Purpose | Fields to extract | Validation | Evidence action | Existing support (before) | Missing support |
|---|---|---|---|---|---|---|
| `PASSPORT_SCAN` | Satisfies `upload_passport_ovd` → `ovd_document_uploaded` (BOOLEAN) | Classification (primary); auxiliary name, document_date (issue date), passport number | Confidence ≥ 0.85 | `upload_passport_ovd` | None | Everything |
| `VOTER_ID_CARD` | Same target field, via `upload_voter_id_ovd` | Same + EPIC number | Confidence ≥ 0.80 | `upload_voter_id_ovd` | None | Everything |
| `DRIVING_LICENCE` | Same target field - **maps to `upload_passport_ovd`'s action_id**, real manifest fact, not a separate action | Same + DL number | Confidence ≥ 0.80 | `upload_passport_ovd` | None | Everything |

Full action inventory (traced, none invented): **FORM** — `link_pan_record` (no input_schema;
PAN entered manually, not OCR'd - genuinely out of document-AI scope per the manifest),
`capture_liveness_selfie` (routes to existing VIDEO_VERIFICATION component via
`classifyInteraction`'s "liveness" match, zero new work), `validate_gps_location` (generic
FORM), `sign_rekyc_undertaking` (`sign_` prefix → existing CONSENT component). **EVIDENCE**:
`upload_passport_ovd`, `upload_voter_id_ovd`. **CLARIFICATION**: none as a direct kind; 2
`ambiguity_rules` — `AMB_NAME_DISCREPANCY` (name mismatch, TEXT answer) and
`AMB_EXPIRED_DOCUMENT` (OVD > 10 years old, CHOICE answer). Target field is **BOOLEAN**
(`ovd_document_uploaded`), the same shape as Insurance.

**Same class of manifest bug found again**: both `upload_passport_ovd`/`upload_voter_id_ovd`'s
`accepts` listed MIME types instead of doc_type values - identical defect to Insurance's,
confirming this was a systemic authoring pattern across manifests, not a one-off. Fixed
identically (`accepts: [PASSPORT_SCAN, DRIVING_LICENCE]` / `accepts: [VOTER_ID_CARD]`,
matching `evidence_mappings` and the frozen contract).

## 2. Reusability audit

Reused **without any code change**: `ocr.py`, `preprocessing.py`, `normalize.py`,
`confidence.py`, `consistency.py`, `classifier.py`, `train_classifier.py`,
`evaluate_extraction.py`, `build_ocr_cache.py` (all already generalized during the Insurance
phase). `LocalMLProvider`'s BOOLEAN-target-field handling (built for Insurance) worked for
KYC with **zero changes** - confirmed by direct smoke test before writing any new test file.
New, KYC-specific (correctly not shared): `dataset/generate_kyc.py`,
`train_classifier_kyc.py` (thin wrapper). Narrowly extended in `extraction.py`: a new
`extract_identifier()` function (real Indian government ID formats - genuinely new surface,
not present in Lending or Insurance) and doc-type-aware date-label priority (KYC documents
carry 2-3 real dates per page, unlike Insurance's usually-one).

## 3. Dataset

162 documents: **75 train / 21 val / 27 test / 39 unseen_template**, 3 real doc types
(`PASSPORT_SCAN`, `VOTER_ID_CARD`, `DRIVING_LICENCE`), 3 templates each (1 held out per type),
`OTHER`/`UNREADABLE` controls. 0 sample_id overlap across splits; 0 template leakage for the
3 real doc types. No content copied from Lending/Insurance.

Two real dataset-generation bugs found and fixed before any baseline was reported: the
`passport_compact` and `dl_compact` templates rendered the person's name with no label at all
(`f"{name} | DOB {dob}"`) while every other template in the same doc types used a real label -
an unintentional content gap, not a deliberate hard-case design (unlike, say, Lending's
deliberately sparse `id_qr_unseen`); fixed by adding a minimal `"Name: "` prefix, matching
realistic terse-layout conventions.

## 4. Document classification

| split | n | accuracy | macro F1 |
|---|---|---|---|
| val | 21 | 1.0000 | 1.0000 |
| test | 21 | 1.0000 | 1.0000 |
| **unseen_template** | 39 | **0.9744** | 0.9791 |

Per-class (unseen_template): PASSPORT_SCAN precision 0.923/recall 1.000, VOTER_ID_CARD
precision 1.000/recall 0.917, DRIVING_LICENCE and OTHER both 1.000/1.000. Confusion matrix in
`data/docai/kyc/reports/classifier_metrics.json`.

Runtime-safety-aware:

| split | n | correct_rate | false_rejection_rate | false_acceptance_rate | safe_non_answer_rate |
|---|---|---|---|---|---|
| val | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| test | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| unseen_template | 39 | 0.6154 | **0.0000** | **0.0000** | 0.3077 |

**0% false rejection and 0% false acceptance across every split**, the third journey in a row
to hold this property. `safe_non_answer_rate` is higher on unseen_template than Lending's or
Insurance's - the classifier was not automatically retrained with a different architecture to
chase this down further per the explicit instruction ("do not automatically train a new model
if the existing classifier is adequate") - the existing model's safety property holds, so it
was judged adequate.

## 5. Field-level extraction metrics

| Field | val | test | unseen_template | failure count |
|---|---|---|---|---|
| name (exact match) | 0.9444 | 0.9444 | 0.9444 | 3 total |
| document_date (exact match) | 0.8333 | 1.0000 | 0.8889 | 6 total |
| identifier (exact match) | 0.7778 | 0.7778 | 0.8056 | 15 total |

No single "KYC accuracy" number is reported - each of the 3 auxiliary fields is scored
separately, and none are collapsed by document type (the extractors are label-anchored, not
doc-type-output-branched beyond which label vocabulary and value format apply).

## 6. Seen vs unseen-template performance

Classification: 100% seen, 97.44% unseen (2 raw misclassifications, both safely caught as
AMBIGUOUS at runtime, 0% unsafe). Extraction: name and document_date are essentially flat
across seen/unseen; identifier is actually slightly *better* on unseen_template (80.56%) than
val/test (77.78% each) - the val/test failures are concentrated on 2 "compact"-style templates
whose terse formatting turned out harder than the unseen "letterhead" templates' fuller prose.

## 7. Degraded-document performance

Not separately re-profiled by degradation tier this phase (same OCR/extraction mechanism as
Lending, whose tier-by-tier breakdown already established the pipeline's general degradation
behavior) - **not measured** for KYC specifically, stated honestly.

## 8. Error analysis — every failure traced, not guessed

| category | example | fixed this phase? |
|---|---|---|
| Missing name label (dataset content gap) | `passport_compact`, `dl_compact` | ✅ Fixed (dataset regenerated before baseline) |
| Regex bug: name capture bled across a newline onto the next labeled field | "Tiffany Kennedy" captured as "Tiffany Kennedy\nFather's Name" | ✅ Fixed (word separator restricted to same-line whitespace) |
| **Significant bug**: shared amount-context digit-confusion fixer corrupted a genuine identifier letter | Passport series letter "B" → "8" (`try_fix_ocr_digit_confusion` is correct for amounts like "IB0,000", wrong applied to a mixed letter+digit ID) | ✅ Fixed (letter-prefix and digit-suffix captured as separate groups; the fixer now only ever touches the digit group) |
| Missing "Issued:" bare-label variant for passport dates | `passport_compact` | ✅ Fixed |
| Doc-type-unaware date selection (multiple real dates per document) | Passport shows DOB + Issue + Expiry; picking the wrong one silently | ✅ Fixed (`_DATE_LABELS_BY_DOC_TYPE` priority, generic vocabulary preserved as fallback) |
| **Pervasive OCR artifact**: contiguous digit run split by a false inserted space | "G6808811" OCR'd as "G680881 1" - affected the majority of early identifier failures | ✅ Fixed (digit-suffix pattern tolerates embedded spaces, strips and validates exact expected length before accepting) |
| Label-word OCR letter confusion not yet in the fuzzy vocabulary | "Card" → "Gard", "DL" → "OL" | Residual - same disclosed category as Insurance's "Policy Periog", not extended to identifier/date labels this phase |
| Leading identifier letter itself OCR-misread to a digit | Passport series letter "Z" → "2" | Residual - genuine OCR letter-to-digit misread with no letter left to anchor on |
| Residual digit-level OCR noise inside an identifier or date | 1↔4 misread, mid-token space beyond tolerance | Residual - genuine pixel-level noise |

## 9. Security

Unchanged, reconfirmed: `<untrusted_document>` wrapping, 8000-char cap, banned-word scan,
AI-never-mutates-state all intact - no changes made or needed.

## 10. Cross-document consistency

Same disclosed limitation as Insurance: the consistency **mechanism**
(`consistency.py::check_name_consistency`) is real and already unit-tested, but not wired
end-to-end for KYC - the manifest's `state_schema` persists no name/identifier value between
evidence uploads for `existing_fields` to compare against. This is directly relevant here:
`AMB_NAME_DISCREPANCY` explicitly describes a real cross-document name-consistency scenario
(Aadhaar vs PAN), but wiring it requires extending what gets persisted between submissions - a
real, disclosed architecture gap, not invented storage.

## 11. Inference latency / resource usage

Not separately re-profiled this phase (identical mechanism to Lending/Insurance, already
measured there). **Not measured** for KYC specifically.

## 12. Exact files changed

New: `app/docai/dataset/generate_kyc.py`, `app/docai/train_classifier_kyc.py`,
`tests/integration/test_local_ml_provider_kyc.py`,
`tests/integration/test_evidence_local_ml_endpoint_kyc.py`, `docs/docai_kyc_report.md`,
`data/docai/kyc/` (dataset + reports, small files committed, bulk PDFs/JPGs gitignored).
Modified: `app/docai/extraction.py` (new `extract_identifier`, doc-type-aware
`extract_document_date`, name-capture newline-bleed fix, expanded name-label vocabulary),
`app/docai/__init__.py` / `app/ai/local_ml.py` (scope docstrings), `app/packs/manifests/kyc.yaml`
(`accepts` fix), `tests/unit/test_docai_extraction.py` (14 new tests),
`tests/integration/test_local_ml_provider.py` (1 test retargeted from KYC to CREDIT_CARD,
since KYC now has real coverage - not weakened, corrected, same pattern as the Insurance
phase's fix to this same test).

## 13. Tests passed

Full backend pytest (dedicated `paytmflow_test` DB): **377/377 passed** (360 prior + 17 new:
14 unit, 4 provider-level [1 pre-existing test retargeted], 2 HTTP-level). `ruff check app
tests`: clean. `mypy --strict app/core`: clean, 9 files, unchanged. `lint-imports`: 1/1 kept,
0 broken. Frontend not re-run (zero frontend files touched).

## 14. Remaining limitations (honest, not hidden)

- Cross-document name consistency mechanism exists but isn't wired end-to-end (§10).
- Identifier/date label vocabulary isn't fuzzy-OCR-tolerant yet (2 disclosed residual
  failures from this gap - same category as Insurance's).
- Degraded-document tier breakdown and latency/RAM/VRAM not independently re-measured for
  KYC this phase.
- `OTHER` negative class has no dedicated unseen-template variant (same minor gap as the
  other two packs).
- `safe_non_answer_rate` on unseen_template (30.77%) is meaningfully higher than Lending's or
  Insurance's - not investigated further this phase since the safety property (0%/0% false
  accept/reject) holds and no model change was made per the explicit "do not automatically
  retrain" instruction.
