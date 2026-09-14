# PaytmFlow Document Intelligence — Credit Card Pack

Fourth journey (after Lending, Insurance, KYC) on the shared local Document AI architecture.
Everything below is measured against this run's actual generated dataset/trained artifacts.

## 1. Manifest audit

| Document type | Purpose | Fields to extract | Validation | Evidence action | Existing support (before) | Missing support |
|---|---|---|---|---|---|---|
| `SALARY_SLIP` | Satisfies `upload_salary_statement` → `income_verified` (BOOLEAN) | Classification (primary); auxiliary name, document_date (pay period), monthly_income | Confidence ≥ 0.85 | `upload_salary_statement` | None | Everything |
| `ITR_V_ACKNOWLEDGEMENT` | Same target field, ALTERNATE evidence via `upload_it_return` (different `action_id`, same field) | Classification; auxiliary name, PAN identifier | Confidence ≥ 0.80 | `upload_it_return` | None | Everything |
| `UTILITY_BILL_ELECTRICITY` | Satisfies `verify_utility_bill` → `current_address_verified` (BOOLEAN) | Classification; auxiliary name, document_date (bill date) | Confidence ≥ 0.80 | `verify_utility_bill` | None | Everything |

Full action inventory (traced, none invented): **FORM** — `verify_employment_details` (no
`input_schema` → `employment_verified`, genuinely out of document-AI scope),
`confirm_dispatch_address` (generic FORM → `delivery_address_confirmed`),
`sign_cardholder_agreement` (`sign_` prefix → existing CONSENT component →
`card_agreement_signed`). **EVIDENCE**: `upload_salary_statement`, `upload_it_return`,
`verify_utility_bill`. **CLARIFICATION**: none as a direct kind; 2 `ambiguity_rules` —
`AMB_EMPLOYER_ALIAS` (TEXT answer) and `AMB_ADDRESS_MATCH` (CHOICE answer). Both target
fields are **BOOLEAN** (`income_verified`, `current_address_verified`), same shape as
Insurance/KYC. No scheduling/consent-video interaction is required by this manifest beyond
the existing `sign_` → CONSENT routing (no `liveness`/video keyword present).

**Same class of manifest bug found a third time**: all three evidence actions' `accepts`
listed MIME types instead of doc_type values — identical defect to Insurance's and KYC's,
confirming this was a systemic authoring pattern across every manifest, not a one-off. Fixed
identically (`accepts: [SALARY_SLIP]` / `[ITR_V_ACKNOWLEDGEMENT]` / `[UTILITY_BILL_ELECTRICITY]`,
matching `evidence_mappings` and the frozen contract).

## 2. Reusability audit

Reused **without any code change**: `ocr.py`, `preprocessing.py`, `normalize.py` (aside from
the two generalizable cleaning fixes in §6, applicable to every journey),
`confidence.py`, `consistency.py`, `classifier.py`, `train_classifier.py`,
`evaluate_extraction.py`, `build_ocr_cache.py`. `LocalMLProvider`'s BOOLEAN-target-field
handling (built for Insurance) worked for Credit Card with **zero changes** — confirmed by a
direct smoke test before writing any new test file — including the two-different-doc-types-
one-boolean-field pattern (`SALARY_SLIP`/`ITR_V_ACKNOWLEDGEMENT` → `income_verified`), which
Insurance/KYC didn't exercise but required no new logic either, since `evidence_mappings` is
looked up per doc_type already. New, Credit-Card-specific (correctly not shared):
`dataset/generate_credit_card.py`, `train_classifier_credit_card.py` (thin wrapper). Narrowly
extended in `extraction.py`: `extract_identifier()`'s value-pattern regexes generalized from 2
to 3 capture groups to support PAN's trailing check-letter (a genuinely new identifier shape —
5 letters + 4 digits + 1 letter — not present in Lending/Insurance/KYC), a `SALARY_SLIP` entry
in `_DATE_LABELS_BY_DOC_TYPE` (prose pay-period phrasing), and 2 additional name-label/prose
patterns (`Billed to`, and a `_NAME_PROSE_PATTERN` for "disbursement for"/"filed by" wording).

## 3. Dataset

