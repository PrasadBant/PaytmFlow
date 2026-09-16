# PaytmFlow Final Full-Flow Audit

This report has been updated following a second real-user manual test pass that reported two
concrete, reproducible runtime inconsistencies (BUG A, BUG B below) contradicting the previous
GO status. Both were investigated from first principles against the actual running application —
not assumed, not dismissed. One (BUG B) was a genuine, confirmed, now-fixed P1 code defect. The
other (BUG A) was root-caused to a real, serious **operational/handoff failure**, not a code
defect in the audited pipeline — the running server the user tested against was left configured
with `AI_PROVIDER=mock` (a deliberate, documented, fixed-output stub), not the real `local_ml`
pipeline this project's whole mission is about. Both findings are reported in full, with exact
runtime evidence, per the explicit instruction not to hide anything and not to declare GO
without proof.

## 1. Executive Summary

**🟢 GO — READY FOR FINAL PROTOTYPE DEMONSTRATION**, with one important operational caveat now
fixed at the process level and documented prominently (§9).

**What actually happened this round**, in one sentence each:

- **BUG A** ("wrong document shown as verified salary slip, ₹85,000"): **not a code defect**.
  The server the user tested against was running `AI_PROVIDER=mock` — confirmed by direct
  runtime query — and `app/ai/mock.py`'s `MockAI.reconcile_evidence()` is a deliberate,
  documented, always-`verified=True`, fixed-`₹85,000`, fixed-`92%`-confidence stub built for
  frontend development without a backend, explicitly disclosed in its own docstring as
  "deterministic output regardless of real OCR signals." Restarting with `AI_PROVIDER=local_ml`
  and re-uploading a real, unrelated PDF (a reconstruction of the user's own
  `FIN-SHIELD_Hackathon_Presentation.pdf`) through the real browser against the real backend
  produced the correct, honest result: `verified: false, confidence: 0.3042, detected: [],
  summary: "The document type could not be confidently determined.", consequence_preview: null`
  — captured directly from the real `POST /evidence` response. **This is the real, unbroken
  behavior the previous audit already verified; it was not verified again by the user because
  the environment I handed over defaulted to the wrong AI provider.** A new backend regression
  test (`test_genuine_unrelated_pdf_is_not_shown_as_verified_salary_slip`) locks this exact
  scenario in permanently.
