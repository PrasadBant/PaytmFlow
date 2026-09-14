# PaytmFlow Document Intelligence — Architecture, Dataset, Training & Evaluation

Status: **LENDING pack, full depth (Phase 1 of the multi-journey rollout).** This document
reports exactly what was built and measured. Nothing below is invented; where something
was not measured or not tested, it says so.

## 1. Architecture

```
uploaded file (PDF/JPEG/PNG)
  -> app/evidence/storage.py       real: magic-byte validation, size cap, SHA-256 dedup (pre-existing)
  -> app/docai/ocr.py              real: PyMuPDF text layer (native PDFs) OR Tesseract 5 OCR
                                    (images / scanned PDFs), with per-line bounding boxes
  -> app/docai/classifier.py       real: TF-IDF + LogisticRegression document classifier,
                                    trained per journey; wrong/ambiguous/unreadable detection
  -> app/docai/extraction.py       real: label-anchored + row-band-aware structured field
                                    extraction, normalized via app/docai/normalize.py
  -> app/docai/confidence.py       real: composed from OCR confidence x classification
                                    confidence x extraction-validation outcome
  -> app/docai/consistency.py      real: cross-document consistency vs already-recorded
                                    journey field values
  -> app/ai/local_ml.py            LocalMLProvider - implements the existing AIProvider
                                    Protocol (app/ai/provider.py), returns
                                    AIInterpretationResult - same shape MockAI/LLMProvider use
  -> app/ai/guardrails.py          UNCHANGED: timeout, schema validation, banned-word scan,
                                    untrusted-content wrapping - applied uniformly to all 3
                                    providers
  -> app/evidence/reconcile.py     UNCHANGED downstream: consequence_preview / diff_preview
                                    computed by app/core/simulate.py, purely deterministic
  -> app/core/*                    UNCHANGED: final workflow-state authority. AI output never
                                    mints a CheckToken, never creates a snapshot, never decides
                                    READY/NOT_READY/NEEDS_REVIEW/DEAD_END directly.
```

**Contract impact: none.** `contract/openapi.yaml`, `EvidenceResponse`, `AIInterpretationResult`,
action semantics, and `app/core`'s import boundaries (enforced by `.importlinter`, verified
clean below) are all unchanged. The only addition to an existing interface is one new
**optional** keyword argument, `ocr_meta`, on `AIProvider.reconcile_evidence` - `MockAI` and
`LLMProvider` both accept and ignore it, so this is additive, not breaking.

## 2. Why this model, not a VLM

Hardware measured on the actual dev machine this was built and evaluated on:
Intel i5-11400H (6c/12t), 15.7 GB RAM, NVIDIA RTX 3050 laptop GPU with **4 GB VRAM**, no
CUDA-enabled ML runtime installed at the start of this work. This rules out running most
open multi-billion-parameter vision-language document models (Qwen2-VL, Donut-large, etc.)
without heavy quantization, and this repo's task - closed-set classification over a small,
manifest-defined `doc_type` list per journey, plus extraction of 1-2 target fields per
document - does not need one. A TF-IDF + logistic-regression classifier and label/layout-
anchored extraction are the appropriate, honestly-evaluable choice for this exact task on
this hardware: sub-millisecond inference, no GPU dependency, fully reproducible training
in seconds. **Not benchmarked** (no time/hardware budget to responsibly evaluate them):
LayoutLMv3, Donut, PaddleOCR/PP-Structure, DocTR. If a future pack's doc_type set is large
or visually ambiguous enough that OCR text alone is insufficient, a layout-aware model is
the next real candidate to evaluate - not a default.

