# PaytmFlow — Cross-Document Consistency Completion (Phase 11)

Wires the real, already-unit-tested consistency mechanism into the production evidence path
for all six journeys, without expanding the public API, touching state_schema, or inventing
any manifest relationship the six manifests don't themselves establish.

## 1. Before/After Consistency Audit

| Journey | Before | After | Production-Wired? |
|---|---|---|---|
| LENDING | `monthly_income`/`employer_name` compared via plain `!=` (fixed to a real 10%-tolerance function in the prior integrity-hardening phase); `name` never compared at all (explicitly `continue`d, discarded) | `monthly_income` unchanged (already fixed); `name` now compared across ANY two evidence uploads in the journey | **Yes** — `monthly_income` cleanly; `name` fires and surfaces, but attaches to `INCOME_MISMATCH` (a topic-mismatched ambiguity_rule — see §4) |
| INSURANCE | `check_name_consistency` existed, fully unit-tested, zero production call sites; `name` was never even retained past extraction | `name` compared across the journey's 3 evidence doc types | **Yes** — fires and surfaces via `AMB_PRE_EXISTING_ILLNESS` (topic-mismatched) |
| KYC | Same as Insurance | `name` compared; `identifier` compared only within the SAME doc_type (re-upload scenario) | **Yes** — `name` fires and surfaces via `AMB_EXPIRED_DOCUMENT` (topic-mismatched) |
| CREDIT_CARD | Same as Insurance | `name` compared across the journey's 3 evidence doc types | **Yes, cleanly** — surfaces via `AMB_ADDRESS_MATCH`, whose own question ("is the utility bill in the name of your spouse...") is genuinely about this exact scenario |
| ACCOUNT_OPENING | Same as Insurance | `name`/`identifier` are detected, compared, and persisted, but no evidence_mappings target_field in this manifest has ANY matching ambiguity_rule | **Detected, never surfaceable** — a real, honest manifest-content limitation, not a bug |
| INVESTMENT | Same as Insurance | `name` compared across the 3 doc types; `identifier` same-doc_type only | **Yes, cleanly** — surfaces via `AMB_BANK_NAME_MISMATCH`, whose question ("confirm primary/secondary holder") is genuinely about this exact scenario |

## 2. Persisted Fields