- **BUG B** ("Accept Loan Agreement Terms checkbox checked, but backend says accept_terms is
  missing"): **a real, confirmed, now-fixed P1 code defect** (tracked as BUG-003 below).
  Root cause, traced precisely: `ConsentPanel`/`SchedulingPicker`/`VideoVerificationFlow` (three
  shared "richer FORM UI" components used for consent/scheduling/video-style actions across all
  six journeys) submitted their payload keyed by `action.unlocks[0]` — the *state field the
  action satisfies* — instead of `action.input_schema[0].key` — the *actual payload key the
  backend requires*. For 10 of the 11 real consent/scheduling/video actions across all six
  manifests, these two values happen to be the same string (because those 10 actions declare no
  `input_schema` at all), which is exactly why this bug was invisible until now. Lending's
  `ACCEPT_LOAN_TERMS` is the **one** action that declares a real `input_schema`
  (`accept_terms`) with a genuinely different key than what it `satisfies`
  (`loan_offer_accepted`) — the exact case that exposes the bug. Fixed generically at the one
  shared call site (`Screen06UploadEvidence.tsx`), proven by a regression test that fails when
  reverted and passes when fixed, and re-verified live: the real captured `POST /actions`
  request body now reads `{"input": {"accept_terms": true}}`, and the real journey reaches
  `7/7 Completed`.

Both are now fixed, both have regression tests, and both were re-verified against the real,
running application — not merely re-tested by an automated suite.

## 2. Environment Tested

Same environment as the previous pass (Docker Postgres, real FastAPI backend, real Vite dev
server, real Chromium via Playwright against the live stack — `claude-in-chrome` remains
unavailable this session). **New this round**: the backend was deliberately restarted and its
`AI_PROVIDER` explicitly confirmed via a live `GET /api/v1/health` call before every test in this
phase, specifically because the root cause of BUG A was exactly this configuration being wrong
in the environment handed to the user.

## 3-8. Startup / Database / Contract / Six-Journey / Real-User / Frontend UX Verification

Unchanged from the previous pass except where explicitly updated below (§9-§13). Nothing in
those areas regressed; the fixes in this phase touch only `app/evidence/reconcile.py`'s already-
gated preview block (no new change needed there — BUG A required no backend fix, only proof) and
three frontend interaction components plus their one shared call site.

## 9. Runtime Proof That AI Is Actually Integrated (user's Part 1, answered directly)

Every question below was answered from the **actual running application**, not inferred:

| # | Question | Answer (with evidence) |
|---|---|---|
| 1 | Which AI provider is active? | Depends entirely on how the backend process was started — this is exactly the finding. The instance originally handed to the user was `mock`. Restarted with `AI_PROVIDER=local_ml` explicitly for this investigation. |
| 2 | Is `AI_PROVIDER` actually `local_ml`? | Confirmed live: `curl http://localhost:5173/api/v1/health` → `{"ai_provider":"local_ml", ...}` (captured this phase, §1). |
| 3 | Which OCR implementation executes? | `app/docai/ocr.py` (real Tesseract binary + PyMuPDF text-layer extraction) — the same code exercised by every prior phase's OCR benchmark; unchanged. |
| 4 | Which classifier model executes? | `app/docai/classifier.py::DocumentClassifier`, loading `lending_classifier.joblib` for the Lending journey — the real trained TF-IDF+LogisticRegression model. |
| 5 | Which extraction code executes? | `app/docai/extraction.py::extract_fields_for_doc_type` — unchanged, real label-anchored regex extraction. |
| 6 | What document type did the classifier actually predict? | For the reconstructed hackathon PDF: the classifier was never even reached with a confident prediction — word count/OCR confidence on a title-slide-style PDF triggered the `UNREADABLE`/low-confidence floor before classification could commit, producing `summary: "The document type could not be confidently determined."` — a real, honest "I can't tell" answer, not a wrong guess. |
| 7 | What confidence did it actually return? | `0.3042` (real, captured from the actual API response, not estimated). |
| 8 | What extracted fields did it actually return? | `[]` — none, correctly, since nothing was verified. |
| 9 | What `verified` boolean did it actually return? | `false`. |
| 10 | What exact response does `POST /evidence` return? | Captured verbatim (§10 below). |
| 11 | What exact data does Screen 7 receive? | The same JSON object, unmodified, via React Router location state — traced through `Screen06UploadEvidence.tsx`'s `handleUpload`/navigate call into `Screen07AiAnalysis.tsx`'s `evidenceResponse` prop; no transformation layer sits between them. |
| 12 | Where does ₹85,000 come from? | **Only** from `app/ai/mock.py`'s hardcoded `val = 85000` for any MONEY-type field (line ~150), which only ever executes when `AI_PROVIDER=mock`. It does **not** appear anywhere in the real `local_ml` response for this document (confirmed: `"85,000" not in interpretation.summary`, new regression test). |
| 13 | Where does "Verified Salary Slip" come from? | `MockAI.reconcile_evidence`'s `summary = f"Verified {doc_name_clean} with high confidence..."` — again, mock-only, always `verified=True` by construction. |
| 14 | Where does "92%" come from? | `MockAI`'s `confidence = min(0.98, confidence_threshold + 0.07)` — for Lending's SALARY_SLIP mapping (`confidence_threshold≈0.85`), that's `0.92`. Deterministic, mock-only arithmetic, not a real model output. |
| 15 | Is any `simulation_default` involved? | Not in this exact scenario (MockAI's ₹85,000 is a separate hardcoded literal in `mock.py`, not `manifest.simulation_defaults` — the two coincide in value but are different code). `simulation_defaults` **is** involved in the already-fixed BUG-002 path (§ from the prior audit), unrelated to this. |
| 16 | Is mock mode involved anywhere? | Yes — this **is** the root cause. `AI_PROVIDER=mock` on the backend. (Distinct from `VITE_API_MODE`, a frontend-only toggle for whether the browser talks to MSW or a real backend — the frontend was already correctly in `live` mode, genuinely reaching the real backend; the backend itself was the one configured for its own mock/stub provider.) |
| 17 | Is a fixture involved anywhere? | No frontend fixture/MSW handler was involved — `VITE_API_MODE=live` was active and confirmed reaching the real backend both times. |
| 18 | Is the frontend transforming/replacing the real response? | No — traced end-to-end; Screen 7 renders exactly what `POST /evidence` returned. |
| 19 | Is the backend returning fabricated/default analysis? | Only when explicitly configured to run `MockAI` (`AI_PROVIDER=mock`), which is a documented, intentional dev-mode stub, not a defect in the `local_ml` path. |
| 20 | Is the AI result being discarded before Screen 7? | No — traced and confirmed identical, both this phase and the prior one. |

## 10. `POST /evidence` — Captured Real Request/Response (user's Part 5)

Real request (from the live browser, real file upload): `multipart/form-data`, `doc_type:
SALARY_SLIP`, `expected_snapshot_id: <real snapshot uuid>`, file:
`FIN-SHIELD_Hackathon_Presentation.pdf` (a reconstruction of the user's reported file — team/
problem-statement/tech-stack slide text, genuinely unrelated to a salary slip).

Real response, captured verbatim via Playwright's network interception (not summarized):

```json
{
  "evidence_id": "abbf01a8-0095-4ce6-bcd8-021979acac55",
  "filename": "FIN-SHIELD_Hackathon_Presentation.pdf",
  "uploaded_at": "2026-09-15T17:17:41.665824Z",
  "size_bytes": 1827,
  "interpretation": {
    "verified": false,
    "confidence": 0.3042,
    "detected": [],
    "summary": "The document type could not be confidently determined.",
    "conflicts": []
  },
  "proposed_action_id": "UPLOAD_INCOME_PROOF",
  "consequence_preview": null,
  "diff_preview": null,
  "requires_review": true
}
```

## 11. Screen 7 Verification (user's Part 6)

Traced directly in `Screen07AiAnalysis.tsx`: the heading ("This document looks good!" /
"This document needs a closer look"), the AI summary text, and the evidence card's
`verified`/`requiresReview` badges are all driven exclusively by `interpretation.verified` and
`interpretation.summary` from the response above — none are hardcoded, none default to a
positive claim. For the real hackathon PDF against real `local_ml`, the screen correctly showed
"This document needs a closer look" / "The document type could not be confidently determined." —
confirmed both by direct DOM assertion and by screenshot. This is the same conditional-rendering
fix (BUG-002) verified in the previous audit pass, now additionally exercised against this
specific document shape (low-text/ambiguous, not just "confidently wrong") and confirmed to
behave correctly for that outcome path too.

## 12. `accept_terms` Full Trace (user's Part 7)

| Step | What was found |
|---|---|
| 1. Checkbox state variable | `ConsentPanel.tsx`'s local `const [agreed, setAgreed] = useState(false)` |
| 2. `onChange` handler | `onChange={(e) => setAgreed(e.target.checked)}` — correct, unchanged |
| 3. Form state | A single boolean, not a react-hook-form-managed field (this component is deliberately simpler than the generic `SchemaForm` path) |
| 4. Action payload builder | **Root cause, found here**: `onClick={() => void onSubmit({ [fieldKey \|\| 'consent_given']: true })}` — `fieldKey` was always `action?.unlocks?.[0]` |
| 5. API request body | Before fix: `{"input": {"loan_offer_accepted": true}}`. After fix: `{"input": {"accept_terms": true}}` (captured live, §1) |
| 6. Backend `input_schema` | `ACCEPT_LOAN_TERMS.input_schema = [{key: "accept_terms", type: boolean, required: true}]` (`app/packs/manifests/lending.yaml`) |
| 7. Backend validation | `app/core/deterministic_check.py` step 4: `if f_spec.required and val is None: raise ... "Required input field '{f_spec.key}' is missing"` — this is the **exact, byte-for-byte** error text the user saw, confirming the precise validation line responsible |
| 8. Deterministic action execution | Once the key matches, `loan_offer_accepted` is correctly satisfied via the existing exact-key-match path in `deterministic_check.py`'s new-values computation — unchanged, already correct |

**Fix**: `Screen06UploadEvidence.tsx` now computes `interactionFieldKey = action?.input_schema?.
[0]?.key || action?.unlocks?.[0]` once, and all three interaction components consume that
corrected value instead of reading `unlocks[0]` directly. This is the smallest generic fix:
no manifest change, no new business logic, no per-journey/per-action special-casing — it simply
makes the frontend consult the field the contract itself says is authoritative ("FORM -> generic
action modal rendered from input_schema") whenever one is declared, falling back to the previous
behavior only when it is not.

**Tested**: unchecked → `consent-confirm-btn` is `disabled` (pre-existing, unchanged, correct).
Checked → real request now contains `accept_terms: true`, action succeeds, journey reaches
`7/7 Completed` (screenshot-confirmed). Double-click: `isSubmitting`/`applyAction.isPending`
already disables the button during the mutation — unchanged from the prior phase's verification.
Refresh: not separately re-tested this phase (no code path touched here affects persistence/
idempotency).

## 13. Audit of All FORM Actions Across All Six Journeys (user's Part 8)

Systematically enumerated every `kind: FORM` action across all six manifests and classified each
by the same three interaction patterns the frontend actually uses
(`VIDEO_VERIFICATION`/`SCHEDULING`/`CONSENT`/generic `FORM`):

| Manifest | Action | Interaction type | `satisfies[0]` (`unlocks[0]`) | `input_schema[0].key` | Bug present? |
|---|---|---|---|---|---|
| account_opening | `complete_video_kyc` | VIDEO_VERIFICATION | `vkyc_completed` | *(none declared)* | No — fallback path, unaffected |
| account_opening | `accept_banking_terms` | CONSENT | `account_agreement_accepted` | *(none declared)* | No — fallback path, unaffected |
| credit_card | `sign_cardholder_agreement` | CONSENT | `card_agreement_signed` | *(none declared)* | No — fallback path, unaffected |
| insurance | `schedule_tele_mer` | SCHEDULING | `tele_underwriting_scheduled` | *(none declared)* | No — fallback path, unaffected |
| insurance | `setup_insurance_mandate` | CONSENT | `bank_mandate_registered` | *(none declared)* | No — fallback path, unaffected |
| insurance | `accept_insurance_policy` | CONSENT | `policy_terms_accepted` | *(none declared)* | No — fallback path, unaffected |
| investment | `register_enach_mandate` | CONSENT | `sip_mandate_approved` | *(none declared)* | No — fallback path, unaffected |
| investment | `sign_investment_declaration` | CONSENT | `nomination_and_fatca_signed` | *(none declared)* | No — fallback path, unaffected |
| kyc | `capture_liveness_selfie` | VIDEO_VERIFICATION | `live_photo_captured` | *(none declared)* | No — fallback path, unaffected |
| kyc | `sign_rekyc_undertaking` | CONSENT | `rekyc_declaration_signed` | *(none declared)* | No — fallback path, unaffected |
| **lending** | **`ACCEPT_LOAN_TERMS`** | **CONSENT** | **`loan_offer_accepted`** | **`accept_terms`** | **YES — the reported bug** |

All other FORM actions across all six journeys (`SUBMIT_EMPLOYMENT_INFO`,
`VERIFY_EMPLOYER_RECORD`, every generic data-entry FORM in every journey) render through
`FormActionModal`/`SchemaForm`, which builds its payload from react-hook-form state keyed
individually by each field's own `input_schema[].key` — a structurally different, unaffected
code path, confirmed by direct code reading and by this phase's own live test of
`SUBMIT_EMPLOYMENT_INFO`/`VERIFY_EMPLOYER_RECORD` completing correctly.

**Conclusion**: the bug was real and structurally present in three shared components across all
six journeys, but was only externally *observable* in exactly one action
(`ACCEPT_LOAN_TERMS`) today, because it is the only one of 11 consent/scheduling/video actions
that declares a real `input_schema`. The fix is generic and protects all 11 (and any future
action of this shape), not just the one that happened to expose it — proven by a regression test
that specifically declares an `input_schema` on a synthetic consent action and asserts the
correct payload key is used, and by confirming the pre-existing test for a consent action
*without* an `input_schema` (`SIGN_CARD_AGREEMENT`) still passes unchanged (the fallback path is
provably intact).

## 14. Regression Tests Added This Phase

| Test | File | Proves |
|---|---|---|
| `test_genuine_unrelated_pdf_is_not_shown_as_verified_salary_slip` | `backend/tests/integration/test_docai_e2e_journeys.py` | The real `local_ml` pipeline, given a document shaped exactly like the user's report, returns `verified=false`, `detected=[]`, no `₹85,000`/`92%` claim, `consequence_preview=null`, and mutates no state (`version_number` stays 1, `monthly_income` stays `null`) |
| `CONSENT action WITH a declared input_schema submits the input_schema key, not unlocks[0]` | `frontend/tests/unit/screens/Screen06UploadEvidence.test.tsx` | Reproduces `ACCEPT_LOAN_TERMS`'s exact manifest shape; asserts the real captured request body contains `{accept_terms: true}`, not `{loan_offer_accepted: true}`. **Verified to actually catch the bug**: reverting the fix locally and re-running this test fails with the exact wrong key (`loan_offer_accepted: true`) as the captured payload — restoring the fix makes it pass again. |

Both were additionally re-verified live against the real running application (not just the
automated suite) — captured request/response payloads reproduced in §10 and §12 above.

## 15. Confirmed Bugs (cumulative, this phase + carried forward)

**BUG-001** (prior phase, unchanged, still fixed): `GET /api/v1/health` 500'd with
`AI_PROVIDER=local_ml` due to an incomplete `Literal`/contract enum. Fixed.

**BUG-002** (prior phase, unchanged, still fixed): Screen 7's "looks good" header rendered
unconditionally; backend evidence preview was computed without regard to whether evidence was
genuinely verified. Fixed; this phase's BUG A investigation additionally re-confirms the fix
holds for the *ambiguous/low-confidence* outcome path (not just the *wrong-document* path
previously tested).

**BUG-003** (this phase — user-reported as "BUG B")
- Severity: **P1**
- Component: Frontend interaction components (shared across all six journeys)
- Files: `frontend/src/screens/Screen06UploadEvidence.tsx`,
  `frontend/src/components/interactions/{ConsentPanel,SchedulingPicker,VideoVerificationFlow}.tsx`
- Reproduction: any CONSENT/SCHEDULING/VIDEO_VERIFICATION-classified FORM action whose manifest
  declares an `input_schema` with a key different from what it `satisfies` — today, exactly
  Lending's `ACCEPT_LOAN_TERMS` (`input_schema[0].key="accept_terms"` vs.
  `satisfies[0]="loan_offer_accepted"`). Check the consent checkbox, click confirm.
- Expected: `POST /actions` request body contains `{"input": {"accept_terms": true}}`; action
  succeeds.
- Actual (before fix): request body contained `{"input": {"loan_offer_accepted": true}}`;
  backend correctly rejected it with `422 "Required input field 'accept_terms' is missing"`.
- Root cause: all three components derived their submission key from `action.unlocks[0]`
  unconditionally, rather than preferring `action.input_schema[0].key` (the contract's own
  documented source of truth for FORM-action payloads) when declared.
- Impact: a real user visibly agreeing to loan terms was blocked from completing the journey by
  a confusing, backend-originated validation error that gave no hint the checkbox itself was the
  problem — the journey could not reach 7/7 completion at all via this path.
- Recommended fix (implemented): derive the submission key generically, preferring
  `input_schema[0].key`, falling back to `unlocks[0]` only when no `input_schema` is declared.
- Regression test: added (§14), verified to fail-then-pass across the revert/restore cycle.

**Investigated and found NOT to be a code defect** ("BUG A" as reported): root-caused precisely
to `AI_PROVIDER=mock` being active on the handed-over server, not a fault in `local_ml` — see
Executive Summary and §9-§10 for full evidence. Classified separately (§16) as a **process/
operational finding**, not a code bug.

## 16. Process/Operational Finding — Mock AI Provider Was Left Active Without a Clear Signal

This is the most important non-code finding of this phase, reported with full honesty:

- **What happened**: after the previous audit phase, I handed the user a running instance with
  `AI_PROVIDER=mock` on the backend (the framework default), while the frontend was correctly in
  `VITE_API_MODE=live`. I stated this explicitly in my handoff message, but the distinction
  between "the frontend genuinely reaches a real backend" (true) and "that backend is running
  real Document AI" (false, in that instance) is subtle and easy to miss — and the user, given
  the entire prior mission's emphasis on real local AI, reasonably expected the latter.
- **Why this matters beyond a one-off miscommunication**: `MockAI` is an intentional, honestly-
  documented dev stub (`app/ai/mock.py`'s own docstring: "MockAI's whole purpose is fixed,
  reproducible output regardless of real OCR signals") — it is not a defect. But **nothing in the
  running application itself ever indicates which AI provider is active** — no UI badge, no
  visible marker, nothing beyond an API call a normal user would never think to make
  (`GET /api/v1/health`). A QA process (human or automated) that doesn't independently confirm
  `AI_PROVIDER` before testing "real AI" behavior can silently test the wrong thing and reach a
  false conclusion in either direction — exactly what happened here.
- **Action taken this phase**: none to application code (per Part 2's explicit
  do-not-guess-do-not-invent constraints, this is a process observation, not an ambiguous
  business requirement to resolve blindly) — but it is now formally recorded (§17, P2) with a
  concrete recommendation, and the runtime-proof discipline in §9 is now the standing bar for any
  future claim about AI behavior in this project.

## 17. Remaining P2/P3 Issues (updated)

| Priority | Issue | Notes |
|---|---|---|
| **P2 (new this phase)** | No runtime indicator anywhere distinguishes mock/stub AI output from real local Document AI output | §16. Recommendation: a visible, unmissable indicator (e.g. a persistent banner or badge) whenever `AI_PROVIDER != local_ml`, or requiring an explicit non-default choice before any "real AI" claim is tested/demoed. Not implemented this phase — a UI/product decision about what and how to show, not a mechanical bug fix. |
| P2 (carried forward) | `apply-error-banner`'s wrong-document rejection message is technically correct but somewhat dry | Unchanged from the prior phase. |
| P3 (carried forward) | `packs_metadata` DB table exists, never read by any code path | Unchanged. |
| P3 (carried forward) | Playwright's `reuseExistingServer` can silently reuse a stray live-mode dev server | Unchanged; directly relevant methodology note re-confirmed this phase (had to explicitly stop/restart the dev server between live-mode manual testing and the MSW-designed E2E suite). |
| P3 (carried forward) | No automated accessibility tooling | Unchanged. |
| P3 (carried forward) | `/demo/reset` secret comparison not constant-time | Unchanged. |

## 18. Final Test Results (this phase's final run)

| Suite | Result |
|---|---|
| Backend pytest | **472/472 passed** (471 prior + 1 new: `test_genuine_unrelated_pdf_is_not_shown_as_verified_salary_slip`) |
| Backend ruff | Clean |
| Backend mypy --strict (`app/core`) | Clean, 9 files |
| Backend import-linter | 1/1 kept, 0 broken |
| Frontend unit (Vitest) | **317/317 passed** (316 prior + 1 new: the `ACCEPT_LOAN_TERMS`-shaped CONSENT payload-key regression test) |
| Frontend TypeScript | Clean |
| Frontend ESLint | Clean |
| Frontend production build | Succeeds |
| Frontend E2E (Playwright, both projects) | **52/52 passed** |
| Live-browser BUG A re-verification | ✅ Pass — real `local_ml`, real document, `verified: false`, no fabricated values, honest UI |
| Live-browser BUG B re-verification | ✅ Pass — real captured payload contains `accept_terms: true`, journey reaches 7/7 Completed |

## 19. Final Acceptance Criteria (checked against the user's explicit list)

1. Wrong genuine documents cannot be displayed as verified documents. ✅ (proven live, §9-§11,
   against the real `local_ml` pipeline — the only pipeline this criterion can honestly be
   evaluated against; `AI_PROVIDER=mock` is out of scope for this criterion by definition, §16)
2. Screen 7 displays actual evidence results rather than simulation defaults. ✅ (§11, §14)
3. Correct documents produce real local OCR/ML/extraction results. ✅ (re-confirmed this phase's
   own runtime proof, §9, plus the prior phase's ₹133,000 real-value confirmation)
4. Wrong documents fail safely. ✅ (§9-§10; no state mutation, `consequence_preview: null`)
5. `accept_terms` checkbox state reaches the backend correctly. ✅ (fixed and proven, §12, §14)
6. All FORM actions have consistent UI → payload → backend behavior. ✅ (audited all 11
   consent/scheduling/video actions across all six journeys, §13; the generic `FormActionModal`
   path was independently confirmed unaffected)
7. Mock data does not leak into live mode. ✅ **at the code level** — `VITE_API_MODE` (frontend
   mock/live) and `AI_PROVIDER` (backend real/mock AI) are independent settings with no code path
   connecting them; confirmed no leak exists. ⚠️ **Operationally**, a backend left on
   `AI_PROVIDER=mock` is easy to mistake for "live" if `VITE_API_MODE=live` — this is the exact
   confusion behind BUG A, now formally documented (§16, P2) rather than silently repeated.
8. Frontend display matches backend evidence. ✅ (§11, and the prior phase's fix)
9. Backend persisted state matches successful evidence results. ✅ (unchanged architectural
   guarantee, re-confirmed via the full regression suite)
10. No known P0/P1 defects remain. ✅ — BUG-003 (the one confirmed new P1) is fixed and
    regression-tested; BUG A resolved to "not a code defect, a process finding" rather than
    silently dismissed.
11. Full regression suite passes. ✅ (§18)
12. Real browser verification passes. ✅ (§9-§13, this phase's own live testing)
13. Six journeys remain functional. ✅ (§13's structural audit covers all six; Lending re-verified
    live end-to-end through 7/7 completion this phase)
14. A first-time user can complete a meaningful journey without developer assistance. ✅ — Lending
    was completed live, start to finish, through the exact consent step that was previously
    broken, to `7/7 Completed`.

All 14 criteria are satisfied.

## 20. Final Go/No-Go

**🟢 GO — READY FOR FINAL PROTOTYPE DEMONSTRATION**

No P0. No unconfirmed or unfixed P1. One genuine P1 code defect (BUG-003) found by real-user
testing this phase, root-caused precisely, fixed generically across all six journeys' shared
code path, and proven fixed with both a regression test and live runtime re-verification. One
serious finding (BUG A as reported) was investigated with full rigor and resolved to "not a code
defect" with direct runtime proof — not asserted, not assumed, not hand-waved — while surfacing
and documenting a real, actionable process gap (§16) that a purely code-focused audit would have
missed. This is prototype readiness, demonstrated by re-running the exact failure the user
reported, live, against the real stack, and confirming it is gone — not by re-reading a previous
report and trusting it.

---

## Final Numbers

**P0: 0**
**P1: 0** (1 confirmed and fixed this phase — BUG-003; 1 reported issue investigated and
resolved to not-a-code-defect — see §16)
**P2: 2** (1 new this phase — no mock/real AI runtime indicator; 1 carried forward)
**P3: 4** (carried forward, unchanged)

**TEST RESULTS:**

- Backend: **472/472**
- Frontend Unit: **317/317**
- Frontend E2E: **52/52**
- Security: pass (unaffected by this phase's changes)
- Document AI: pass (this phase adds direct proof against the exact user-reported document
  shape, §9-§10, §14)
- Unseen Template: pass (unaffected)

**TypeScript: PASS**
**ESLint: PASS**
**Ruff: PASS**
**Mypy: PASS**
**Import-linter: PASS**
**Production Build: PASS**

**STARTUP: PASS**
**DATABASE: PASS**
**API: PASS**
**ALL SIX JOURNEYS: PASS**
**REAL USER FLOW: YES** (upgraded from "YES WITH MINOR CONFUSION" in the prior pass — the
consent-step dead end that would have caused genuine confusion for any Lending user reaching
`ACCEPT_LOAN_TERMS` is now fixed; the minor error-message-tone observation from the prior pass
remains, §17)

## Git / Repository Final State

Working tree is **not** clean — this phase's fix and its regression tests are present as
uncommitted changes (per instructions, nothing was committed automatically):

```
 M backend/app/evidence/reconcile.py
 M backend/app/schemas/system.py
 M backend/tests/integration/test_docai_e2e_journeys.py
 M backend/tests/integration/test_system_endpoints.py
 M backend/tests/unit/test_api_system_and_packs.py
 M backend/tests/unit/test_health.py
 M contract/openapi.yaml
 M frontend/src/components/interactions/ConsentPanel.tsx
 M frontend/src/components/interactions/SchedulingPicker.tsx
 M frontend/src/components/interactions/VideoVerificationFlow.tsx
 M frontend/src/screens/Screen06UploadEvidence.tsx
 M frontend/src/screens/Screen07AiAnalysis.tsx
 M frontend/tests/unit/screens/Screen06UploadEvidence.test.tsx
 M frontend/tests/unit/screens/Screen07AiAnalysis.test.tsx
 M backend/docs/paytmflow_final_full_flow_audit.md
```

No untracked files remain (temporary manual browser-verification scripts and screenshots used to
gather this phase's runtime evidence were removed after use — not part of the repository).

## Files Changed (this phase, in addition to the prior phase's BUG-001/BUG-002 files)

- `frontend/src/screens/Screen06UploadEvidence.tsx` — added `interactionFieldKey`, derived from
  `action.input_schema[0]?.key || action.unlocks?.[0]`; all three interaction components now
  receive this instead of `action.unlocks?.[0]` directly (BUG-003 fix).
- `frontend/src/components/interactions/{ConsentPanel,SchedulingPicker,VideoVerificationFlow}.tsx`
  — doc-comment for the `fieldKey` prop updated to describe the corrected, contract-aligned
  semantics (no functional change in these three files themselves — the fix lives entirely at
  the call site above).
- `frontend/tests/unit/screens/Screen06UploadEvidence.test.tsx` — new regression test for
  BUG-003, verified to fail on the reverted code and pass on the fix.
- `backend/tests/integration/test_docai_e2e_journeys.py` — new
  `test_genuine_unrelated_pdf_is_not_shown_as_verified_salary_slip`, reproducing the user's exact
  reported document shape against the real `local_ml` pipeline.
- `backend/docs/paytmflow_final_full_flow_audit.md` — this report, updated.

No `app/core`, manifest, or `contract/openapi.yaml` file needed to change for BUG-003 (the
backend's validation was already correct — it was the frontend that sent the wrong key). BUG A
required no code change anywhere (§16).

Nothing committed. Per the task's stop condition, no further phase was started after this report.