OCR engine: **Tesseract 5.4.0** (`winget install UB-Mannheim.TesseractOCR`), bound via
`pytesseract`. Chosen over PaddleOCR/DocTR for this phase because it installs without a
multi-GB deep-learning runtime, runs entirely on CPU, and was sufficient to reach the
measured accuracy below. Not benchmarked against PaddleOCR/DocTR - that comparison is a
disclosed next step (`app/docai/dataset/generate.py`'s degraded-image dataset makes it a
same-input, drop-in comparison whenever that's prioritized).

## 3. Dataset

**Entirely synthetic.** No real Indian salary slips, bank statements, ID cards, or offer
letters exist anywhere in this repository or were used to build this - a repo-wide search
confirmed zero pre-existing sample documents, and obtaining genuine ones would be a
privacy/licensing problem this project has no path to solve. Every document is fabricated
content (Faker-generated names/companies/amounts) rendered onto deliberately varied
templates via `app/docai/dataset/generate.py`. **This is a disclosed limitation**: measured
accuracy is against synthetic layouts with synthetic degradation, not a guarantee of
real-world scan performance.

Source of truth for doc types: LENDING manifest's `evidence_mappings`
(`app/packs/manifests/lending.yaml`) - `SALARY_SLIP`, `BANK_STATEMENT`, `OFFICE_ID_CARD`,
`OFFER_LETTER` - not invented.

Each doc_type has **4 visual templates** (different issuer letterheads / field-label
wording / layouts - e.g. SALARY_SLIP's "Net Pay" / "Net Salary Credited" / "Take Home" /
"Net Amount Payable"). **One template per doc_type is reserved exclusively for the
`unseen_template` split** and never appears in train/val/test - this is what the mandatory
unseen-template evaluation actually measures, not a relabeled train sample.

Each sample is rendered twice: a native-text PDF (PyMuPDF text-layer path) and a degraded
JPEG rasterization (random rotation ±3.5°, optional Gaussian blur/noise, JPEG re-compression
at quality 55/70/85) - the JPEG is the primary artifact used for training/evaluation since
it's the harder, more realistic case and is what actually exercises Tesseract OCR (the PDF
text-layer path is separately real but trivially accurate for native-text PDFs).

Also generated: `OTHER` (an unrelated grocery-receipt document, for wrong-document/out-of-
set testing) and `UNREADABLE` (blank/pure-noise images, test split only).

Split sizes (this run, `SEED=20260914`, fully reproducible - a different seed or sample
count changes these numbers, which is the point of generating them rather than hand-typing
a report):

| split | documents |
|---|---|
| train | 115 |
| val | 33 |
| test | 39 |
| unseen_template | 51 |

Reproduce: `uv run python -m app.docai.dataset.generate` then
`uv run python -m app.docai.dataset.build_ocr_cache` (runs real Tesseract OCR once over
every sample and caches text + per-line bounding boxes + confidence).

## 4. Training

`uv run python -m app.docai.train_classifier`

- Model: `TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)` + 
  `LogisticRegression(C=2.0, class_weight="balanced", max_iter=2000, random_state=20260914)`
  (`scikit-learn` 1.9.1).
- No baseline-vs-fine-tuned comparison applies here: there is no pretrained checkpoint being
  fine-tuned - this IS the from-scratch model, trained entirely on the synthetic dataset
  above. The "baseline" in mission Phase 17's sense is the *previous* system (`MockAI`'s
  fixed per-field-type constants), reported in §7 below.
- Versioning: every training run writes `app/docai/models/lending_classifier.meta.json`
  with model version string, dataset seed, train sample count, scikit-learn/Python/platform
  versions, and an ISO timestamp - alongside the `.joblib` artifact itself.
- Reproducibility: fully deterministic given the same dataset (fixed `SEED` in
  `dataset/generate.py`, fixed `random_state` in the classifier).

## 5. Measured results (real, from this run - see `data/docai/lending/reports/*.json` for
full per-class precision/recall/F1 and confusion matrices)

### 5a. Document classification

Raw argmax (`pipeline.predict()` - what a model-to-model comparison should use):

| split | n | accuracy | macro F1 | macro precision | macro recall |
|---|---|---|---|---|---|
| val | 33 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| test | 33 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| **unseen_template** | 51 | **0.9412** | 0.9492 | 0.9600 | 0.9500 |

**Runtime-safety-aware (what actually ships, via `DocumentClassifier.classify()`, which
refuses a confident answer below its probability floor)** - this is the number that
describes real production behavior, and it tells a materially different, more important
story than raw accuracy alone:

| split | n | correct_rate | false_rejection_rate | false_acceptance_rate | safe_non_answer_rate |
|---|---|---|---|---|---|
| val | 33 | 0.9091 | **0.0000** | **0.0000** | 0.0000 |
| test | 33 | 0.9091 | **0.0000** | **0.0000** | 0.0000 |
| unseen_template | 51 | 0.7059 | **0.0000** | **0.0000** | 0.2353 |

`false_rejection_rate` = a genuinely valid document incorrectly refused; `false_acceptance_rate`
= a genuinely wrong/junk document incorrectly accepted as the expected type - these are the
two failure modes that actually matter for a lending workflow, and **both are 0% across all
three splits, including the fully unseen-template split.** On `unseen_template`, the raw
argmax's 3 "misclassifications" (all the same held-out `id_qr_unseen` OFFICE_ID_CARD
template, sparse at only 11-12 recognizable words) are, in the deployed `classify()` path,
already reported as `AMBIGUOUS_DOCUMENT` (their own top predicted probability was 0.29-0.35,
below the 0.45 safety floor) - a safe non-answer, not a wrong one. This is disclosed as a
genuine methodology finding, not spin: the earlier report's raw-94.12%-accuracy framing
understated how safely the system actually behaves. (An initial version of this
runtime-safety evaluation had its own bug - it tested `expected_doc_type="OTHER"` against the
synthetic junk-document class, which is not a real production scenario since no manifest
action ever requests a document of type "OTHER"; fixed by testing junk documents against a
representative real `expected_doc_type` instead, matching what actually happens at runtime.)