| Journey | Field | Why Persisted | Used For |
|---|---|---|---|
| All six | `name` | The same real-world fact (a person's name) legitimately appears on multiple, structurally different document types within one journey; comparing it is the core cross-document consistency use case every manifest's own `ambiguity_rules` gesture at | Detecting whether two documents in the same journey plausibly belong to the same person |
| All six (per doc_type) | `identifier::<doc_type>` | An identifier's FORMAT is doc_type-specific (a PAN and an IFSC code are structurally incomparable); scoping the persisted key to the doc_type is what makes a later comparison safe rather than "comparing arbitrary identifiers merely because they look like identifiers" | Detecting whether a re-uploaded/corrected document of the SAME doc_type reports the same identifier as an earlier one |

Both live only in the existing, already-append-only `evidence.extracted_data` JSON column
(`app/db/models.py::EvidenceModel`) — never in `snapshot.fields` (state_schema), never in a
new DB table or column, never in the wire-level `EvidenceResponse`/`EvidenceInterpretation`
schema (`app/schemas/evidence.py`, unchanged, still has no `extracted_data` field at all). No
public API was expanded; this is the "smallest safe internal representation" the state_schema
being intentionally minimal calls for.

## 3. Comparisons Supported

| Field | Normalization | Tolerance | Conflict Behavior |
|---|---|---|---|
| `name` | `names_match` (`app/docai/normalize.py`, unchanged): case/whitespace-insensitive, token-overlap based | Allows 1 non-overlapping token, or matching initials, out of the shorter name's token count | Conflict when token overlap and initials both fail |
| `identifier` | Strip + uppercase (new `check_identifier_consistency`) | **None — exact match only, deliberately** | Conflict on ANY difference after normalization; never fuzzy, per the explicit "do not let genuinely different identities become equal" instruction |
| `monthly_income` | Plain int | 10% relative tolerance (`check_income_consistency`, wired in the prior phase, unchanged this phase) | Conflict beyond 10% |
| `employer_name` | None (pre-existing, unchanged) | None (exact match) | Conflict on any difference — deliberately NOT given `names_match`'s tolerance, since that function is built for person names (first/last-token, initials), not company names |

## 4. Conflict Scenarios

All results below are from REAL runs (`tests/integration/test_cross_document_consistency.py`),
not hand-computed:

- **Matching names** ("SRIJA UPPULURI" vs "Srija Uppuluri", "priya sharma" vs "Priya Sharma",
  "ADITYA RAO" vs "Aditya Rao", "meera nair" vs "Meera Nair", "kevin brooks" vs "Kevin Brooks"):
  **no conflict**, in every journey tested.
- **Formatting differences** (case, whitespace): covered by the same matching-name tests above
  and by dedicated unit tests (`TestNameConsistency::test_whitespace_only_difference_no_conflict`,
  `test_case_only_difference_no_conflict`).
- **Monetary tolerance**: unchanged from the prior phase — `test_small_income_variance_within_
  tolerance_is_not_flagged` (3% difference, no conflict) and `test_income_conflict_against_
  existing_fields_is_flagged` (huge difference, conflict) both still pass.
- **Genuine name conflict**: real, different names ("Rahul Kumar" vs "Srija Uppuluri", "Someone
  Else" vs "Original Applicant", "Different Employee" vs "Original Applicant", etc.) —
  **conflict detected in every journey**; surfaced with the correct ambiguity_id where a
  structural match exists (all six journeys), which is a genuine semantic fit for two of them
  (Credit Card, Investment) and a disclosed topic mismatch for three (Lending, Insurance, KYC);
  never surfaceable at all for Account Opening (no structural match exists).
- **Genuine identifier conflict**: proven via unit tests (`TestIdentifierConsistency`) — exact,
  no-tolerance conflict detection confirmed; production wiring confirmed via
  `test_identifier_conflict_same_doc_type_no_matching_ambiguity_rule` (Investment's
  `KRA_KYC_LETTER`, detected — proven via `auxiliary_facts` — but not surfaced, since
  `kra_kyc_validated` has no ambiguity_rule).
- **Missing field**: `test_missing_prior_fact_no_conflict` — no prior fact recorded → no
  conflict, never treated as a contradiction.
- **Low-confidence/malformed extraction**: `test_malformed_identifier_never_triggers_a_conflict`
  — a too-short/malformed PAN (fails format validation, `field.validated=False`) is never even
  compared, regardless of how different it looks from the prior value; `auxiliary_facts` confirms
  it wasn't even recorded.

## 5. Six-Journey Results

- **LENDING**: matching name → no conflict; conflicting name → detected AND surfaced (attached
  to `INCOME_MISMATCH`, a real but topic-mismatched rule — disclosed limitation, not a safety
  gap, since NEEDS_REVIEW still correctly triggers). `monthly_income`/`employer_name` unchanged
  from the prior phase.
- **INSURANCE**: matching name → no conflict; conflicting name → detected AND surfaced via
  `AMB_PRE_EXISTING_ILLNESS` (topic-mismatched, same caveat).
- **KYC**: matching name → no conflict; conflicting name → detected AND surfaced via
  `AMB_EXPIRED_DOCUMENT` (topic-mismatched, same caveat); identifier comparison scoped
  same-doc_type, structurally available but not specifically exercised by a KYC test this phase
  (no KYC doc type is realistically re-uploaded twice in the existing test flow — mechanism is
  identical to Investment's, already proven).
- **CREDIT_CARD**: matching name → no conflict; conflicting name → detected AND surfaced via
  `AMB_ADDRESS_MATCH` — a genuine semantic fit, the cleanest non-Investment case.
  identifier: `ITR_V_ACKNOWLEDGEMENT`'s PAN is compared same-doc_type only (same mechanism as
  Investment/KYC).
- **ACCOUNT_OPENING**: name conflict is genuinely detected (`auxiliary_facts` proves it) but can
  never be surfaced — no evidence_mappings target_field in this manifest has ANY matching
  ambiguity_rule (`AMB_NOMINEE_RELATION`→`nominee_declared`, `AMB_FATCA_STATUS`→
  `identity_verified`, neither an evidence-driven field). Documented as a real limitation, not
  invented around.
- **INVESTMENT**: matching name (across alternate evidence, `CANCELLED_CHEQUE` →
  `BANK_STATEMENT_SUMMARY`) → no conflict; conflicting name → detected AND surfaced via
  `AMB_BANK_NAME_MISMATCH` — genuine semantic fit. `identifier` same-doc_type comparison proven
  for `KRA_KYC_LETTER` (detected, correctly not surfaced — no matching ambiguity_rule for
  `kra_kyc_validated`).

No journey required inventing a cross-document relationship the manifest doesn't establish;
Account Opening's "no legitimate comparison surfaceable" and every journey's identifier-comparison
scope (same doc_type only) are both documented rather than worked around.

## 6. Tests

Full backend pytest (dedicated `paytmflow_test` DB via `REQUIRE_POSTGRES=1`): **439/439 passed**
(438 prior + 1 new: the low-confidence/malformed-extraction gate test — the 22 other new tests
this phase, 9 unit + 13 integration, were included in the 438 baseline established mid-phase and
reconfirmed in every subsequent run). `ruff check app tests`: clean (1 f-string lint issue found
and fixed during this phase). `ruff format`: clean. `mypy --strict app/core`: clean, 9 files,
unchanged. `lint-imports`: 1/1 kept, 0 broken (the new code lives in `app/ai`/`app/docai`/
`app/evidence`, none of which `app/core` imports).

Document AI: all six journeys' classification and extraction evaluations re-run, matched exactly
against pre-phase figures (§7). Consistency-specific: 9 new unit tests
(`tests/unit/test_docai_consistency.py`, covering `check_identifier_consistency` fully plus 3
new `names_match` edge cases) + 14 integration tests
(`tests/integration/test_cross_document_consistency.py`, covering all six journeys with real
rendered documents, real OCR, real classification, real extraction, and the real
`reconcile_evidence` path).

API/integration: stale-snapshot 409 behavior (`test_actions_endpoints.py`,
`test_clarifications_endpoints.py`, `test_evidence_endpoints.py`), idempotency
(`test_api_actions.py`, `test_db_models_and_triggers.py`, `test_gate_b_d.py`), cross-session
isolation (`test_journeys_endpoints.py`, `test_recommendation_endpoints.py`,
`test_prompt_injection.py`, `test_api_*.py`), and demo reset (`test_system_endpoints.py`) all
confirmed passing as part of the 439 — none of these files were modified this phase.

Frontend: not run. No frontend file was touched, and no wire-level schema changed (confirmed:
`EvidenceResponse`/`EvidenceInterpretation` in `app/schemas/evidence.py` are byte-for-byte
unchanged this phase).

## 7. Regressions

| Journey | Classification (val/test/unseen) | Extraction (unseen key fields) | Changed? |
|---|---|---|---|
| LENDING | 1.0000/1.0000/0.9412 | monthly_income 0.875, employer_name 1.0 | **No** |
| INSURANCE | 1.0000/1.0000/1.0000 | name 0.9167, date 0.9722 | **No** |
| KYC | 1.0000/1.0000/0.9744 | name 0.9444, date 0.9444, identifier 0.8056 | **No** |
| CREDIT_CARD | 1.0000/1.0000/1.0000 | name 0.9444, date 1.0, income 1.0, identifier 0.75 | **No** |
| ACCOUNT_OPENING | 1.0000/1.0000/0.9744 | name 0.5833, identifier 0.9167, date 1.0 | **No** |
| INVESTMENT | 1.0000/1.0000/1.0000 | name 0.9722, identifier 0.8889, date 0.9583 | **No** |

Every number matches the manifest-confidence-calibration phase's own report exactly. No
classifier was retrained, no dataset changed, no extraction/normalization logic touched — this
phase's code changes are additive (new consistency wiring) and confined to `app/ai/local_ml.py`'s
extraction-result-handling loop, `app/evidence/reconcile.py`'s evidence-creation step, and two
small new functions/fields, none of which sit on the classification or extraction code path.

## 8. Remaining Limitations

- **Synthetic-data limitation** (carried forward, unchanged): all six journeys' datasets are
  synthetic, rendered documents; this phase's consistency tests are likewise synthetic — real
  production document pairs (two genuine, independently-scanned documents for the same
  applicant) were never available to test against.
- **Real-document validation still pending**: the same-person/different-person distinction
  relies on `names_match`'s tolerance, tuned and tested only against synthetic Faker-generated
  names; real-world name variation (transliteration, honorifics, married-name changes) was not
  measured.
- **Unresolved ambiguous manifest mappings**: `PAN_CARD_IMAGE` (Account Opening) and
  `KRA_KYC_LETTER` (Investment) remain exactly as disclosed in the manifest-integrity-hardening
  and manifest-confidence-calibration phases — **not touched this phase**, per explicit
  instruction. Both still correctly determine their boolean target fact
  (`test_local_ml_provider_account_opening.py`, `test_local_ml_provider_investment.py`,
  unaffected by this phase), but the `PAN_CARD_IMAGE` upload path still cannot surface a
  `consequence_preview`, an unrelated, pre-existing limitation.
- **Confidence calibration intentionally deferred**: unchanged, untouched this phase.
  `confidence.py` was not modified; no threshold in any manifest was changed.
- **New limitation disclosed this phase — the "topic-mismatched ambiguity_rule" gap**: for
  Lending, Insurance, and KYC, a genuine name conflict is correctly detected and correctly
  triggers NEEDS_REVIEW, but the `ambiguity_id` attached belongs to a rule whose own static
  `question` text (surfaced only if the user proceeds into a formal CLARIFICATION resolution
  flow) is about a different topic (income mismatch / pre-existing illness / document expiry,
  not identity). This is a genuine manifest-schema limitation — there is no field in
  `AmbiguityRuleSpec` tagging a rule's semantic topic, so a fully generic mechanism (the only
  kind this phase's instructions permit — "do NOT create six separate consistency
  implementations") cannot distinguish a topically-matching rule from a merely
  structurally-matching one. The immediate `EvidenceConflict.message` shown right after upload
  is always accurate regardless; only a later, formal clarification screen could show a
  misleading question. Not fixed this phase, since doing so would require either inventing a
  new manifest schema field (out of scope) or journey-specific branching (explicitly
  prohibited).
- **Account Opening has zero surfaceable cross-document conflict path**: by manifest design (no
  evidence-driven target field has a matching ambiguity_rule at all) — disclosed, not worked
  around.
- **Identifier comparison is deliberately same-doc_type-only**: a PAN, an IFSC code, and an
  Aadhaar number are structurally incomparable; this phase never compares across doc_types,
  meaning a genuinely useful comparison (e.g. "does the PAN on this ITR match the PAN on that
  KRA letter") is out of scope until/unless the manifest itself establishes that two different
  doc_types' identifiers represent the same real-world number in the same format — it does not,
  for any of the six journeys today.

## 9. Files Changed

- `app/ai/models.py` — added `AIInterpretationResult.auxiliary_facts: dict[str, Any]`, an
  internal-only field (never wire-serialized) carrying the name/identifier facts for the caller
  to persist.
- `app/ai/local_ml.py` — restructured the per-field extraction loop so `name`/`identifier` are
  compared against `existing_fields` (via the new `consistency.py` functions), gated on
  `field.validated`, and attached to whichever ambiguity_rule structurally matches the current
  evidence's target field — fully generic, no per-journey branching. Added the
  `check_identifier_consistency`/`check_name_consistency` import.
- `app/docai/consistency.py` — new `check_identifier_consistency()` function (exact-match only,
  deliberately no fuzzy tolerance).
- `app/evidence/reconcile.py` — queries `evidence_repo.list_by_journey_id()` before calling the
  AI provider to merge prior auxiliary facts into `existing_fields`; merges
  `ai_res.auxiliary_facts` into `extracted_data` before persisting the new evidence record.
- `tests/unit/test_docai_consistency.py` — 9 new tests (`TestIdentifierConsistency` fully new; 3
  new `TestNameConsistency` edge cases).
- `tests/integration/test_cross_document_consistency.py` — new file, 14 tests covering all six
  journeys' matching/conflicting/no-comparison cases plus the low-confidence gate, using real
  rendered documents through the real production path.
- `docs/docai_cross_document_consistency_report.md` — this report.

Not modified: any dataset generator, any manifest YAML, any classifier/extraction/normalization/
confidence file, `contract/openapi.yaml`, `app/schemas/evidence.py` (wire schema unchanged), any
`app/core` file, any frontend file.
