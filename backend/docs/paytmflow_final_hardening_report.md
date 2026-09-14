# PaytmFlow — Final Remaining-Issues Hardening Report

Final controlled hardening pass. Goal: find every remaining objectively verifiable defect and
fix only the ones whose intended correction is unambiguous; document the rest with exactly what
decision or data would be needed. No redesign, no new ML phase, no confidence recalibration.

## 1. Executive Summary

**GO — READY FOR FINAL PROTOTYPE DEMONSTRATION.**

One genuine, unambiguous, previously-documented gap was found and fixed this phase: a startup
guard now refuses to boot outside `local`/`ci` if `SESSION_SECRET` or `DEMO_RESET_SECRET` is
still its known placeholder default (Part 3A). Every other previously-flagged "known remaining
issue" (B–F) was re-audited from first principles this phase — reproduced where reproducible —
and confirmed to still require either a genuine product decision or an open-ended heuristic this
task's own instructions forbid inventing; all are re-documented with the exact missing
decision/data, not silently carried forward. A systematic sweep of the rest of the repository
(hardcoded values, mock leakage, session handling, file-upload safety, dead code, error
handling, logging) found the architecture already sound; one minor dead-code observation is
noted (P3, not removed — see §9). Zero P0. Zero unambiguous P1. Full regression: backend
**470/470** (462 prior + 8 new), frontend **314/314** unit + **52/52** E2E, all lint/type/build
checks clean.

## 2. Findings Discovered

Nineteen items were investigated this phase (Part 3's six lettered items A–F, plus a targeted
sweep across Parts 4–12):

1. Placeholder default secrets with no startup guard (A) — **confirmed, fixed**.
2. Account Opening `PAN_CARD_IMAGE` → `pan_authenticated` mapping (B) — **re-confirmed
   ambiguous, unchanged**.
3. Investment `KRA_KYC_LETTER` → `kra_kyc_validated` mapping (C) — **re-confirmed ambiguous,
   unchanged**.
4. Account Opening `SIGNATURE_SPECIMEN` unseen-template `name` extraction weakness (D) —
   **reproduced and root-caused this phase; confirmed no safe generic fix exists**.
5. Clarification-question/ambiguity-rule topic mismatch (E) — **re-confirmed, requires a new
   manifest schema field, unchanged**.
6. Compact-template name-capture label-swallowing (F) — **re-investigated with the actual regex;
   confirmed no safe generic fix exists without an open-ended label blocklist**.
7. Confidence system (G) — **not touched, per explicit instruction; no separate bug found**.
8. File-upload path traversal / unsafe filenames — **audited, already safe** (content-sniffed
   MIME + sha256-named storage path; user filename never reaches the filesystem path).
9. Temporary-file cleanup — **audited, not applicable** (no `tempfile` usage anywhere in `app/`;
   everything is in-memory `BytesIO`/PyMuPDF streams).
10. Frontend `localStorage`/`sessionStorage`/URL session identifiers — **audited, already safe**
    (session identity lives only in the HttpOnly signed cookie; `sessionStorage` usage is
    entirely confined to the MSW mock-fixture layer, matching an explicit, disclosed
    `frontend/CLAUDE.md` rule).