### 5b. Field extraction (exact-match accuracy against ground truth; only the manifest's
real target fields are scored - `monthly_income` for SALARY_SLIP/BANK_STATEMENT,
`employer_name` for OFFICE_ID_CARD/OFFER_LETTER)

**BEFORE** (previous baseline, same frozen dataset):

| split | monthly_income exact-match | monthly_income coverage | employer_name exact-match | employer_name coverage |
|---|---|---|---|---|
| val | 0.6667 | 0.8889 | 0.8333 | 0.8333 |
| test | 0.9444 | 1.0000 | 0.9167 | 0.9167 |
| unseen_template | 0.7917 | 0.8750 | 1.0000 | 1.0000 |

**AFTER** (this pass's fixes, IDENTICAL frozen val/test/unseen_template dataset - no
document added, removed, relabeled, or moved into training):

| split | monthly_income exact-match | monthly_income coverage | employer_name exact-match | employer_name coverage |
|---|---|---|---|---|
| val | **0.9444** (+0.2778) | 1.0000 | **0.9167** (+0.0833) | 1.0000 |
| test | 0.9444 (unchanged) | 1.0000 | **1.0000** (+0.0833) | 1.0000 |
| unseen_template | **0.8333** (+0.0417) | 0.8750 | 1.0000 (unchanged) | 1.0000 |

("coverage" = fraction of documents where a value was extracted at all, whether or not it
matched; "exact-match" = fraction where the extracted value exactly equals ground truth.)

**Exact failure counts**: BEFORE, monthly_income had 11 failures across the 3 splits
(18+18+24=60 samples) and employer_name had 3 (12+12+24=48 samples), 14 total. AFTER, 5
monthly_income failures and 1 employer_name failure remain, 6 total - **8 of the original 14
failures fixed** by genuine algorithmic changes (below), not by touching the dataset.

**What was fixed, and how (all generalizable, none dataset-specific)**:

1. **OCR text flattening destroyed label/value association.** `ocr.py`'s Tesseract call
   originally joined every recognized word into one space-separated string, discarding which
   words were on the same printed line. Fixed by grouping words into real lines
   (`OcrLine`, keyed by Tesseract's own block/paragraph/line numbers, carrying real
   top/bottom pixel positions) - this is what made every subsequent fix possible.
2. **Row-band tolerance was a single fixed 18px constant**, tuned to nothing in particular,
   and missed real label/amount pairs whenever a document's rendered row height (which
   varies by template, font, and DPI) exceeded it - the actual measured gaps on failing
   documents ranged from 22px to 36px. Fixed by deriving the tolerance from **each
   document's own measured median line spacing** (`_row_band_tolerance`, 1.5x median gap,
   floor 20px / ceiling 100px) - self-calibrating per document instead of one guessed
   number.
3. **Row-band candidate selection picked the first-found match, not the best one.** When
   a label's own OCR line already contained ANY amount-shaped token (even a bare,
   unmarked one like a transaction-date year), the search stopped there and never
   considered a better candidate elsewhere on the page - e.g. "SALARY CREDIT ... 2010"
   would be accepted over the real "₹76,000" three lines below. Fixed by collecting every
   candidate from both the label's own line and nearby lines into one pool, then ranking
   by (a) comma/currency-marked before bare digit runs, (b) ordinal line-index distance
   from the label (not raw pixel distance - see next point), (c) pixel distance as a final
   tiebreaker.
4. **Pixel-distance ranking used line CENTER, not line TOP, and this was measurably wrong**
   on real failing documents: a label's own OCR bounding box is often taller than a plain
   amount line (extra padding from a longer/wrapped narration), which skews its computed
   center away from its actual text baseline. Two real documents were traced by hand:
   using center-distance picked the WRONG of two candidate amounts (the utility-bill
   figure instead of the salary figure) in both; using top-distance and ordinal-line-index
   picked correctly in both. Fixed by switching to top-anchored distance plus the
   ordinal-index tiebreaker above - a standard technique for tables an OCR engine has
   segmented into separate description/value blocks, not tuned to one document.