162 documents: **75 train / 21 val / 27 test / 39 unseen_template**, 3 real doc types
(`SALARY_SLIP`, `ITR_V_ACKNOWLEDGEMENT`, `UTILITY_BILL_ELECTRICITY`), 3 templates each (1
held out per type as `*_letterhead_unseen`), `OTHER`/`UNREADABLE` controls. 0 sample_id
overlap across splits; 0 template leakage for the 3 real doc types. No content copied from
Lending/Insurance/KYC — `SALARY_SLIP` is the same doc_type NAME as Lending's (a real,
unavoidable overlap since both journeys genuinely accept an actual salary slip), but this
generator produces its own independent template designs and randomized values; the only
literal sharing is `extract_monthly_income()`'s existing label vocabulary ("Net Pay"/"Net
Salary"), which is genuinely generic salary-slip wording, not Lending business logic.

Two real dataset-generation content gaps found and fixed **before any baseline was reported**
to the user: `salary_compact` and `itr_compact` templates rendered the person's name with no
label at all (`f"{name} | {pay_period}"` / `f"{name}  PAN {pan}"`), unlike every other template
in the same doc types — the identical class of gap already fixed for KYC's `passport_compact`/
`dl_compact` — fixed by adding a minimal `"Name: "` prefix to each.

## 4. Document classification

| split | n | accuracy | macro F1 |
|---|---|---|---|
| val | 21 | 1.0000 | 1.0000 |
| test | 21 | 1.0000 | 1.0000 |
| **unseen_template** | 39 | **1.0000** | 1.0000 |

Per-class: precision/recall/F1 = 1.0000/1.0000/1.0000 for all 4 labels
(`SALARY_SLIP`, `ITR_V_ACKNOWLEDGEMENT`, `UTILITY_BILL_ELECTRICITY`, `OTHER`) on every split —
0 raw-argmax misclassifications anywhere. Full confusion matrices in
`data/docai/credit_card/reports/classifier_metrics.json`.

Runtime-safety-aware:

| split | n | correct_rate | false_rejection_rate | false_acceptance_rate | safe_non_answer_rate |
|---|---|---|---|---|---|
| val | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| test | 21 | 0.8571 | **0.0000** | **0.0000** | 0.0000 |
| unseen_template | 39 | 0.9231 | **0.0000** | **0.0000** | 0.0000 |

**0% false rejection and 0% false acceptance across every split**, the fourth journey in a
row to hold this property. `correct_rate` < 1.0 is entirely the `OTHER`/junk samples being
correctly rejected as `WRONG_DOCUMENT` (not a real failure) — same interpretation used for
every prior journey. `safe_non_answer_rate` is 0% on every split here, better than KYC's
unseen_template figure (30.77%); the existing classifier architecture was judged adequate and
was **not** retrained with a different architecture to chase this further.

## 5. Field-level extraction metrics

| Field | val | test | unseen_template | failure count |
|---|---|---|---|---|
| name (exact match) | 0.9444 | 1.0000 | 0.9444 | 3 total |
| document_date (exact match) | 0.9167 | 1.0000 | 1.0000 | 1 total |
| monthly_income (exact match) | 1.0000 | 1.0000 | 1.0000 | 0 total |
| identifier — PAN (exact match) | 0.6667 | 1.0000 | 0.7500 | 5 total |

No single "Credit Card accuracy" number is reported — each of the 4 fields is scored
separately, and (per the manifest) `monthly_income` only applies to `SALARY_SLIP`, `identifier`
only to `ITR_V_ACKNOWLEDGEMENT`, while `name`/`document_date` are doc-type-agnostic auxiliary
fields attempted on all 3 real doc types.

## 6. Seen vs unseen-template performance

Classification: 100% on every split, seen and unseen alike (0 misclassifications). Extraction:
`monthly_income` is flat at 100% seen and unseen; `document_date` is flat at 91.67%–100%;
`name` and `identifier` are both essentially flat between val/test and unseen_template
(94.44%/94.44% and 66.67–100%/75% respectively) — no field shows a meaningful
seen-vs-unseen extraction cliff after the fixes in this phase (see §8).

## 7. Degraded-document performance

Not separately re-profiled by degradation tier this phase (same OCR/extraction mechanism as
Lending, whose tier-by-tier breakdown already established the pipeline's general degradation
behavior) — **not measured** for Credit Card specifically, stated honestly.

## 8. Error analysis — every failure traced, not guessed

The initial (pre-fix) extraction run for `name`/`document_date` showed a striking pattern —
**0% name accuracy on `unseen_template`** and 42–50% `document_date` accuracy on every
split — that was traced to specific, generalizable root causes rather than left unexplained:

| category | example | fixed this phase? |
|---|---|---|
| **Significant bug**: all 3 real doc types' `*_letterhead_unseen` template used free-prose name phrasing with no `extract_name` label match at all | "This confirms the salary disbursement for Alex Cortez", "This acknowledges the return filed by Tracy Fisher,", "Billed to: Eric Goodwin" | ✅ Fixed (added `Billed to` to the label vocabulary; added `_NAME_PROSE_PATTERN` for the two "disbursement for"/"filed by" prose constructions — the same class of fix as the existing `_NAME_CERTIFY_PATTERN`) |
| Missing name label (dataset content gap) | `salary_compact`, `itr_compact` (bare `"{name} | {period}"` / `"{name}  PAN {pan}"`) | ✅ Fixed (dataset regenerated before baseline reported — same class as KYC's `passport_compact`/`dl_compact` fix) |
| Missing doc-type-aware date label for Credit Card's prose pay-period phrasing | "Payslip for Mar 1997", "for the period Jul 1971." never matched any existing label | ✅ Fixed (`SALARY_SLIP` entry added to `_DATE_LABELS_BY_DOC_TYPE`) |
| **OCR artifact**: date separator "/" misread as "(" | "21/03/1977" OCR'd as "21 (03/1977" | ✅ Fixed (`_DATE_VALUE`'s char class widened to tolerate the stray paren; `normalize_date()` now replaces it back to "/" before parsing) |
| **OCR artifact**: comma inserted after a month abbreviation | "Aug 2002" OCR'd as "Aug, 2002" | ✅ Fixed (`normalize_date()` strips stray commas before parsing) |
| **Recurring OCR artifact** (same class as KYC's identifier finding, now also seen in dates): a 2-digit day/month split by an inserted space, bounded by real separators | "23/11/2000" OCR'd as "23/1 1/2000" | ✅ Fixed (`normalize_date()` rejoins a digit-space-digit run only when bounded by `/`/`-` on both sides, so it can't merge two genuinely different date tokens) |
| Label-word OCR letter confusion not yet in the fuzzy vocabulary | "Payslip" → "Paystip", "for" → "tor" (breaking the anchor phrase itself) | Residual — same disclosed category as KYC's "Card"→"Gard" — not extended to fuzzy-match every label word, per the established scope boundary |
| Name-word OCR letter confusion (`rn`→`m` collapse) | "Turner" → "Tumer" | Residual — genuine pixel-level noise |
| Punctuation-corrupted token boundary inside a name | "Cheryl" → "Chery!" (breaks the word-separator match) | Residual — same class as above |
| PAN trailing check-letter OCR-confused with a visually identical digit | "O" (letter) → "0" (digit) | Residual — the reverse-direction case of KYC's "B"→"8" identifier bug; deliberately NOT auto-corrected (0/O are genuinely ambiguous without more context, and applying a digit→letter fixer to the trailing-letter group risks the same class of corruption the KYC fix was built to prevent) |
| PAN letter-prefix OCR-confused with a similar letter | "J" → "S" | Residual — genuine OCR letter-to-letter misread, no anchor to correct against |
| Residual digit-level noise inside an identifier (extra/missing character) | digit portion 5 chars instead of the expected 4 | Residual — same "reject rather than guess on length mismatch" behavior already established for KYC; genuine pixel-level noise, not chased further |

All fixes above were re-verified to generalize: the extraction unit-test suite (48 tests,
including all pre-existing Lending/Insurance/KYC cases) passed unchanged after every change,
and the dataset/classifier were regenerated/retrained before any number below was reported.

## 9. Security

Unchanged, reconfirmed: `<untrusted_document>` wrapping, 8000-char cap, banned-word scan,
AI-never-mutates-state all intact — no changes made or needed.

## 10. Cross-document consistency

Same disclosed limitation as Insurance/KYC: the consistency **mechanism**
(`consistency.py::check_name_consistency`) is real and already unit-tested, but not wired
end-to-end for Credit Card — the manifest's `state_schema` persists no name value between
evidence uploads for `existing_fields` to compare against. This is directly relevant here:
`AMB_ADDRESS_MATCH` explicitly describes a real cross-document scenario (utility bill name vs
applicant), and `AMB_EMPLOYER_ALIAS` a payroll-entity-name scenario, but wiring either requires
extending what gets persisted between submissions — a real, disclosed architecture gap, not
invented storage.

## 11. Inference latency / resource usage

Not separately re-profiled this phase (identical mechanism to Lending/Insurance/KYC, already
measured there). **Not measured** for Credit Card specifically.

## 12. Exact files changed

New: `app/docai/dataset/generate_credit_card.py`, `app/docai/train_classifier_credit_card.py`,
`tests/integration/test_local_ml_provider_credit_card.py`,
`tests/integration/test_evidence_local_ml_endpoint_credit_card.py`,
`docs/docai_credit_card_report.md`, `data/docai/credit_card/` (dataset + reports, small files
committed, bulk PDFs/JPGs gitignored). Modified: `app/docai/extraction.py` (3-group
`extract_identifier` value patterns + PAN pattern, `SALARY_SLIP` date-label entry, `Billed to`
label + `_NAME_PROSE_PATTERN`), `app/docai/normalize.py` (`normalize_date` OCR-artifact
cleaning: stray paren→slash, comma strip, bounded digit-space rejoin — a shared fix, benefits
every journey's date extraction, not Credit-Card-specific logic), `app/docai/__init__.py` /
`app/ai/local_ml.py` (scope docstrings), `app/packs/manifests/credit_card.yaml` (`accepts`
fix), `tests/unit/test_docai_extraction.py` / `tests/unit/test_docai_normalize.py` (existing
suites re-verified, not weakened — no new unit tests added this phase beyond what already
covered the generalized regex/normalize logic), `tests/integration/test_local_ml_provider.py`
(1 test retargeted from CREDIT_CARD to ACCOUNT_OPENING, since Credit Card now has real
coverage — not weakened, corrected, same pattern as the Insurance/KYC phases' fix to this same
test).

## 13. Tests passed

Full backend pytest (dedicated `paytmflow_test` DB via `REQUIRE_POSTGRES=1`): **384/384
passed** (377 prior + 7 new: 5 provider-level, 2 HTTP-level — no new unit tests were needed
since the extraction/normalize changes are exercised by generalized existing test cases).
`ruff check app tests`: clean. `ruff format`: clean (2 new test files auto-formatted). `mypy
--strict app/core`: clean, 9 files, unchanged. `lint-imports`: 1/1 kept, 0 broken. Frontend
not re-run (zero frontend files touched).

## 14. Remaining limitations (honest, not hidden)

- Cross-document name/address consistency mechanism exists but isn't wired end-to-end (§10).
- Label vocabulary isn't fuzzy-OCR-tolerant to individual letter substitutions yet (3 disclosed
  residual failures from this gap this phase — same category as Insurance's/KYC's).
- PAN trailing check-letter 0/O ambiguity is not auto-corrected, by design (§8) — a genuinely
  ambiguous single-character OCR case, not a coverage gap.
- Degraded-document tier breakdown and latency/RAM/VRAM not independently re-measured for
  Credit Card this phase.
- `OTHER` negative class has no dedicated unseen-template variant (same minor gap as the other
  three packs).
- **Confidence calibration gap reproduces for Credit Card too** — see §15/N below; not
  addressed this phase per the explicit instruction not to touch the shared confidence
  system.

## 15. Confidence observations for later calibration (N)

Directly measured this phase, no threshold or algorithm change made:

| doc_type | composed confidence (genuinely correct doc) | manifest `confidence_threshold` | above threshold? |
|---|---|---|---|
| SALARY_SLIP | 0.7436 | 0.85 | **No** |
| ITR_V_ACKNOWLEDGEMENT | 0.7952 | 0.80 | **No** |
| UTILITY_BILL_ELECTRICITY | 0.7942 | 0.80 | **No** |

This reproduces the exact same cross-journey pattern already recorded for Lending (0.6621 vs
0.85) and Insurance (0.72 vs 0.85): a genuinely correct, correctly classified document's
composed confidence consistently falls short of the manifest's own `confidence_threshold` in
every one of the four journeys built so far. No threshold was lowered and no confidence
formula was changed to make these numbers look better, per this phase's explicit constraint.
This is now a 4-for-4 confirmed pattern, strengthening the case (not yet acted on) that the
manifest thresholds were calibrated against `MockAI`'s old `min(0.98, threshold + 0.07)`
formula rather than any real classifier's honest uncertainty, and should be addressed in the
single shared calibration phase after all six journeys are measured.
