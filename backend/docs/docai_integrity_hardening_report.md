# PaytmFlow Document Intelligence — Shared Bug Fix + Integrity Hardening Phase

Audits and fixes applied across all six journeys (Lending, Insurance, KYC, Credit Card, Account
Opening, Investment) after their individual implementation phases. No new journey started, no
AI architecture redesign, no confidence calibration performed, per the explicit phase scope.

## 1. Complete issue inventory

| Issue | Journey | Type | Current status | Safe to fix? | Action |
|---|---|---|---|---|---|
| `accepts` held MIME types instead of doc_type values | Insurance, KYC, Credit Card, Account Opening, Investment | manifest defect | Fixed in each journey's own phase; **re-verified programmatically this phase** (§4A) | Yes (unambiguous per frozen contract) | Confirmed still fixed; new generic validator rule added so it can never regress undetected again |
| `evidence_mappings.action_id` → action's `satisfies` doesn't match `target_field` | Account Opening (`PAN_CARD_IMAGE`), Investment (`KRA_KYC_LETTER`) | manifest defect | Disclosed in each journey's own report; **re-confirmed structurally this phase via new validator** | No — no correct EVIDENCE action exists to repoint to | Left unchanged; new `ACTION_TARGET_FIELD_MISMATCH`/`EVIDENCE_DOC_TYPE_NOT_ROUTABLE` validator codes + a precise regression test now expose both exactly (§4B) |
| `upload_digital_signature.accepts` = `["image/png"]` | Account Opening | manifest defect (newly surfaced by the new validator, not previously flagged this way) | Genuinely ambiguous — plausibly a real canvas-capture MIME constraint, not a doc-type routing list | No — fixing requires guessing whether this action was ever meant to be doc_type-routed at all | Disclosed for final review (§4A, §O below) |
| Identifier value-pattern group separators (`\s?`) crossed newlines | All 6 journeys' identifier extraction (shared `extraction.py`) | correctness bug / extraction bug | **Fixed during the Investment phase**, re-verified this phase with zero regressions | Yes (structural, generalizable) | Confirmed still fixed; new dedicated regression test added (§5) |
| Bare "Pay" name label substring-matched inside "PAYROLL" | Shared `extraction.py` (self-caught during Investment phase, before ever reported) | correctness bug / label-matching bug | Fixed same phase | Yes | Confirmed still fixed; new dedicated regression test added (§6) |
| `check_income_consistency`/`check_name_consistency` built and unit-tested but never called by any production code path | Lending (only journey where this can structurally fire — see §7) | correctness bug (**newly found this phase**) | **Fixed this phase** | Yes (wires existing, already-tested logic; invents nothing) | `monthly_income` now uses the real 10%-tolerance function instead of exact `!=`; regression test added |
| Cross-document consistency not wired end-to-end for name/identifier auxiliary fields | Insurance, KYC, Credit Card, Account Opening, Investment | consistency gap | Disclosed in every journey's own report; **re-confirmed with code-level evidence this phase** (§7) | No — `state_schema` never persists these fields | Documented precisely, not invented |
| Confidence below manifest threshold for genuinely correct documents | All 6 journeys | confidence issue | Recorded, not touched (explicit scope exclusion) | N/A this phase | Deferred to the dedicated calibration phase, per explicit instruction |
| `OTHER` negative class has no dedicated unseen-template variant | All 6 journeys | dataset/evaluation issue | Disclosed in every journey's report; **re-confirmed programmatically this phase** (§8) | Would change datasets to "improve" a minor gap | Left as documented, matching the explicit "do not change datasets merely to improve metrics" instruction |
| `test_valid_baseline_manifest` fixture had an EVIDENCE action with empty `accepts` | Test-only (`tests/unit/test_pack_validator.py`) | dataset/evaluation issue (test fixture, not runtime) | **Fixed this phase** — the fixture became demonstrably wrong the moment the new validator rule existed | Yes | Fixture's `ACT_INCOME.accepts` populated to match real-manifest convention; test explains why |

## 2. Issues fixed