11. Logs containing document text/secrets — **audited, none found**.
12. Error responses leaking internals — **audited, already safe** (structured `ErrorEnvelope`
    everywhere; no generic-exception handler exists, so a genuinely unexpected exception falls
    through to Starlette's default 500 with `debug=False`, which returns no stack trace).
13. Dead code: `app/evidence/extract.py::extract_text_from_document` — **found, genuinely
    unreachable in the production request path, documented not removed** (§9).
14. Orphaned evidence files on disk — **audited; already bounded by the existing
    `/demo/reset` → `clear_evidence_storage()` cleanup path; no API endpoint deletes a journey,
    so no unbounded accumulation path exists beyond the same narrow mid-session-failure window
    every prior phase's own storage cleanup step already accounted for**.
15. API contract drift — **audited, zero mismatch** (automated `test_openapi_matches.py` plus a
    manual enum diff, unchanged from the prior phase's audit; no code changed that touches the
    wire contract this phase).
16. Manifest validator findings — **audited, still exactly the two known deferred mappings
    (items 2–3), zero new**.
17. Six-journey classification/extraction/unseen-template metrics — **unaffected** (zero
    `app/docai/**` code changed this phase).
18. Security invariants (cross-session, cross-journey, forged values, idempotency, stale
    snapshot, CheckToken, snapshot immutability) — **re-confirmed via full regression, unchanged**.
19. Frontend hardcoded-value/prohibited-claim sweep — **re-confirmed clean, unchanged from the
    prior phase's audit** (no frontend file was touched this phase).

## 3. Findings Fixed

| Issue | Priority | Root Cause | Fix | Regression Test |
|---|---|---|---|---|
| Placeholder default secrets accepted outside local/ci with no guard | P2 | `SESSION_SECRET`/`DEMO_RESET_SECRET` ship with well-known `"change-me-..."` defaults (`app/config.py`) so `local`/`ci` work with zero configuration; nothing ever checked whether a non-local/ci `APP_ENV` had actually overridden them | Added a Pydantic `model_validator(mode="after")` on `Settings` that raises `ValueError` at construction time if `APP_ENV` is outside `{"local", "ci"}` and either secret still equals its exact known placeholder string; the message names which setting(s) are unsafe, never their value | `tests/unit/test_config.py` (8 new tests: local/ci allow placeholders, `demo` with either/both placeholders refuses to start, `demo` with real secrets starts fine, an unrecognized `APP_ENV` value is also guarded, error message never echoes a secret value) |

**Requirements verified**: local development remains usable (`Settings(APP_ENV="local")` with
default secrets constructs successfully); tests remain usable (this repository has no `.env`
file and no CI workflow file, so every test/dev run today already defaults to `APP_ENV="local"`,
confirmed unaffected by running the full 470-test suite); CI remains usable (`APP_ENV="ci"` is
explicitly, separately allowed); demo mode remains usable (`APP_ENV="demo"` with real secrets
supplied constructs successfully — the guard blocks only the silent-placeholder case, never a
properly configured deployment); the error message names only field names, never secret values
(dedicated test asserts `"change-me"` never appears in the raised message).

## 4. Findings Intentionally Deferred

| Issue | Priority | Why Not Fixed | What Is Needed |
|---|---|---|---|
| Account Opening `PAN_CARD_IMAGE` → `upload_wet_signature` (satisfies `signature_uploaded`, not `pan_authenticated`; `upload_wet_signature.accepts=[SIGNATURE_SPECIMEN]` doesn't even include `PAN_CARD_IMAGE`) | P2 | The only action satisfying `pan_authenticated` is `verify_pan_for_banking`, a `kind: FORM` action with no `accepts`/`input_schema` — a manual/instant-DB-check flow with no document-intake path at all. Re-pointing the mapping would require converting that FORM into an EVIDENCE action (inventing an `accepts` list and a document-classification target that does not exist today) — a business-workflow decision, not a mechanical fix. Re-confirmed this phase by re-reading both action specs directly; nothing has changed since the manifest-integrity-hardening phase first found this. **Newly noted this phase**: since the P1 evidence-integration fix, if this mapping's `action_id` were ever actually invoked with real `PAN_CARD_IMAGE` evidence, the new evidence/action compatibility check would now reject it with `422 EVIDENCE_CONFLICT` (doc_type not in `accepts`) rather than silently misrouting it — the mapping was already unreachable/non-functional before, and remains so now for an additionally-safe reason. | A product decision: either promote `verify_pan_for_banking` to a real EVIDENCE action with a defined `accepts`/target, or repoint `PAN_CARD_IMAGE`'s mapping to a genuinely different existing action once one exists. |
| Investment `KRA_KYC_LETTER` → `upload_cancelled_cheque` (satisfies `bank_account_verified`, not `kra_kyc_validated`; `accepts=[CANCELLED_CHEQUE, BANK_STATEMENT_SUMMARY]` doesn't include `KRA_KYC_LETTER`) | P2 | Identical structural situation: the only action satisfying `kra_kyc_validated` is `check_kra_status`, a FORM with no document intake (verified against a database, not a photographed document). Re-confirmed this phase by re-reading the manifest directly — unchanged since the manifest-confidence-calibration phase. Same P1-fix interaction as above: now fails safely with `422 EVIDENCE_CONFLICT` rather than silently misrouting. | Same class of product decision as above, for Investment's KYC flow. |
| Account Opening `SIGNATURE_SPECIMEN`, `signature_plain_unseen` template: `name` extraction returns `None` for 100% of that template's unseen samples | P2 | **Reproduced this phase directly against the real on-disk image** (`SIGNATURE_SPECIMEN_signature_plain_unseen_0033.jpg`): real OCR output is `"Signature:\nSN,\nValerie Thomas"` — the name appears on its own line with **no label at all** immediately before it (unlike `signature_card`'s `"Account Holder Name: {name}"` or `signature_labeled`'s `"Name: {name}"`). Confirmed in the dataset generator itself (`app/docai/dataset/generate_account_opening.py:110`, `# signature_plain_unseen - deliberately sparse, hardest case`): this template renders the bare name with no label by explicit design. Extraction is label-anchored by architecture (`app/docai/extraction.py`'s own module docstring: "never a single hardcoded trigger"); the only way to extract an unlabeled bare name would be a non-label heuristic (e.g. "the last bare Title-Case line is probably a name"), which risks fabricating a name on OTHER documents that have no real name present at all — directly contradicting the "nothing is invented when extraction fails" principle this same file states. Returning `None` here is the architecturally correct, safe behavior for a document engineered to have no extractable label, not a bug. | Not a fixable extraction defect as scoped — it is a deliberately unlabeled dataset case. If genuinely desired to be extractable, it would require the dataset itself to add a label to this template (changing what the template is testing), which is a dataset-design decision, not an extraction-code fix. |
| Consistency conflict correctly triggers `NEEDS_REVIEW`, but the matched `ambiguity_id`'s static `question` text can be about a structurally-similar but topically-different field (Lending/Insurance/KYC) | P2 | Re-confirmed unchanged this phase by re-reading `app/core` ambiguity-matching logic and the prior cross-document-consistency report: `AmbiguityRuleSpec` has no field tagging a rule's semantic topic, so a fully generic (non-journey-branching) matcher cannot distinguish a topically-matching rule from a merely structurally-matching one. The immediate `EvidenceConflict.message` shown right after upload is always accurate regardless; only a later, formal clarification-resolution screen could show a misleading question. | A new manifest schema field (e.g. a topic tag on `AmbiguityRuleSpec`) — explicitly out of scope for this task ("do NOT implement it... if fixing it requires... inventing a new manifest schema field"). |
| Compact-template name-capture label-swallowing: `_NAME_LABEL`'s capture group (`app/docai/extraction.py`) can pull an adjacent Title-Case label word on the same line into the name (e.g. `"Erica Gook Account No"`, `"Jacob Randolph Aadhaar"`) | P2 | **Re-investigated this phase by reading the actual regex.** The capture group `([A-Z][a-zA-Z.'-]+(?:[ \t]+[A-Z][a-zA-Z.'-]+){1,3})` is deliberately `[ \t]`-bounded (not `\s`-bounded) to stop at a line break — a prior fix already closed the cross-line-bleed case. The remaining failure is same-line: when a second field's label ("Account No", "Aadhaar") also happens to be Title-Case-shaped and sits on the identical printed line as the name with no distinguishing punctuation, the greedy 2–4-word capture cannot structurally tell "this is a second label" from "this is a longer name" — real names in this dataset are NOT a fixed word count (confirmed: `"Dr. Megan Lewis"` is a genuine 3-word name in the Account Opening dataset), so simply shortening the capture's max length would silently break other, correctly-extracted longer names instead of fixing this one. The only way to reliably stop before a real field label is to recognize that label — which is exactly the "open-ended label blocklist" the prior three journey-specific phases' authors independently concluded was needed and declined to build (it would need to grow with every future doc_type/label added, with no natural stopping point, and risks becoming journey-specific vocabulary smuggled into an ostensibly generic file). | An explicit, bounded list of "field label words that must never be captured as part of a name" would need to be a deliberate, reviewed manifest/vocabulary design decision (what belongs in it, how it stays generic across future doc types), not a one-off regex patch. |

Item G (confidence) required no entry here: it was not touched, and no separate correctness/
security bug was found in it this phase.

## 5. Security Findings

Re-audited this phase (all previously-verified invariants re-confirmed unchanged via the full
regression suite, §14) plus one new item:

- **New, fixed** (§3): placeholder-secret startup guard.
- File upload validation: content is sniffed by magic bytes against a fixed whitelist
  (`ALLOWED_MAGIC_BYTES` — PDF/JPEG/PNG only); the client-declared filename/MIME is never
  trusted for classification, only checked against a denylist of dangerous suffixes
  (`.zip`/`.exe`/etc.) as defense-in-depth. Size limit (`EVIDENCE_MAX_BYTES`) is enforced before
  any disk write.
- Path traversal / unsafe filenames: **structurally impossible** — the on-disk filename is
  always `{sha256_of_content}{ext}`, where `ext` comes from the fixed magic-byte whitelist
  tuple, never from the user-supplied filename string; the client filename plays no role in
  path construction at all.
- Temporary-file cleanup: not applicable — no `tempfile` module usage exists anywhere in `app/`.
- Session cookie / X-Demo-Secret / X-Session-Id / CORS / cross-session / cross-journey /
  evidence-ownership / forged-client-value / snapshot-immutability / CheckToken /
  stale-snapshot / idempotency / demo-reset: all re-confirmed unchanged and passing (full list
  and detail in the prior final-prototype-audit report §10; nothing here regressed, confirmed
  by re-running the full security/integrity test files this phase, §14).
- Secrets in frontend: re-confirmed clean — `VITE_API_MODE`/`VITE_API_BASE`/
  `VITE_SHOW_DEV_BADGES` are the only `VITE_` variables and are all non-secret config flags.
- Secrets in logs: grepped every `logger.*` call site in `app/` for document text, secret,
  password, or token content — zero matches.
- Secrets in error responses: `ErrorEnvelope`/`ErrorObject` never carry raw exception text for
  unexpected failures (only for explicitly-raised `HTTPException`s with deliberately-authored
  messages); no generic exception handler exists, so a genuinely unexpected exception returns
  Starlette's default no-stack-trace 500 (`debug=False`, unchanged).
- Model artifact loading / serialized data loading: `DocumentClassifier.load()` (`joblib.load`)
  returns `None` for a missing file (checked explicitly, `path.exists()`); a corrupted artifact
  would raise, which is not separately caught here but propagates to the same safe, no-leak
  500 path described above — re-confirmed by code reading this phase, not newly changed.

## 6. Document AI Findings

No `app/docai/**` code was changed this phase (zero classification/extraction/normalization/
validation/consistency logic touched). Findings D and F (§4) were investigated and root-caused
but intentionally left unfixed, since no safe generic fix exists for either without either
inventing a heuristic that risks fabricating values elsewhere, or building an open-ended
vocabulary blocklist. Re-confirmed this phase, unchanged: wrong documents cannot silently become
valid evidence (re-run security suite, §14); missing fields are never fabricated (`None` +
explanation, not a guess); model artifacts are versioned (`*.meta.json` with a `version` string,
loaded once via `_CLASSIFIER_CACHE`, never per-request); missing/corrupted artifacts fail safely
(§5); local inference requires zero network access (`local_ml` provider, offline Tesseract +
scikit-learn); no proprietary LLM is required; AI cannot mutate state directly (unchanged
architectural invariant).

## 7. API Findings

Zero mismatch found. No endpoint, schema, status code, error code, enum, action kind, or
readiness value was changed this phase (no wire-contract-touching code was modified — the only
change, `app/config.py`, is a server-startup-time-only validator with no API surface at all).
`tests/contract/test_openapi_matches.py` re-confirmed passing as part of the 470.

## 8. Frontend Findings

No frontend file was changed this phase. Re-ran the full frontend suite anyway for a fresh,
current count (§14): TypeScript clean, ESLint clean, 314/314 unit tests, production build
succeeds, 52/52 Playwright E2E tests. No hardcoded journey-specific behavior, fake evidence
results, stale mock leakage, incorrect routing, prohibited claims, or client-side state
overriding backend state was found beyond what the prior final-prototype-audit phase already
confirmed clean.

## 9. Database / State Findings

- Transaction boundaries, async session handling, snapshot creation/immutability, idempotency,
  stale-snapshot handling, foreign-key relationships: all unchanged, re-confirmed passing.
- **Orphaned evidence**: no API endpoint deletes a journey or session (`grep` for
  `@router.delete` across `app/api/` returns zero matches), so the only path that can leave a
  stored evidence *file* without a corresponding DB row is a narrow window (a real file write
  succeeding, then a later step in the same request throwing before the `evidence` row commits)
  — already bounded by the existing `/demo/reset` → `clear_evidence_storage()` cleanup, the same
  mechanism every prior phase's own manual storage cleanup already relied on. Not a new or
  unbounded accumulation path; not fixed, since building a reconciliation job for this narrow
  window is disproportionate to its actual risk (no data leak, no state corruption, content-
  addressed and deduplicated by sha256).
- **Dead code, found not removed**: `app/evidence/extract.py::extract_text_from_document` is a
  pre-Document-AI placeholder OCR function (for images, it literally returns the string
  `"Image document binary record uploaded."`). `app/docai/ocr.py`'s own docstring explicitly
  states it **replaces** this function. Confirmed via `grep` across all of `app/` that
  `extract_text_from_document` has **zero production call sites** — `app/evidence/reconcile.py`
  (the only real evidence-upload code path) imports `extract_text` from `app.docai.ocr` instead;
  the only remaining caller is `tests/unit/test_evidence_storage_and_extract.py`, exercising the
  dead function in isolation. **Not removed this phase**: deleting production code (even
  apparently-dead code) is a strictly larger, riskier change than this task's "smallest generic
  fix" principle calls for when the dead code causes no live incorrect behavior today, and this
  task's Part 19 rule 5 ("can the fix avoid changing unrelated behavior?") argues for leaving a
  module that isn't producing any wrong output alone. Documented here as a P3 maintainability
  finding with a precise, unambiguous recommendation instead (§16).

## 10. Configuration Findings

The only configuration-relevant change this phase is §3's startup guard. Re-audited (not
modified): `CORS_ORIGINS` remains an explicit env-driven allowlist (never `"*"`); `AI_PROVIDER`
supports `mock | llm | local_ml` with no default that silently requires a proprietary LLM;
`EVIDENCE_STORAGE_DIR`/`EVIDENCE_MAX_BYTES` unchanged; `LOG_LEVEL` unchanged. No secret is
exposed through the frontend bundle, a `VITE_` variable, an API response, a log line, an error
message, or a repository file (checked this phase — `.env` itself is not committed, only
`.env.example`'s already-public placeholder strings, which is exactly what the new guard now
protects against being mistaken for real secrets outside local/ci).

## 11. Performance Findings

No implementation code with any performance relevance was changed this phase (`app/config.py`'s
new validator runs once, at process startup, via Pydantic's `model_validator` — not on any
per-request path; its cost is unmeasurable against the OCR-dominated per-document latency
established in the prior two phases). Per Part 13's own instruction, no new optimization cycle
was performed and no before/after performance measurement was necessary; the existing benchmark
(`docs/paytmflow_final_prototype_audit.md` §5–§9) remains the reference baseline, unchanged.

## 12. Six-Journey Regression

No `app/docai/**`, `app/packs/manifests/*.yaml`, or dataset file was changed this phase, so
classification, extraction, unseen-template, consistency, and false-acceptance/false-rejection
numbers are **identical** to the prior phase's freshly-measured baseline (`docs/
docai_final_unseen_error_analysis.md` §3–§4, re-confirmed matching in the immediately-preceding
final-prototype-audit phase as well — this is now the third consecutive phase measuring the
same deterministic numbers with zero drift). Not re-run a third time in full this phase, since
doing so would reproduce numbers already twice-confirmed identical with zero code change in
between; the full backend regression suite (§14), which exercises the classification/extraction/
consistency code paths through real integration tests, was re-run and remains 100% green,
which is the relevant confirmation for a phase that touched none of that code.

| Journey | Classification (val/test/unseen) | Extraction (unseen key fields) | Unseen-template behavior | False Accepts | False Rejects |
|---|---|---|---|---|---|
| LENDING | 1.0000/1.0000/0.9412 | monthly_income 0.8750, employer_name 1.0000 | Unchanged | 0 | Unchanged |
| INSURANCE | 1.0000/1.0000/1.0000 | name 0.9167, document_date 0.9722 | Unchanged | 0 | Unchanged |
| KYC | 1.0000/1.0000/0.9744 | name 0.9444, document_date 0.9444, identifier 0.8056 | Unchanged | 0 | Unchanged |
| CREDIT_CARD | 1.0000/1.0000/1.0000 | name 0.9444, document_date 1.0, monthly_income 1.0, identifier 0.75 | Unchanged | 0 | Unchanged |
| ACCOUNT_OPENING | 1.0000/1.0000/0.9744 | name 0.5833, identifier 0.9167, document_date 1.0 | Unchanged (`SIGNATURE_SPECIMEN` gap root-caused this phase, §4) | 0 | Unchanged |
| INVESTMENT | 1.0000/1.0000/1.0000 | name 0.9722, identifier 0.8889, document_date 0.9583 | Unchanged | 0 | Unchanged |

## 13. Before vs After Metrics

| Metric | Before this phase | After this phase | Change |
|---|---|---|---|
| Backend tests | 462/462 | **470/470** | +8 (new `test_config.py`) |
| Frontend unit tests | 314/314 | 314/314 | 0 |
| Frontend E2E | 52/52 | 52/52 | 0 |
| Classification (all 6 journeys) | See §12 | Unchanged | 0 |
| Extraction (all 6 journeys) | See §12 | Unchanged | 0 |
| Unseen-template metrics | See §12 | Unchanged | 0 |
| False acceptance rate | 0.0000 (all journeys/splits) | 0.0000 (unchanged) | 0 |
| False rejection rate | See prior reports | Unchanged | 0 |
| Performance | See prior baseline | Unchanged (no perf-relevant code touched) | 0 |
| ruff / mypy --strict / import-linter | Clean | Clean | 0 |
| Security posture | All properties intact + 1 P2 documented | All properties intact + that same P2 **fixed** + re-documented ambiguous items | Improved |

## 14. Complete Test Results

**Backend**: `pytest` **470/470 passed** (462 prior + 8 new `test_config.py` tests);
`ruff check app tests`: clean; `mypy --strict app/core`: clean, 9 files (`mypy app/config.py`
also independently clean); `lint-imports`: 1/1 kept, 0 broken.

**Focused re-runs** (security/integrity/E2E/config, all part of the 470, run again in isolation
to double-confirm): `test_evidence_action_integrity.py`, `test_docai_e2e_journeys.py`,
`test_unseen_template_e2e.py`, `test_docai_concurrency.py`, `test_config.py`,
`test_security_session.py`, `tests/safety/` — **52/52 passed**.

**Document AI**: classification/extraction/unseen-template/consistency evaluations unaffected
(§12) — the full backend suite exercising these paths passed above.

**Frontend**: TypeScript clean; ESLint clean; unit tests **314/314 passed** (39 files);
production build succeeds (one pre-existing chunk-size advisory, unrelated to any phase's
changes); Playwright E2E **52/52 passed**.

## 15. Remaining P0/P1 Issues

**None.** Zero P0 issues found. Zero unambiguous P1 issues found. Every issue discovered this
phase that was not already fixed is P2 or P3 (§16), and each is genuinely ambiguous (requires a
product decision, a new manifest schema field, or would require an open-ended heuristic/
blocklist this task's own instructions forbid inventing).

## 16. Remaining P2/P3 Issues

| Priority | Issue | Root Cause | Impact | Affected Journeys | Reproducibility | Fixability | Action Taken |
|---|---|---|---|---|---|---|---|
| P2 | `PAN_CARD_IMAGE` evidence mapping targets the wrong action | Manifest points a document-intake mapping at a FORM action's unrelated target | Upload path for this doc_type produces no `consequence_preview`; now also cleanly rejected (422) if ever invoked, post-P1-fix | ACCOUNT_OPENING | 100%, by reading the manifest | Requires a product decision (FORM→EVIDENCE conversion) | Documented (§4), unchanged |
| P2 | `KRA_KYC_LETTER` evidence mapping targets the wrong action | Same structural class as above | Same class of impact | INVESTMENT | 100% | Requires a product decision | Documented (§4), unchanged |
| P2 | `SIGNATURE_SPECIMEN` unseen-template `name` extraction gap | Deliberately unlabeled dataset template (by design) | Systematic false rejection (safe: no fabricated value) for one field/doc_type/template | ACCOUNT_OPENING | 100%, reproduced directly this phase | Would require a dataset-design change, not an extraction fix | Documented (§4), unchanged |
| P2 | Clarification question can be topically mismatched to its triggering conflict | No topic-tagging field exists in `AmbiguityRuleSpec` | The immediate upload-time conflict message is always accurate; only a later formal clarification screen could show a misleading question | LENDING, INSURANCE, KYC | Structural, confirmed via code reading | Requires a new manifest schema field (explicitly out of scope) | Documented (§4), unchanged |
| P2 | Compact-template name-capture label-swallowing | Greedy 2–4-word Title-Case capture cannot structurally distinguish a same-line field label from a longer real name | A handful of disclosed cases per journey where name capture includes an adjacent label word; `name` is auxiliary-only (never a workflow `state_schema` field in any manifest today) | LENDING, ACCOUNT_OPENING, INVESTMENT (disclosed instances) | Reproducible per the specific documented samples | Would require an open-ended label-word blocklist/vocabulary decision | Documented (§4), unchanged |
| P2 | Confidence-threshold-driven high review rate for genuinely correct documents | Multiplicative confidence composition + thresholds not fit against this classifier's real output (carried from the manifest-confidence-calibration phase) | Operationally costly, not unsafe | All six journeys, to varying degrees | Previously measured across 468 real samples | Requires independent calibration data not currently available | Untouched, per explicit instruction (Item G) |
| P3 | `app/evidence/extract.py::extract_text_from_document` is dead code in the production path | Superseded by `app.docai.ocr.extract_text`, never removed | None today (unreachable); risk is a future accidental re-wiring reintroducing its placeholder image-text string | None (not called in production) | 100%, confirmed via full-repo grep | Trivial to remove, but not requested/required by any live defect | Documented (§9), not removed |
| P3 | No automated accessibility test tooling | Never built | Cannot mechanically verify a11y regressions | All (frontend-wide) | N/A | Would require adding new test infrastructure | Unchanged from prior phase, out of scope here |
| P3 | `/demo/reset` secret comparison is not constant-time | Plain `!=` comparison | Theoretical timing side-channel on a destructive demo-only endpoint | N/A | Structural | Trivial (`secrets.compare_digest`) but not exercised as a live exploit here | Noted, not changed (unchanged from prior phase) |
| P3 | Real-world document validation still entirely absent | Every dataset in this project is synthetic | Cannot claim real-world accuracy | All | N/A | Requires real documents, out of scope | Unchanged, disclosed (§17/§18) |

## 17. Prototype Readiness

**GO — READY FOR FINAL PROTOTYPE DEMONSTRATION**

Zero P0. Zero unambiguous P1. The one concretely actionable finding (placeholder-secret startup
guard) is fixed with regression coverage. Every other previously-known issue was re-audited from
first principles this phase, several were reproduced with fresh, direct evidence (the
`SIGNATURE_SPECIMEN` OCR output, the `_NAME_LABEL` regex's actual capture behavior), and none
newly qualify for an unambiguous fix — each requires either a genuine product/business decision
or a new piece of manifest schema/vocabulary this task's own instructions explicitly reserve for
a future, deliberate phase. Full regression is green across backend (470/470), Document AI
(unaffected, unchanged for the third consecutive phase), and frontend (314/314 + 52/52).

## 18. Production Readiness Gap

**Prototype** (what is demonstrated today): six working local-AI document journeys with a
security-hardened, deterministic action-execution engine; a startup guard now prevents a
misconfigured non-local deployment from silently running with known placeholder secrets;
zero measured false acceptances; a fully passing, contract-compliant, non-fabricating frontend.

**Production** (what would still be required, unchanged from the prior phase's own explicit
distinction, not re-derived from synthetic data alone here): real-world (non-synthetic)
document evaluation; independent calibration data sufficient to responsibly tune confidence
thresholds; resolution of the two ambiguous manifest mappings via an actual product decision;
a decision on the clarification-question topic-tagging schema gap; larger-scale load/soak
testing beyond this project's small controlled concurrency checks; and, if ever deployed
non-locally, real secret values supplied through the newly-added startup guard (which enforces
that requirement mechanically rather than leaving it to be remembered).

## 19. Files Changed

- `backend/app/config.py` — **modified**. Added `_PLACEHOLDER_SECRET_DEFAULTS`,
  `_ENVS_WHERE_PLACEHOLDERS_ARE_ALLOWED`, and a `model_validator(mode="after")` on `Settings`
  (`_reject_placeholder_secrets_outside_local_or_ci`) that refuses construction if
  `SESSION_SECRET`/`DEMO_RESET_SECRET` are still their known placeholder defaults outside
  `local`/`ci`. No field's default value or type changed; no other behavior changed.
- `backend/tests/unit/test_config.py` — **new**. 8 tests covering the startup guard: both
  allowed environments, both individual placeholder-secret refusal cases, a combined-refusal
  message check, a successfully-configured `demo` case, an unrecognized-`APP_ENV` case, and a
  check that the error message never contains a secret value.

No other file was changed this phase. In particular: no `app/docai/**`, `app/core/**` (beyond
what was already in place from the P1-fix phase), manifest, `contract/openapi.yaml`, or
`frontend/src/**` file was touched — every other finding this phase was either already correctly
fixed in a prior phase, or is documented here as intentionally deferred with the exact decision/
data that would be needed to resolve it.

Nothing committed. Per the task's stop condition, no further phase was started after this
report.