5. **The OCR-digit-confusion fixer's safety threshold rejected valid tokens.** A conservative
   guard (`digit_like < len(token) - 2`) meant to avoid mangling real words was miscounting
   comma characters as "not digit-like enough", so a genuinely valid comma-grouped amount
   with one OCR-confused letter (e.g. "l1,54,000") was left uncorrected. Fixed by recognizing
   that the token was already regex-scoped to only digits/commas/known-confusable-letters
   before this function ever sees it, so the substitution is safe unconditionally within
   that scope - restored the digit-fix without reopening the "don't mangle real words" gap
   (a *different*, real bug in the same area, `try_fix_ocr_digit_confusion`'s original
   unconditional-in-2nd-pass version, was caught by this pass's own new unit test and fixed
   with a proper word-boundary guard, `(?<![A-Za-z])...(?![A-Za-z])`).
6. **Employer-suffix matching required an exact literal spelling** ("Pvt Ltd", "Ltd",
   "Limited", "LLP") and had no entry for "Private Limited" at all, so any OCR misread of
   the suffix itself (observed: "Ltd" -> "Lid"/"Lta", "Pvt" -> "Pyt") caused the WHOLE
   employer-name extraction to fail, not just look slightly wrong - a stricter failure mode
   than the income case. Fixed with a small, disclosed per-character OCR-confusion table
   (`_ALPHA_OCR_CONFUSIONS`, t<->i, v<->y, d<->a, l<->1/i - each individually verified
   against this pipeline's own real OCR output, not guessed) used to build a fuzzy-tolerant
   regex for the suffix vocabulary, plus an explicit `Private\s*Limited` alternative. The
   matched suffix is then canonicalized back to its correct spelling (`_CANONICAL_SUFFIX`)
   using the specific alternation branch that matched - never guessing, since the branch
   that fired tells us exactly which correct spelling was intended.
7. **A genuine bug in step 6's own implementation**: `match.lastgroup` was used to identify
   which suffix alternative matched, but it unreliably returned `None` because of how Python's
   `re` module resolves it when an unnamed OUTER capture group encloses the named
   alternation group (the outer group "closes" after the inner one, at the same text
   position, and wins `lastgroup` despite having no name). Found via a direct unit test that
   printed `match.lastgroup` against a known input and got `None` despite a named group
   clearly matching; fixed by reading `match.groupdict()` directly instead.
8. **A narration-code-style bank-statement label ("SAL/<company>") depends on a single thin
   punctuation character surviving OCR**, which it often doesn't under degradation. Widened
   to also accept a dash in place of a slash (`sal\s*[-/]\s*`) - a real, generalizable
   alternate spelling issuers use - while deliberately NOT making the separator fully
   optional, since that would let a bare "sal" match as a substring prefix of any unrelated
   word and trade one narrow failure for a much broader false-positive risk. Cases where OCR
   destroys the separator with no trace at all remain a disclosed residual limitation (3 of
   the 5 remaining `monthly_income` failures, all on this one narration-style template - see
   §6).

### 5c. Wrong-document detection

Exercised functionally (an `OFFER_LETTER` submitted where `SALARY_SLIP` is expected is
correctly flagged, `tests/integration/test_local_ml_provider.py::test_wrong_document_is_
detected_not_silently_accepted` and the HTTP-level
`test_evidence_local_ml_endpoint.py::test_wrong_document_upload_through_http_endpoint_is_
flagged`) and implicitly covered by the classification confusion matrices above (any
misclassified sample IS a wrong-document-detection failure, since the classifier's job in
production is exactly "does this match what was expected"). **Not separately reported as
one isolated wrong-document-only metric** beyond what the confusion matrix already shows -
doing so would double-count the same measurement under a different name.

### 5d. Numeric/date normalization

Not evaluated as an isolated metric separate from field-extraction exact-match (§5b) -
`monthly_income` exact-match IS the normalization-correctness metric here, since the ground
truth is the normalized integer and the extractor's output is compared directly against it
(not against a raw string). Date normalization (`normalize_date`) is unit-tested
(`tests/unit/test_docai_normalize.py`) but not evaluated dataset-wide, since no manifest
target field in LENDING's evidence_mappings is a date - `document_date` is only an auxiliary
label in the dataset, not something the pipeline currently extracts or scores.

## 6. Error analysis (mission Phase 19)

Full machine-readable detail in `data/docai/lending/reports/{classifier,extraction}_metrics.json`.
The 8 fixes made this pass are listed in full in §5b above (not repeated here). Remaining,
honestly-disclosed residual failures (6 total: 5 `monthly_income`, 1 `employer_name`) as of
this run:

| category | example | why not fixed |
|---|---|---|
| OCR digit duplication (2 cases) | "2,55,000" read as "82,55,000"; "1,91,000" read as "11,91,000" under noise/blur degradation | Genuine pixel-level OCR misread, not a regex/logic bug - "correcting" a plausible-looking extra leading digit generically risks silently corrupting a genuinely large, correct amount elsewhere; no safe, generalizable rule distinguishes the two |
| OCR symbol misread as letter (1 case) | A currency-symbol artifact OCR'd as a stray "l" prefix before a valid comma-grouped amount, then legitimately digit-fixed into an extra leading "1" | Not every stray letter before a number is a digit substitution; the character-confusion fix that resolves 8 other cases correctly is, in this one instance, working exactly as designed on a genuinely different underlying OCR error (a dropped/misread currency glyph, not a digit) |
| Destroyed narration separator (3 cases, all `bank_axis_unseen`) | "SAL/<company>" narration where OCR fused the separator away entirely (e.g. "SALISHAW..." with no "/" or space at all) or misread "SAL" itself (observed "SAU") | The dash/slash widening (§5b fix 8) only recovers cases where the separator survived in SOME form; making the label match "sal" as a bare substring prefix (to catch full destruction) would falsely trigger on any unrelated word starting with those letters - a materially worse trade than 3 missed extractions |
| Insufficient text on sparse template (12 cases, unseen_template only) | `id_qr_unseen` OFFICE_ID_CARD template (11-13 recognizable words) | Not a defect in the shipped behavior - see §5a: the deployed `classify()` path already reports these as `AMBIGUOUS_DOCUMENT` (safe non-answer), not a wrong guess; 0% false-accept/false-reject rate holds |

## 6a. OCR robustness across document-quality tiers (mission Phase 2)

Re-sliced the SAME frozen val/test/unseen_template documents (117 real, non-junk samples) by
the degradation actually applied at generation time - no new documents, no re-labeling:

| tier | n | mean OCR confidence | field exact-match accuracy |
|---|---|---|---|
| clean (rotation only, <2.5°, no blur/noise, high JPEG quality) | 14 | 0.9288 | **1.0000** |
| heavy_jpeg_compression (quality<=60) | 9 | 0.9168 | **1.0000** |
| blurred | 45 | 0.9156 | 0.9333 |
| noisy | 35 | 0.9181 | 0.9143 |
| rotated (>2.5°, otherwise clean) | 5 | 0.8950 | 0.8000 |

Reproduce: `uv run python -m app.docai.evaluate_ocr_robustness`. Accuracy degrades in the
expected direction as document quality worsens (clean/low-compression tiers are perfect;
blur and noise cost a few points; rotation is worst but n=5 is too small here to treat as a
precise number - it is directionally consistent with the other tiers, not a strong
standalone claim). No tier shows a *collapse* in OCR confidence (all stay above 0.89), which
is itself evidence the pipeline degrades gracefully rather than catastrophically.

## 6b. Preprocessing experiment: projection-profile deskew - tried, measured, REJECTED

Per mission Phase 2's explicit instruction to try preprocessing improvements but "not simply
make preprocessing more aggressive if it damages clean documents" and measure before/after:
implemented a standard projection-profile skew estimator (`app/docai/preprocessing.py`,
tries a range of small candidate rotation angles and picks the one that maximizes text-row
alignment) to specifically target the weakest tier above (rotated, 80% accuracy).

**Tesseract's own OSD (`image_to_osd`) was tried first and confirmed useless for this**:
directly tested against a real -2.68° rotated sample, it reported "Rotate: 0" - Tesseract's
OSD only detects gross 90°-multiple orientation, not the few-degree skew this pipeline
actually has (a measured fact about Tesseract 5.4.0 in this environment, not an assumption).

**Result of the custom projection-profile deskew: it made OCR measurably WORSE**, not
better, on 53 real rotated documents tested (mean confidence dropped on the large majority;
several documents lost most of their recognized words entirely, e.g. one went from 66 words
recovered to 25, another from 40 to 4). Verified this wasn't simply a sign-convention bug by
trying BOTH rotation directions on one document by hand: baseline (no correction)
confidence 0.8519 beat both "+3.5°" (0.8397) and "-3.5°" (0.8114) corrections. Per this
project's own rule ("if [a change] performs worse, do not force it into production"), this
preprocessing step is **kept in the repository as a documented, measured, rejected
experiment** (`preprocessing.py`, with the full negative result in its own docstring) and is
**intentionally not called** from the live OCR path. The rotated tier's weaker accuracy
remains a genuine, disclosed limitation rather than one covered up by an ineffective fix.

## 7. Baseline comparison: MockAI vs LocalMLProvider

The **actual previous baseline** in this codebase was not a weaker ML model - it was
`MockAI`, which returned a **fixed constant regardless of document content**: every `MONEY`
field extracted as exactly `85000`, every employer field as exactly `"Acme Technologies
India Pvt Ltd"`, image uploads got zero extraction at all (a placeholder string). Its
"accuracy" against varying ground truth is 0% by construction on any document whose actual
value differs from that constant - it was never designed to be measured this way, since it
was explicitly a fixed-output stand-in. `LocalMLProvider` is the first provider in this
codebase that reads the actual uploaded document and reports what's actually different
between documents (verified directly: `tests/integration/test_local_ml_provider.py::
test_correct_document_extracts_real_field_not_a_hardcoded_value` asserts the extracted
value equals the specific randomized amount rendered onto that one document, not a shared
constant).

## 8. Confidence & calibration

`app/docai/confidence.py` composes OCR confidence × classification confidence × an
extraction-outcome penalty - every input is a real, measured signal (Tesseract's own mean
word confidence; the classifier's own predicted probability; whether the target field was
found and passed deterministic plausibility validation). **Calibration (e.g. Expected
Calibration Error) was NOT measured** - there is no labeled "was this confidence level
actually right that often" dataset available in this environment to calibrate against. This
is disclosed rather than a calibration curve being invented.

## 9. Security / guardrails

- All 3 `AIProvider` implementations (Mock, LLM, LocalML) go through the same unchanged
  `GuardrailedAIProvider` - timeout, schema validation, banned-word scan
  (`approved/approval/probability/credit score/eligibility score/readiness score/guaranteed`),
  `<untrusted_document>` wrapping.
- `LocalMLProvider` strips that wrapper's own boilerplate before running the classifier
  (`_strip_untrusted_wrapper`) - documented in-code as *not* a security bypass: a TF-IDF
  classifier and regex extractor have no prompt to be injected into, they can only
  misclassify or fail to extract, both already handled by the confidence/threshold path;
  leaving the wrapper text in would only have been a real train/serve text mismatch.
- File upload validation (magic bytes, 10MB cap, extension allow-list) is pre-existing and
  unchanged (`app/evidence/storage.py`).
- Never fabricates a detected field for a document it doesn't recognize
  (`test_unsupported_journey_returns_safe_not_fabricated_result`,
  `test_wrong_document_upload_through_http_endpoint_is_flagged`).

## 10. Test results (this run)

- Backend pytest (dedicated `paytmflow_test` Postgres DB): **340/340 passed** (302 pre-existing
  + 38 new: 5 docai unit-test files, `test_local_ml_provider.py`,
  `test_evidence_local_ml_endpoint.py`).
- `ruff check app tests`: clean.
- `mypy --strict app/core`: clean, 9 source files, unchanged (docai code lives entirely
  outside `app/core`).
- `lint-imports` (`.importlinter`): 1/1 contract kept, 0 broken - `app/core` still imports
  nothing from `app.ai`/`app.docai`/`app.db`/`app.api`/`app.services`.

## 11. What is NOT yet done (disclosed, not hidden)

- Only LENDING is trained/evaluated. The other five packs use the same pipeline code
  (`get_classifier(journey_type)` returns `None` for them today) and get a safe "not yet
  analyzed" result rather than a guess - extending coverage is a dataset/training exercise
  per pack, not an architecture change.
- `parse_goal`, `select_action`, `explain` on `LocalMLProvider` delegate to `MockAI` -
  out of this mission's document-intelligence scope, disclosed in `local_ml.py`'s docstring,
  not silently passed off as "real local AI".
- OCR engine choice (Tesseract) was not benchmarked against PaddleOCR/DocTR - time/hardware-
  budget limited, disclosed as a next step, not skipped silently.
- Confidence calibration not measured (no ground-truth calibration dataset available).
- Real-world (non-synthetic) document performance is unknown - only synthetic data was
  available to train/evaluate against.

## 12. Reproduction commands

```bash
cd backend
uv sync                                              # installs pytesseract/pillow/scikit-learn/reportlab/faker/joblib
# Tesseract binary (Windows): winget install --id UB-Mannheim.TesseractOCR -e
uv run python -m app.docai.dataset.generate          # regenerate the synthetic dataset
uv run python -m app.docai.dataset.build_ocr_cache   # real OCR pass, cached
uv run python -m app.docai.train_classifier          # trains + evaluates classification
uv run python -m app.docai.evaluate_extraction        # evaluates field extraction
AI_PROVIDER=local_ml uv run uvicorn app.main:app --port 8000 --loop none  # run the real path
uv run pytest tests/unit/test_docai_*.py tests/integration/test_local_ml_provider.py tests/integration/test_evidence_local_ml_endpoint.py -q
```

## 13. Phase 2 hardening: further extraction fixes, OCR benchmark, DL extraction evaluation

### 13a. OCR engine decision (reviewed and accepted)

A small, isolated, per-document-instrumented benchmark (`app/docai/bench_ocr_paddleocr_small.py`)
was run on 8 representative documents (2 per doc_type, spanning near-clean and
blurred+noisy+heavy-compression+rotated), alone (no concurrent pytest/training), with
Tesseract and DocTR re-run on the identical 8 documents for a true apples-to-apples
comparison:

| engine | success | mean latency | median latency | min-max | field accuracy (n=8) |
|---|---|---|---|---|---|
| Tesseract | 8/8 | 0.296s | 0.271s | 0.242-0.443s | 8/8 |
| DocTR | 8/8 | 1.398s | 1.383s | 1.138-1.725s | 8/8 |
| PaddleOCR (`enable_mkldnn=False`) | 8/8 | **22.954s** | 22.792s | 20.842-26.102s | 8/8 |

Text quality was identical across all three engines on this set - the disqualifying factor
is pure latency: PaddleOCR is ~77x slower than Tesseract and ~16x slower than DocTR on this
machine with the required oneDNN-disabled workaround. This also retroactively explains an
earlier full-111-document PaddleOCR run that appeared to hang for ~58 minutes while sharing
the CPU with two other heavy jobs - it was never stuck, it is genuinely this slow (111 x ~22s
alone is already ~40+ minutes). **Decision (accepted): Tesseract remains the primary OCR
engine; DocTR is a measured, viable fallback; PaddleOCR is rejected for this interactive
pipeline** - not retested further per explicit instruction, unless a future requirement
specifically demands it.

### 13b. Further extraction fixes (frozen dataset unchanged)

Traced the 6 residual failures from Section 6 in detail. One additional generalizable root
cause was found and fixed: the bank-statement narration-code label ("SAL/&lt;company&gt;")
was, in 2 of its 4 observed unseen-template failures, being OCR'd as "SAU/&lt;company&gt;" -
a real, observed L-to-U letter misread under degradation, distinct from the already-known
digit confusions. Added `"u"` to the existing per-character `_ALPHA_OCR_CONFUSIONS` table
(used to build fuzzy-tolerant label/suffix patterns via `_fuzzy_literal`) and rebuilt the
"SAL" narration-code label as fuzzy-tolerant rather than a hardcoded literal - a small,
disclosed, generalizable extension of the same mechanism already used for the employer-suffix
fix, not a new hack.

**Measured result** (same frozen val/test/unseen_template dataset, no documents added,
removed, relabeled, or moved into training):

| split | monthly_income BEFORE this fix | monthly_income AFTER |
|---|---|---|
| unseen_template | 0.8333 (20/24) | **0.8750 (21/24)** |
| val, test | unchanged (fix is bank_axis_unseen-specific) | unchanged |

1 of 4 remaining `bank_axis_unseen` failures fixed (0118). The other 3 were traced and
confirmed NOT safely fixable without overfitting: 2 have the separator destroyed with no
trace at all (0109, 0117 - widening the match to a bare "sal"/"sau" substring prefix would
create a materially worse false-positive risk on unrelated words, rejected as a trade), and
1 (0119) is pure OCR digit duplication ("82,55,000" for "2,55,000"), unrelated to label
matching at all.

### 13c. Dataset quality audit (mission task 5)

Programmatically verified against the actual generated `labels.jsonl` files (not asserted):

- **Split contamination**: 0 sample_id overlap between any pair of {train, val, test,
  unseen_template} - verified by direct set intersection, all pairs empty.
- **Template leakage** (a template used for `unseen_template` also appearing in
  train/val/test): **0** for all 4 real Lending doc types. One deliberate, disclosed
  exception: the synthetic `OTHER` (junk-document) negative class reuses its single
  "receipt" template across every split, since it exists only to teach wrong-document
  detection and was never given its own held-out unseen variant - a known, minor scope gap,
  not a leak affecting the actual field-extraction or real-doc-type classification
  evaluation.
- **Value duplication**: 88/88 employer names unique; 207/208 person names unique (1 natural
  Faker collision); 93 distinct income values across 120 records - collision rate consistent
  with random sampling from a ~232-value range (expected under the birthday paradox), not
  evidence of templated/copy-pasted content.
- **Unseen-template coverage**: confirmed structurally and empirically - one template per
  real doc_type (`salary_takehome`, `bank_axis_unseen`, `id_qr_unseen`,
  `offer_letterhead_unseen`) is generated exclusively for `unseen_template` and never for
  train/val/test.
- **OCR corruption diversity**: already characterized by degradation tier in Section 6a
  (clean, blurred, noisy, rotated, heavy JPEG compression), each independently measurable.

No dataset generator changes were made this pass beyond the label-pattern code fix in 13b -
the dataset itself was judged sufficiently clean and diverse for its stated (synthetic,
disclosed) scope.

### 13d. DL field-extraction evaluation (mission task 4) - REJECTED

Evaluated a lightweight, pretrained, open-source extractive question-answering model,
`distilbert-base-cased-distilled-squad` (66M params, Apache-2.0, zero-shot - no training
performed or required, since this is a pretrained-model evaluation, not a from-scratch
architecture choice). Chosen over training a token-classification/NER extractor because no
token-level BIO-labeled training data exists for this task, and building one would be a
substantial new annotation project, not a "lightweight evaluation" of an existing model.

A real API break was found and fixed along the way: `transformers` 5.17.0 (installed in the
isolated bench venv) removed the `"question-answering"` high-level pipeline task alias
entirely (`KeyError: "Unknown task question-answering"`, confirmed directly, not assumed) -
worked around by calling `AutoModelForQuestionAnswering`/`AutoTokenizer` directly with manual
span decoding, the standard lower-level equivalent.

Tested on the same 8-document representative subset used for the OCR benchmark, alone, with
per-document progress output:

| approach | monthly_income exact-match (n=4) | employer_name exact-match (n=4, corrected) | mean latency |
|---|---|---|---|
| Deterministic baseline (this pipeline) | 4/4 (100%, matches full-dataset numbers in 5b) | 4/4 (100%) | not separately profiled (regex-level, sub-millisecond) |
| Zero-shot QA (DistilBERT) | **0/4 (0%)** | **1/4 (25%)**, see correction below | 0.034s |

The QA model's raw output initially scored 2/4 on employer_name, but one of those two
"matches" was a scoring-methodology false positive, caught and disclosed rather than left to
stand: the model answered `"Pine"` for a document whose real employer name was `"Rogers
Cunningham and Pineda Technologies Pvt Ltd"` - a short fragment that trivially satisfies a
naive substring-containment check without being a real, usable answer. Corrected count: 1/4
(25%), not 2/4. **Root cause of the monthly_income failure**: the QA model has no notion of
table/layout structure - fed a column of visually-similar numbers (e.g. "66,600 / 933,300 /
1,16,550 / 5,550 / 1,11,000"), it answered with broad, multi-number spans instead of
isolating the one relevant figure, exactly the ambiguity the deterministic extractor's
row-band + ordinal-line-index logic (Section 5b) was specifically built to resolve using real
layout information the QA model discards.

**Decision: rejected.** This is not a hardware-feasibility rejection (it ran comfortably on
CPU, fast) - it is an accuracy rejection: the deterministic baseline is categorically
stronger for this specific structured-field-extraction task. The full 111-document dataset
was deliberately NOT run for this comparison, since the small-sample result (0% and a
corrected 25%, against a 94-100% deterministic baseline) is already unambiguous and running
it further would only confirm the same conclusion at more cost, following the same
judiciousness principle applied to the PaddleOCR benchmark.

### 13e. Confidence, consistency, and security (mission tasks 7-9) - unchanged, reconfirmed

- **Confidence remains explicitly heuristic**, composed from real measured signals (OCR
  confidence x classification probability x extraction-validation outcome -
  `app/docai/confidence.py`) but NOT statistically calibrated - restated here per the
  explicit instruction not to imply otherwise. No calibration was attempted this pass; no
  held-out calibration dataset (confidence-vs-correctness ground truth) exists to calibrate
  against.
- **Cross-document consistency remains fully deterministic**, never delegated to an LLM
  (`app/docai/consistency.py`, wired through `app/ai/local_ml.py` against the journey's
  already-recorded `existing_fields` - the same mechanism verified in
  `test_income_conflict_against_existing_fields_is_flagged`). Unchanged this pass.
- **Security unchanged**: `<untrusted_document>` wrapping, the 8000-char document cap, the
  banned-word scan, and "AI facts only, never mutates state" all remain exactly as
  implemented in the prior phase (`app/ai/guardrails.py`, `app/ai/local_ml.py`) - no changes
  made or needed this pass.

### 13f. Testing (mission task 10)

- 2 new regression tests added for the L-to-U label fix
  (`test_narration_code_label_tolerates_l_to_u_ocr_misread`,
  `test_narration_code_label_still_requires_a_separator` - the latter proving the fix did
  NOT loosen the separator requirement into a false-positive risk).
- Full backend pytest (dedicated `paytmflow_test` DB, run alone): **352/352 passed** (350
  prior + 2 new).
- `ruff check app tests`: clean.
- `mypy --strict app/core`: clean, 9 files, unchanged.
- `lint-imports`: 1/1 contract kept, 0 broken.
- Extraction-specific re-evaluation (`evaluate_extraction.py`) and dataset-quality audit: see
  13b/13c above.