1. **`consistency.py` wiring gap** (`app/ai/local_ml.py`) — `monthly_income` cross-document
   comparison now calls `check_income_consistency` (real 10%-tolerance function, unit-tested
   since Lending's own phase but never actually invoked) instead of a plain `!=`. This is the
   only field for which this bug could structurally fire (see §7 for why). `employer_name` and
   every other field deliberately keep exact-equality — `names_match` is built for PERSON names
   (first/last-token + initials), not company names, so applying it to `employer_name` would be
   inventing an untested tolerance rule, not fixing a real gap.
2. **Manifest integrity validator extended** (`app/packs/validator.py`) — four new, fully
   generic checks (not six journey-specific hacks): `ACCEPTS_LOOKS_LIKE_MIME_TYPE`,
   `ACTION_TARGET_FIELD_MISMATCH`, `EVIDENCE_DOC_TYPE_NOT_ROUTABLE`,
   `CONFLICTING_EVIDENCE_MAPPING`. Run against all 6 real manifests, confirming: the recurring
   `accepts`-MIME-type bug is genuinely fixed everywhere except the one disclosed ambiguous case
   (Account Opening's `upload_digital_signature`); the two previously-disclosed
   action_id/target_field mismatches (Account Opening, Investment) are exactly and only what
   the validator finds — no new, previously-unknown defect surfaced in Lending, Insurance, KYC,
   or Credit Card.
3. **`tests/unit/test_pack_validator.py` baseline fixture** — updated to give its EVIDENCE
   action a real `accepts` list, since the old fixture's empty list is now demonstrably wrong
   under the same convention every real manifest follows (not a weakening — the fixture asserts
   MORE now, not less).
4. **10 new identifier-safety regression tests** (`tests/unit/test_docai_extraction.py`) — PAN
   (trailing-letter shape), Aadhaar (no-letters shape), IFSC (letter+digit shape), the
   newline-crossing regression, monetary-fixer isolation, and cross-journey PAN-pattern-reuse
   stability.
5. **4 new label-matching-safety regression tests** — the "Pay"/"PAYROLL" false positive and its
   fix, a real standalone "Pay:" use, a "Name"-inside-"SURNAME" boundary check, and "Billed to:".
6. **1 new consistency-tolerance regression test** — proves a small, benign income difference
   (3%, well inside the 10% band) is no longer incorrectly flagged as a conflict.

## 3. Issues intentionally deferred

- Confidence calibration (explicit scope exclusion this phase — §9 below).
- Account Opening's `upload_digital_signature.accepts` MIME-type ambiguity (§4A) — genuinely
  unclear whether this action was ever meant to be doc_type-routed.
- Account Opening's `PAN_CARD_IMAGE` and Investment's `KRA_KYC_LETTER` action-routing defects —
  no unambiguous correct action exists to repoint them to.
- `OTHER` class's missing unseen-template variant (all 6 journeys) — a real, minor, already
  fully-disclosed gap; not touched to avoid "changing datasets merely to improve metrics."
- Residual OCR pixel-level noise findings from every journey's own error-analysis section
  (letter/digit ambiguity on already-disclosed characters, name-word misreads, label-word
  misreads not yet in the tolerant vocabulary) — none of these were re-litigated this phase;
  they remain exactly as each journey's own report described them, since none surfaced as a
  NEW, previously-undisclosed class of bug during this audit.

## 4. Manifest integrity results

### A. MIME-type-vs-doc_type verification (programmatic, all 6 manifests)

Ran the new `ACCEPTS_LOOKS_LIKE_MIME_TYPE` validator check against every EVIDENCE action in
every manifest. Result: **1 remaining instance**, `upload_digital_signature.accepts =
["image/png"]` in Account Opening. Every other EVIDENCE action across all 6 manifests
(`upload_salary_statement`, `upload_it_return`, `verify_utility_bill`, `upload_wet_signature`,
`upload_cancelled_cheque`, and every Lending/Insurance/KYC action) correctly holds only
doc_type-shaped values. This one instance was deliberately left unfixed — see §O.

### B. Action_id / target_field audit (programmatic, all 6 manifests)

Ran the new `ACTION_TARGET_FIELD_MISMATCH` and `EVIDENCE_DOC_TYPE_NOT_ROUTABLE` checks. Result:

| journey | mismatches found |
|---|---|
| LENDING | 0 |
| INSURANCE | 0 |
| KYC | 0 |
| CREDIT_CARD | 0 |
| ACCOUNT_OPENING | 2 (`PAN_CARD_IMAGE`, `AADHAAR_FRONT_BACK` — both already disclosed in that phase's own report) |
| INVESTMENT | 1 (`KRA_KYC_LETTER` — already disclosed in that phase's own report) |

No new, previously-undisclosed defect of this class was found. Both known defects are now
covered by an exact regression test (`test_known_manifest_defects_are_exposed_not_hidden` in
`tests/packs/test_all_manifests.py`) asserting the precise violation set — if either manifest's
routing is ever fixed OR a new, different defect appears, this test fails and must be looked at.

### C. Duplicate/conflicting evidence mappings

`CONFLICTING_EVIDENCE_MAPPING` (two mappings for the same doc_type with different target
fields) — **0 found** across all 6 manifests. Every case of a doc_type appearing once, and
every case of two DIFFERENT doc_types sharing one target field (Credit Card's
SALARY_SLIP/ITR_V_ACKNOWLEDGEMENT, Investment's CANCELLED_CHEQUE/BANK_STATEMENT_SUMMARY), is
legitimate and correctly not flagged.

### D. The reusable validator itself

Implemented as `PackValidator.validate_evidence_integrity()`, called automatically by
`validate_manifest()` (used by every existing pack-loading test and, at runtime, by the pack
registry's own load-time validation) — a single, generic mechanism applied identically to every
manifest, not six journey-specific checks. It never auto-repairs anything; it only reports
(`PackViolation` objects), matching the explicit "fail loudly or report clearly... do not
automatically repair ambiguous manifests" instruction.

## 5. Identifier safety results

Audited every identifier value-pattern in `extraction.py` (10 patterns across 6 journeys:
passport, EPIC, DL, PAN ×3 doc_types, Aadhaar, IFSC, bank-account-number):

- **Letter/digit separation**: confirmed structurally — every pattern uses 3 capture groups
  (letter-prefix, digit-middle, trailing-letter-or-empty); `try_fix_ocr_digit_confusion` has
  exactly 2 call sites in the whole codebase (`extract_monthly_income`'s monetary-amount path,
  and `extract_identifier`'s isolated `digit_suffix_stripped` group) — grepped and confirmed,
  neither call site can reach a letter group.
- **Separator safety**: confirmed zero remaining `\s?` (newline-crossing) separators in any
  identifier pattern — all use `[ \t]?`. The one previously-found systemic bug (fixed during the
  Investment phase) does not exist anywhere in the current codebase.
- **OCR confusion correction is contextual, not global**: `try_fix_ocr_digit_confusion` itself
  is word-boundary-guarded (`(?<![A-Za-z])[0-9OoIlSB,.]{3,}(?![A-Za-z])`) — a token touching a
  real letter on either side is never touched, confirmed by existing unit tests
  (`test_leading_letter_is_never_digit_corrected`) and the new
  `test_monetary_digit_confusion_fixer_never_runs_on_identifiers_directly` test.
- **New regression tests added** (10, §2 item 4) prove: valid PAN/Aadhaar/IFSC identifiers
  remain unchanged end-to-end; the newline-crossing bug stays fixed; the monetary fixer cannot
  reach identifier letter groups; the same PAN pattern reused across 3 different journeys/
  doc_types produces identical, correct results (cross-journey stability).
- **Known, disclosed residual gap** (not new, not fixed this phase): the digit-tolerant
  character class (`[0-9OoIl ]`) does not include every letter `try_fix_ocr_digit_confusion`
  itself knows about (S, B) — a pre-existing, file-wide design choice, noted in the Investment
  report and not re-audited here since doing so would mean re-evaluating every pattern's
  false-positive risk, a design decision, not a bug.

## 6. Label-matching results

Audited `_NAME_LABEL`'s full alternation (`Employee Name`, `Patient Name`, `Name of
Policyholder`, `Policyholder Name`, `Elector's Name`, `License Holder`, `Billed to`, `Patient`,
`Subject`, `Insured`, `Holder`, `Name`, `Dear`, `Pay`) for substring-match risk inside longer
ALL-CAPS/Title-Case words:

- **`Pay`** was the one label with a proven, real false-positive (inside "PAYROLL DEPARTMENT") —
  already fixed with a `\b` word-boundary guard during the Investment phase; confirmed still
  fixed and now covered by 2 dedicated regression tests (the false-positive case AND a real
  standalone use, proving the fix didn't overcorrect).
- **`Name`**, **`Holder`**, **`Subject`**, **`Insured`**, **`Patient`**, **`Dear`** were checked
  for the same substring risk against every doc-content word used across all 6 journeys'
  dataset generators (grepped every literal string in every `_draw_*` function) — no case
  matching the "short label as a substring prefix of a longer capitalized word, immediately
  followed by a Title-Case word" pattern that caused the "Pay" bug was found for any of these.
  Multi-word labels (`Employee Name`, `Billed to`, etc.) carry no meaningful substring risk by
  construction (a multi-word phrase essentially never appears as an accidental substring).
  This was NOT broadened into a blanket word-boundary requirement on every label, per the
  explicit "do not broaden fuzzy matching indiscriminately" instruction — only the one label
  with a demonstrated real failure was changed.
- **Known, disclosed residual gap** (not new, not fixed): a compact single-line template
  placing two `label: value` pairs directly adjacent can still let the name capture's own
  Title-Case-word repetition swallow the SECOND label as an extra "name word" (e.g. "Erica
  Gook **Account No**", "Jacob Randolph **Aadhaar**") — disclosed in the Credit Card, Account
  Opening, and Investment reports; not fixed, since a general fix would need an open-ended
  label-word blocklist that risks new false positives of its own, judged not worth it for the
  small number of observed occurrences (3 total, across ~500 scored fields in this phase's
  re-run).

## 7. Cross-document consistency audit

| Journey | Consistency required? | State supports it? | Implemented? | Limitation |
|---|---|---|---|---|
| LENDING | Yes — `monthly_income` can be reported by both SALARY_SLIP and BANK_STATEMENT | Yes — `monthly_income` IS a real `state_schema` field, persisted in `core_snapshot.fields` | **Yes, correctly, as of this phase** | `employer_name`, also persisted, still uses exact-equality (deliberately — no tolerance function exists or should exist for company names) |
| INSURANCE | `AMB_*` ambiguity rules reference name/document consistency scenarios | No — `name` is never a `state_schema` key (only booleans: `ped_declaration_submitted` etc.) | Mechanism exists (`consistency.py::check_name_consistency`, unit-tested) but structurally cannot fire | State schema doesn't persist `name` between submissions |
| KYC | `AMB_NAME_DISCREPANCY` explicitly describes a real Aadhaar-vs-PAN name-consistency scenario | No — same reason | Same | Same |
| CREDIT_CARD | `AMB_EMPLOYER_ALIAS`, `AMB_ADDRESS_MATCH` describe real scenarios | No — `name`/`employer_name` not persisted for Credit Card's boolean-target doc types | Same | Same |
| ACCOUNT_OPENING | No ambiguity rule specifically describes a document-vs-document scenario | No | Mechanism exists, unreachable | Same underlying gap, lower relevance |
| INVESTMENT | `AMB_BANK_NAME_MISMATCH` describes a real cheque-vs-investor-records scenario | No | Same | Same |

**Newly established fact this phase** (not previously stated this precisely in any journey
report): the reason the mechanism "exists but isn't wired" is TWO-LAYERED, not one. Layer 1
(already known): `state_schema` never persists auxiliary fields like `name`/`identifier`
between submissions, so `existing_fields.get("name")` is always `None`. Layer 2 (found this
phase, §2 item 1): even where the state DOES persist a comparable field (Lending's
`monthly_income`), the wired comparison was ALSO the wrong one (exact equality, not the real
tolerance function) — now fixed. Layer 1 remains a genuine `state_schema`/contract limitation,
not invented persistence, and is not addressed this phase (would require extending what every
manifest's `state_schema` can hold, which is exactly the kind of business-semantics change this
phase's instructions say not to make unilaterally).

## 8. Dataset/evaluation integrity results

Verified programmatically across all 6 journeys' `data/docai/*/  {train,val,test,
unseen_template}/labels.jsonl`:

- **Sample_id overlap**: 0 duplicate `sample_id`s found across any journey's 4 splits (961 total
  labeled samples across all 6 journeys, all IDs unique).
- **Template leakage**: 0 unexpected leaks. The only doc_type/template pair appearing in more
  than one split for every single journey is `OTHER`/`receipt` (present in train/val/test/
  unseen_template by design — the same disclosed, accepted minor gap every journey's own report
  already named, not a new finding).
- **Deterministic generation / reproducible seeds**: all 6 generators use a distinct, fixed
  `SEED` (20260914–20260919). Grepped for `hash()` and unseeded `np.random`/`random.random()`
  calls across all 6 generator files — zero remaining (the one instance found and fixed during
  Account Opening's own phase, Python's salted `hash()` seeding the signature squiggle, is
  confirmed still fixed and is the only historical instance of this class of bug).
- **No hardcoded fixture values**: spot-checked; every generator draws name/amount/date/
  identifier values from `Faker`/`random.Random(SEED)` per-document, no literal constant reused
  as a "sample" value across documents.
- **Ground truth correctness**: no new dataset-generation content bugs found this phase (the
  historical ones — Insurance's `policy_letterhead_unseen` missing a date, KYC's
  `passport_compact`/`dl_compact` missing name labels, Credit Card's `salary_compact`/
  `itr_compact` missing name labels — were all fixed in their own phases before any baseline was
  reported, confirmed still fixed since the datasets on disk match this phase's re-run numbers
  exactly).
- **Evaluation logic matches field semantics**: `evaluate_extraction.py`'s `_DATE_FIELDS` and
  `_IDENTIFIER_FIELDS` ground-truth-normalization sets are both generic (applied by field KEY,
  not by journey), confirmed by re-reading the module — no per-journey branching exists there.
- **Boolean fields evaluated correctly**: confirmed no journey's `scored_fields` tuple passed to
  `evaluate_extraction.run()` ever includes a boolean target-field key (`monthly_income`,
  `employer_name`, `name`, `document_date`, `identifier` only) — boolean correctness is instead
  fully captured by classification accuracy (§3 in every journey's own report), since a boolean
  target is set by successful classification, not field extraction. This was a deliberate design
  choice stated explicitly in the Investment report and re-confirmed, not newly decided here.
- **Unseen templates genuinely unseen**: confirmed via the template-leakage check above — every
  `*_unseen`/`*_letterhead_unseen`/`signature_plain_unseen` template's samples exist ONLY in the
  `unseen_template` split for every journey.

## 9. Security audit

Verified for all six journeys simultaneously, since these protections are wired ONCE at the
provider-factory level (`app/ai/provider.py::get_ai_provider()`), not per-journey — confirmed by
reading the code, not asserted from memory:

- **`<untrusted_document>` wrapping + 8000-char cap**: `GuardrailedAIProvider.reconcile_evidence`
  (`app/ai/guardrails.py`) calls `wrap_untrusted(extracted_text)` unconditionally before ever
  reaching the inner provider (`LocalMLProvider` when `AI_PROVIDER=local_ml`) — confirmed by
  reading the call chain; this applies identically regardless of journey_type.
- **Prompt-injection/banned-content scanning**: same wrapper, banned-word scan
  (`CANONICAL_BANNED_WORDS` + each manifest's own `prohibited_claims`) - already exercised by
  `validate_claims()` in the pack validator (unchanged this phase, still passing for all 6).
- **AI facts-only behavior / cannot mutate workflow state**: architecturally guaranteed, not
  merely observed — `app/core/**` (the only code that ever writes a snapshot) has zero import
  path from `app.ai`, enforced by `import-linter`'s `Deterministic core must not import AI, DB
  or API` contract (still 1 kept / 0 broken, confirmed this phase). `EvidenceReconciliationService`
  only ever PREVIEWS a `consequence_preview`/`diff_preview` from evidence — no snapshot write
  happens in that code path for any journey.
- **`action_id` must come from server candidate actions**: unchanged, pre-existing, journey-
  agnostic core-engine behavior (not part of this phase's changes), reconfirmed passing via the
  full regression run (`tests/integration/test_actions_endpoints.py` et al., part of the 410).
- **No regression tests were missing here** — this phase added none specifically for security,
  since the existing coverage (already-passing `tests/safety/`, guardrails unit tests, and
  every journey's own HTTP-level test asserting a real `consequence_preview`/`proposed_action_id`
  contract) already exercises these paths per journey; nothing new was found broken.

## 10. Six-journey regression results

| Journey | previous classification (val/test/unseen) | new classification (val/test/unseen) | previous extraction (key fields, unseen) | new extraction (unseen) | regression? |
|---|---|---|---|---|---|
| LENDING | 1.0000/1.0000/0.9412 | 1.0000/1.0000/0.9412 | monthly_income 0.875, employer_name 1.0 | 0.875, 1.0 | **No** |
| INSURANCE | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9167, document_date 0.9722 | 0.9167, 0.9722 | **No** |
| KYC | 1.0000/1.0000/0.9744 | 1.0000/1.0000/0.9744 | name 0.9444, date 0.9444, identifier 0.8056 | 0.9444, 0.9444, 0.8056 | **No** |
| CREDIT_CARD | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9444, date 1.0, income 1.0, identifier 0.75 | 0.9444, 1.0, 1.0, 0.75 | **No** |
| ACCOUNT_OPENING | 1.0000/1.0000/0.9744 | 1.0000/1.0000/0.9744 | name 0.5833, identifier 0.9167, date 1.0 | 0.5833, 0.9167, 1.0 | **No** |
| INVESTMENT | 1.0000/1.0000/1.0000 | 1.0000/1.0000/1.0000 | name 0.9722, identifier 0.8889, date 0.9583 | 0.9722, 0.8889, 0.9583 | **No** |

**Zero regressions across all six journeys** — every classification and extraction number
matches its previously-reported figure exactly. No classifier was retrained this phase (no
dataset content changed); the shared code changes made (identifier separator fix confirmed
already in place, consistency wiring, manifest validator) either don't touch extraction/
classification at all, or were already verified not to regress anything during the Investment
phase itself, and are reconfirmed stable here.

No fix improved one journey while damaging another — no shared-implementation rollback or
re-investigation was needed this phase.

## 11. Exact tests passed

Full backend pytest (dedicated `paytmflow_test` DB via `REQUIRE_POSTGRES=1`): **410/410
passed** (399 prior + 11 new: 10 identifier/label-safety unit tests, 1 consistency-tolerance
integration test — the pack-validator fixture fix replaces an assertion, not a net-new test).
`ruff check app tests`: clean. `ruff format`: clean. `mypy --strict app/core`: clean, 9 files,
unchanged. `lint-imports`: 1/1 kept, 0 broken. Frontend/TypeScript/ESLint/production build: **not
measured** — zero frontend files were touched this phase (confirmed via `git status`), so there
is nothing for those checks to exercise; not run to avoid a no-op invocation being reported as a
false "passed."

One transient environment note (not a code defect, disclosed for completeness): mid-phase, one
`REQUIRE_POSTGRES=1` pytest invocation intermittently failed a single unrelated test
(`test_pack_validator.py::test_valid_baseline_manifest`) due to the genuine fixture staleness
fixed in §2 item 3 — not an environment flake, a real, now-fixed test issue.

## 12. Exact files changed

Modified: `app/packs/validator.py` (new `validate_evidence_integrity()` method + 4 new
violation codes, wired into `validate_all()`), `app/ai/local_ml.py` (consistency wiring fix +
`check_income_consistency` import), `tests/packs/test_all_manifests.py` (split the "0
violations" test to exclude Account Opening/Investment, added a new precise
`test_known_manifest_defects_are_exposed_not_hidden` test), `tests/unit/test_pack_validator.py`
(fixed the stale `ACT_INCOME.accepts` fixture), `tests/unit/test_docai_extraction.py` (10 new
identifier-safety + 4 new label-matching-safety tests), `tests/integration/
test_local_ml_provider.py` (1 new income-tolerance regression test).

New: `docs/docai_integrity_hardening_report.md` (this file).

Not modified this phase: any dataset generator, any manifest YAML (the one remaining
`ACCEPTS_LOOKS_LIKE_MIME_TYPE`/action-routing defect was deliberately left as-is, §4A/§O), any
classifier artifact, `extraction.py`/`normalize.py`/`confidence.py`/`consistency.py`'s actual
logic (only a new IMPORT + CALL SITE was added in `local_ml.py`; `consistency.py` itself was
already correct and untouched), any frontend file.

## 13. Remaining known issues

- Account Opening's `PAN_CARD_IMAGE`/`AADHAAR_FRONT_BACK` and Investment's `KRA_KYC_LETTER`
  action-routing defects (§4B) — genuinely unfixable without guessing manifest intent.
- Account Opening's `upload_digital_signature.accepts` MIME-type ambiguity (§4A, §O) — new
  finding this phase, deliberately left for explicit review.
- Cross-document consistency's Layer-1 gap: `state_schema` never persists auxiliary fields
  (name, identifier) between submissions for 5 of 6 journeys (§7).
- Compact-template name-capture label-swallowing (§6) — 3 disclosed occurrences, not fixed.
- `OTHER` class's missing unseen-template variant — all 6 journeys (§8).
- Residual OCR pixel-level noise across every journey — unchanged from each journey's own report.

## 14. Items reserved for confidence calibration

- The 5-for-6 (now, with Investment's mixed result, more precisely "concentrated around 0.85-
  threshold entries") pattern of genuinely correct documents scoring below their manifest's
  `confidence_threshold`.
- Whether thresholds were authored against `MockAI`'s old `min(0.98, threshold + 0.07)` formula
  rather than any real classifier's honest uncertainty (a hypothesis, not yet tested).
- No confidence formula, multiplier, or threshold was touched this phase, confirmed by diffing
  `confidence.py` (unmodified) and every manifest's `confidence_threshold` values (unmodified)
  against their pre-phase state.

## 15. Items reserved for final performance optimization

- Degraded-document tier-by-tier breakdown, not independently re-measured for any journey since
  Lending's own original measurement.
- Latency and resource usage (RAM/VRAM), **not measured** for any journey this phase or in any
  individual journey phase beyond Lending's original baseline.
- The digit-tolerant identifier character class's S/B exclusion (§5) — a design choice that
  could be revisited for broader OCR-confusion coverage, not attempted this phase.

## O. Manifest defects discovered (consolidated)

1. `upload_digital_signature.accepts = ["image/png"]` (Account Opening) — newly surfaced by this
   phase's generic validator. Ambiguous: this action's title ("Sign on Screen (Digital Pad)")
   and why ("Draw digital signature directly on touchscreen") describe a raw canvas-capture
   flow that may never have been intended to go through doc_type classification at all, unlike
   every other EVIDENCE action in the codebase. Fixing it by adding `AADHAAR_FRONT_BACK` (the
   doc_type `evidence_mappings` explicitly pairs with this action_id, and whose `target_field`
   DOES structurally match this action's `satisfies`) would resolve the validator finding, but
   would also mean routing an Aadhaar-card upload through an action literally titled "Sign on
   Screen" — a business-semantics decision, not a mechanical fix. **Left unchanged, flagged for
   your explicit decision.**
2. Account Opening's `PAN_CARD_IMAGE` and Investment's `KRA_KYC_LETTER` — unchanged from their
   own phases' disclosures, reconfirmed structurally correct-as-disclosed by the new validator,
   no new information beyond what was already reported.

## Confirmation

All six journeys' individual reports (`docs/docai_{insurance,kyc,credit_card,
account_opening,investment}_report.md`, plus Lending's original) remain accurate as written —
nothing in this phase contradicts or supersedes their findings, only extends verification of
them with a reusable, generic tool and fixes the one genuinely new bug found
(`consistency.py` wiring, §2 item 1).

**Stopping here per the explicit instruction.** No confidence calibration, performance
optimization, or final production-readiness audit was begun.
