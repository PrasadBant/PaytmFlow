# PaytmFlow Human-First Final QA

Real-browser QA pass acting as a genuine first-time user, against the real running application
(Docker Postgres → FastAPI with `AI_PROVIDER=local_ml` → Vite dev server in
`VITE_API_MODE=live`). Interactive Claude-in-Chrome was checked for directly this session (by
name and by function) and found unreachable despite being reported as loaded; a real Chromium
browser driven via Playwright against the live stack was used instead — a genuine browser
executing real navigation, real clicks, real file uploads, real network calls, and real console/
network capture, not a mock. One new, confirmed, now-fixed bug was found this round.

## 1. Executive Summary

**🟢 GO — READY FOR FINAL PROTOTYPE DEMONSTRATION.**

This round found and fixed **BUG-004**: a real salary slip using the common Indian payslip
wording "Monthly Net Income" was correctly classified as `SALARY_SLIP` by the real local
classifier, but its income value could not be extracted — the exact user-reported symptom
("Recognized this as a Salary Slip, but could not reliably extract the required value") —
because "Monthly Net Income" was missing from the extractor's small, curated label vocabulary
(`net pay` / `net salary` / `take home` / `net amount payable`). This is a genuine generalization
gap in a deliberately conservative, label-anchored extractor (never a classifier/OCR/threshold
failure, confirmed by direct code tracing), fixed by adding the one missing, realistic label
synonym — the same class of fix already used throughout this file's history, not a hardcode of
any value or filename. Re-verified live: the real `POST /evidence` response now correctly
returns `detected: [{key: "monthly_income", display_value: "₹133,000"}]` for a reconstruction of
the reported document, and Screen 7 visibly shows `₹133,000 / Monthly Net Income`.

Also re-confirmed this round, live, for the first time this session: **Account Opening** and
**Investment** (goal → status → recommendation) render correctly with their own distinct,
journey-appropriate content through the real backend; multi-tab session isolation holds across
two simultaneous browser contexts; mobile (375px) renders cleanly for a third journey
(Credit Card) with zero horizontal overflow.

No P0. No unfixed P1. One new bug found, root-caused, fixed, and regression-tested.

## 2. First-Time User Experience

Evaluated fresh screenshots of Home, Journey Selection, and each journey's goal form
(Lending/Insurance/Credit Card/KYC/Account Opening/Investment, across this and the two prior QA
rounds this session). The purpose is stated plainly ("A deterministic financial-journey recovery
engine" framing is not exposed to the user — the visible copy is "Tell us about your goal" /
"This helps us personalize your recovery journey"). Journey cards use plain-language titles
("Personal Loan", "Health Insurance", "Credit Card") with a one-line description each. The
primary CTA ("Continue →", "Take Action →") is always the single most prominent element on
every screen tested. No unnecessary information or broken visual elements were found.

## 3. Home Experience

Unchanged from the prior QA round's findings (Home renders correctly, primary CTA navigates to
`/start`, journey selection shows all six packs) — re-confirmed passing as part of the automated
E2E suite this round (52/52, §28) and not separately re-screenshotted since no code touching
this screen changed.

## 4. Lending

Tested most extensively across all three QA rounds this session: full happy path (goal → FORM
action → real evidence upload → AI analysis → apply → updated status → consent step → 7/7
complete), wrong-document rejection (a genuine hackathon-presentation-style PDF, correctly
rejected with an honest UI), and — new this round — the "Monthly Net Income" extraction fix,
verified live end-to-end. `ACCEPT_LOAN_TERMS` (previously broken, BUG-003, fixed in the prior
round) was re-confirmed still working via the full regression suite.

## 5. Insurance

Goal-form rendering, cross-journey isolation, and refresh-mid-form behavior were verified live
in a prior round this session; unchanged.

## 6. KYC / Re-KYC

Goal-form rendering (375px mobile) and mistake-recovery (empty-submit inline validation) were
verified live in a prior round this session; unchanged.

## 7. Credit Card

Goal-form rendering and mistake-recovery were verified live in a prior round; **new this round**:
375px mobile rendering confirmed with zero horizontal overflow (`scrollWidth === clientWidth`,
measured programmatically, not eyeballed), and multi-tab isolation (a Credit Card tab and a KYC
tab open simultaneously in separate browser contexts) confirmed to show genuinely different
page content with no leakage.

## 8. Account Opening

**Tested live for the first time this session.** Goal form: "Digital zero-balance savings bank
account" / "Corporate Salary Account" enum options, "Initial Deposit" money field — rendered
correctly, submitted successfully through the real backend, reached Screen 4 (Current Status)
and Screen 5 (Recommendation) without error. Zero console/network errors.

## 9. Investment

**Tested live for the first time this session.** Goal form: "Monthly Systematic Investment
(SIP)" / "One-Time Lump Sum" enum options, "Target Amount" money field — rendered correctly,
reached Screen 5 showing a real, journey-specific recommendation ("Validate Mutual Fund KYC —
Verification against CVL / NDML KRA database"). Zero console/network errors.

## 10. Forms

`ACCEPT_LOAN_TERMS`'s consent checkbox (BUG-003, fixed in the prior round) was re-confirmed:
unchecked → the `consent-confirm-btn` is disabled by the frontend itself, so a normal user
cannot even submit an empty consent — there is no raw backend error to see on this path anymore.
Checked → the real captured network request now correctly contains `accept_terms: true`
(re-verified this round, part of the automated regression, §28). Employment-type and employer-
name generic FORM fields (`SUBMIT_EMPLOYMENT_INFO`, `VERIFY_EMPLOYER_RECORD`) continue to work
correctly through the shared `FormActionModal`/`SchemaForm` path, confirmed live again this
round as part of the Monthly-Net-Income scenario's setup steps.

## 11. Document Upload

Re-confirmed, live, this round: the AI Analysis screen clearly states the filename, a
Verified/Review Needed badge, a plain-language summary sentence, and — now correctly, for a
document using previously-unrecognized wording — the actual extracted value. A first-time user
reading "Recognized as Salary Slip and extracted 1 field(s)" alongside a visible ₹133,000 figure
has a clear, truthful signal of what happened; the previous "could not reliably extract" dead
end for this exact document is gone.

## 12. Local Document AI

**Runtime-proven again this round**, via a direct, live `POST /evidence` capture (not assumed):
for the reconstructed `paytmflow_salary_slip_demo_accepted.pdf` (containing "Monthly Net
Income: INR 1,33,000"), the real local pipeline returned
`detected: [{"key": "monthly_income", "label": "Monthly Net Income", "display_value":
"₹133,000"}]`, `consequence_preview.newly_satisfied` containing `monthly_income`, and
`diff_preview.fields_changed` showing `monthly_income: BLOCKED → SATISFIED, display_value:
"₹133,000"` — the real extracted value, not a simulation default, not a fabricated figure. Root
cause of the ORIGINAL symptom traced precisely to `INCOME_LABELS_SALARY_SLIP` (`app/docai/
extraction.py`) missing this one common label synonym — confirmed by direct unit-level testing
before touching any UI, and confirmed NOT an OCR, classification, confidence-threshold, or
frontend/backend integration issue (all four were checked and ruled out individually).

## 13. Error Recovery

The specific "Bad" example this mission called out — `"Required input field 'accept_terms' is
missing"` shown raw to a user — is no longer reachable through normal use (BUG-003's fix means
the checkbox now submits the correct key; the disabled-until-checked button additionally
prevents an empty submission from ever reaching the backend). A repository-wide check of
`frontend/src/api/errors.ts` confirms the general pattern: whenever the backend supplies a
message, it is shown directly (`error.message || <friendly fallback>`) — per `backend/CLAUDE.md`
own rule ("error.message is written for end users, never a stack trace or an internal
identifier"), which the backend already follows for HTTP-level errors (no stack traces, no
internal identifiers, no 4xx/5xx codes shown raw). **One residual, unconfirmed-but-plausible
risk noted, not fixed**: `deterministic_check.py`'s own `input_schema` validation messages
reference the field's internal `key` (e.g. `accept_terms`) rather than its human `label` (e.g.
"I agree to the loan agreement and repayment terms") — not currently reachable through any
FORM path tested this session (client-side validation or a disabled button intercepts every
case tried), but the underlying message-construction pattern remains, flagged as P3 (§16).

## 14. Loading Experience

Unchanged from prior rounds' findings: `applyAction.isPending`/`isSubmitting` correctly disables
the relevant button and shows a spinner/"Processing..."/"Submitting..." label during every
mutation observed this session (goal form, FORM actions, evidence upload, consent submission).
No infinite spinner, no silent failure, no duplicate-click vulnerability observed in any live
test this round or the prior two.

## 15. Refresh / Back / Forward

Re-confirmed unchanged (prior round): mid-goal-form refresh re-renders the same journey's own
data cleanly; empty-submit followed by browser Back does not crash or corrupt state. Not
re-exercised at every possible stage this round (time-scoped; no code touching navigation/
persistence changed).

## 16. Multi-Tab / Session

**Tested live this round with two genuinely separate Playwright browser contexts** (distinct
cookie jars, i.e. distinct sessions, not just two tabs sharing one session): Context A opened
Credit Card's goal form, Context B opened KYC's goal form, simultaneously. Verified their
rendered page content is genuinely different (`bodyA !== bodyB`), and that Credit-Card-specific
text ("Card Variant") does not appear in the KYC context. No cross-session leakage.

## 17. Mobile

375px viewport re-confirmed clean for a third journey this round (Credit Card): zero horizontal
overflow, form fields and the Continue button fully usable. Combined with the prior rounds'
coverage of Home, Journey Selection, and KYC at 375px, mobile rendering has now been verified
for the shell plus three of six journeys' goal forms specifically, with no defect found in any
of them.

## 18. Visual Professionalism

No new visual defect found this round across Account Opening, Investment, or the Monthly-Net-
Income AI Analysis screen. Consistent with every prior round: card-based layout, consistent
spacing/typography, a single unambiguous primary button per screen, icon+text status badges
(never color alone).

## 19. Accessibility

Not independently re-tested this round with dedicated tooling (none exists in this project,
unchanged, disclosed limitation). Keyboard/focus conventions are enforced by
`frontend/CLAUDE.md` and exercised by the existing component test suite (part of the 317
passing this round).

## 20. Console / Network

**Zero console errors, zero page errors, across every live scenario run this round**: the
Monthly-Net-Income evidence upload, Account Opening's goal submission, Investment's goal
submission, the multi-tab isolation check, and the mobile Credit Card check — all captured
programmatically via Playwright's `console`/`pageerror` listeners, not eyeballed.

## 21. Frontend vs Backend Consistency

Directly compared for the Monthly-Net-Income document: the real `POST /evidence` JSON response
(`detected[0].display_value: "₹133,000"`) exactly matches what Screen 7 visibly rendered
(`₹133,000 / Monthly Net Income`, confirmed by screenshot) exactly matches the `diff_preview`'s
predicted `monthly_income` state change. All three agree. No divergence found in any scenario
tested this round.

## 22. Security

Session isolation re-confirmed live this round via genuinely separate browser contexts (§16),
in addition to the direct cross-session HTTP check performed in the prior round
(`GET /journeys/{id}` with a different session → 404). No new security-relevant code changed
this round (the fix is a pure extraction-vocabulary addition in `app/docai/extraction.py`).

## 23. Performance

No freezing, unexplained long waits, or repeated processing observed in any live scenario this
round — every upload/analysis/submission completed within the same sub-second-to-few-seconds
range established in the prior performance-focused phase's baseline. Not independently
re-measured (no performance-relevant code changed).

## 24. Bugs Found

**BUG-004** (this round)
- Severity: **P2** (meaningful, real, user-facing extraction gap — but fails *safely*: no
  fabricated value was ever shown, only an honest "could not extract" — so it does not meet the
  P1 bar of "misleading financial/document result" or "incorrect state mutation")
- User scenario: uploading a real, correctly-worded salary slip that happens to use "Monthly Net
  Income" instead of one of the four previously-supported label synonyms.
- Reproduction: upload a SALARY_SLIP document whose income line reads "Monthly Net Income: INR
  1,33,000" (or any amount) for `UPLOAD_INCOME_PROOF`.
- Expected: the income value is extracted and displayed.
- Actual (before fix): correctly classified as `SALARY_SLIP`, but `monthly_income` extraction
  returned `None` with `validation_note: "No recognized income label found for SALARY_SLIP."`
- Root cause: `INCOME_LABELS_SALARY_SLIP` (`app/docai/extraction.py`) did not include "Monthly
  Net Income" as a recognized label synonym — confirmed via direct, isolated unit-level testing
  before any UI involvement, ruling out OCR/classification/threshold/integration as the cause.
- File/Function: `app/docai/extraction.py::INCOME_LABELS_SALARY_SLIP` /
  `extract_monthly_income`.
- Fix: added `r"monthly\s*net\s*income"` to the existing label-synonym list — the same
  architecture and convention as the four pre-existing entries; no document/filename-specific
  logic, no hardcoded value.
- Regression test: `test_monthly_net_income_synonym_label`
  (`backend/tests/unit/test_docai_extraction.py`), plus live re-verification via the real
  browser and the real backend (§12).

No other new bug was confirmed this round. The specific raw-error-message concern (§13) was
investigated and found not currently reachable, so it is recorded as a limitation (§16), not a
confirmed bug.

## 25. Bugs Fixed

BUG-004, described above, is fixed and regression-tested. (BUG-001 through BUG-003 from the two
prior QA rounds this session remain fixed; re-confirmed via the full regression suite this
round, §28 — none regressed.)

## 26. Remaining Issues

Carried forward, unchanged from prior rounds (not re-litigated in full here): no runtime
indicator distinguishing mock vs. real AI provider (P2); the wrong-document rejection error
message is correct but slightly dry (P2); `deterministic_check.py`'s validation messages use
internal field keys rather than human labels (P3, newly framed this round as a latent risk, not
a confirmed reachable bug, §13); `packs_metadata` unused DB table (P3); no automated
accessibility tooling (P3); `/demo/reset` non-constant-time comparison (P3).

## 27. Product Decisions Required

None newly identified this round.

## 28. Automated Test Results (final run, this round)

| Suite | Result |
|---|---|
| Backend pytest | **473/473 passed** (472 prior + 1 new: `test_monthly_net_income_synonym_label`) |
| Backend ruff | Clean |
| Backend mypy --strict (`app/core`) | Clean, 9 files |
| Backend import-linter | 1/1 kept, 0 broken |
| Frontend unit (Vitest) | **317/317 passed** (unchanged — no frontend code changed this round) |
| Frontend TypeScript | Clean |
| Frontend ESLint | Clean |
| Frontend production build | Succeeds |
| Frontend E2E (Playwright, both projects) | **52/52 passed** |
| Extraction dataset re-evaluation (Lending, val/test/unseen) | 0.9444/0.9444/0.875 for `monthly_income` — **exact match to the established baseline**, confirming the new label synonym is purely additive with zero regression on any existing document |

## 29. Final Human Acceptance Test

Fresh browser session (new Playwright context, i.e. a genuinely new cookie/session), Home →
Lending, real user flow: goal form filled naturally → two realistic steps of friction
encountered and resolved along the way this session (the previously-broken consent checkbox,
now fixed, and the previously-broken Monthly Net Income extraction, now fixed) → real evidence
uploaded → real AI analysis shown → real state applied → recommendation continued through the
FORM/consent chain → reached completion. A second journey (Account Opening, then Investment)
was started fresh and reached a real, correct, distinct recommendation screen with zero
assistance beyond reading what was on screen.

**Could a first-time user complete the flow without developer assistance?**

**YES.**

(Upgraded from "YES WITH MINOR CONFUSION" at the start of this session's QA work: both concrete
sources of confusion found across this session's three QA rounds — the consent-step dead end
and the "could not extract" dead end for a realistically-worded document — are now fixed and
regression-tested.)

## 30. Final Recommendation

**🟢 GO — READY FOR FINAL PROTOTYPE DEMONSTRATION**

No P0. No unfixed P1. One new P2 found this round, root-caused precisely (not guessed), fixed
with the smallest generic change consistent with this file's own established architecture, and
verified three ways: an isolated unit test, a full-dataset re-evaluation showing zero
regression, and a live real-browser/real-backend re-run of the exact original symptom. Six of
six journeys have now been exercised through a real browser against the real backend across
this session's three QA rounds (some more deeply than others, stated honestly per journey
throughout); the two journeys never before tested live (Account Opening, Investment) were
confirmed working this round with zero errors.

## 31. Round 5 — Continued Human-First Testing (BUG-005 found and fixed)

Continued directly against the running application via Playwright (Claude-in-Chrome remained
unreachable — checked again directly this round, confirmed absent). Went deliberately beyond
the happy path this round: corrupted files, empty files, duplicate/rapid clicks, browser
Back/Forward through a real multi-step flow, and — for the first time this session — a full
real-evidence upload flow (both correct and wrong documents) for **Insurance**, not just
Lending.

**BUG-005 found**: uploading a genuine, real **Bank Statement** image for Lending's "Upload
Income Proof" action produced `"This does not look like the expected Salary Slip. It looks like
a Bank Statement instead."` — a **false rejection of genuinely valid evidence**. Root cause: the
manifest's own `UPLOAD_INCOME_PROOF` action accepts **either** `SALARY_SLIP` **or**
`BANK_STATEMENT` (two real, independently-thresholded `evidence_mappings` entries, same
action_id, same target_field — a deliberate, pre-existing manifest design, not invented for this
fix), but the frontend always declares `doc_type=action.accepts[0]` when uploading (it has no
way to know in advance which of several accepted types the user's real file is), and the
classifier compared the real prediction against that single declared string instead of the full
accepted set. **Audited the blast radius**: this affects 5 EVIDENCE actions across 4 of 6
journeys wherever `accepts` has more than one entry
(`UPLOAD_INCOME_PROOF`/`UPLOAD_WORK_ID` in Lending, `submit_ped_records` in Insurance,
`upload_cancelled_cheque` in Investment, `upload_passport_ovd` in KYC) — every one of them was
silently rejecting a real user's genuinely correct, manifest-accepted document whenever it
wasn't the specific type occupying position zero in `accepts`.

**Fix** (backend only, no frontend/manifest change): `DocumentClassifier.classify()` now accepts
an optional `accepted_doc_types: set[str]` (defaults to `{expected_doc_type}` alone — fully
backward compatible); `LocalMLProvider.reconcile_evidence()` computes this set from every
`evidence_mappings` entry sharing the declared type's own `action_id`, and — once classification
confirms the real document is one of them — uses the classifier's **actual** prediction (not the
client's declared string) for extraction dispatch and the confidence-threshold/target-field
mapping lookup, both here and in the caller (`app/evidence/reconcile.py`). A genuinely wrong
document (neither accepted type) is still correctly rejected — verified by a dedicated
regression-safety test.

**Verified live**: re-uploaded a real `BANK_STATEMENT` image (ground truth `monthly_income:
159000`) through the real upload UI, declared as `SALARY_SLIP` exactly as the real frontend
does. Result: `"Recognized as Bank Statement and extracted 1 field(s)"`, `₹159,000` displayed,
`consequence_preview` correctly showing `monthly_income: BLOCKED → SATISFIED`. No longer
rejected.

**Other findings this round, all confirmed correct, safe, existing behavior — no new bugs**:
- **Corrupted file** (valid JPEG magic bytes, garbage content): correctly handled —
  `"The document could not be read reliably (poor scan quality or no legible text)"`, Review
  Needed state, no crash.
- **Empty (0-byte) file**: correctly rejected client-side with a clear `"Uploaded file is
  empty."` inline error.
- **Duplicate/rapid click** on both a FORM submit button and the evidence Upload button: the
  button disables itself on the very first click (confirmed via Playwright's own retry log —
  the second click attempt found the element "not enabled" / "detached from the DOM" because the
  page had already navigated). Real network capture confirms **exactly one** `POST /actions` and
  **exactly one** `POST /evidence` request fired in each case, never a duplicate.
- **Browser Back/Forward** through goal → status → recommendation (KYC): both directions landed
  on the correct screen every time, no blank screen, no impossible state.
- **Insurance evidence flow**: a genuine wrong document (`OTHER_receipt`) was correctly rejected
  (`verified: false`, `"This does not look like the expected Medical Discharge Summary. It looks
  like a Other instead."`, `consequence_preview: null`) — confirming the BUG-002 preview-gating
  fix from an earlier round generalizes correctly to a second journey, not just Lending.

**Regression tests added**: `test_alternate_accepted_doc_type_is_not_falsely_rejected` and
`test_genuinely_wrong_document_still_rejected_when_action_accepts_multiple_types`
(`tests/integration/test_docai_e2e_journeys.py`); `test_alternate_accepted_doc_type_is_
correctly_accepted_not_rejected` and `test_accepted_doc_types_defaults_to_expected_alone_when_
omitted` (`tests/unit/test_docai_classifier.py`).

**Regression**: full backend suite **477/477** (473 prior + 4 new); Lending's classification/
extraction dataset re-evaluated in full — **exact match to the established baseline** (1.0/
1.0/0.9412 classification, zero drift), confirming the classifier signature change is genuinely
backward-compatible and introduces no accuracy regression. Frontend unaffected (no frontend code
changed this round) — **317/317** unit, **52/52** E2E, TypeScript/ESLint/build all clean.

---

## 32. Round 6 — BUG-006: Stale MSW Service Worker Silently Defeats Live Mode

Immediately after Round 5's fixes, the user reported "it should be in live mode" — a direct,
real-world report that the running application was not behaving like live mode from their own
browser, despite the backend genuinely being configured and confirmed (via a direct `/health`
call) to be `AI_PROVIDER=local_ml` in live mode. Investigated rather than dismissed.

**Root cause, found precisely**: `bootApp()` (`frontend/src/app/boot.ts`) only ever called
`worker.start()` when `VITE_API_MODE=mock` - it never called `worker.stop()` when the mode was
`live`. MSW's browser service worker, once registered for an origin (`http://localhost:5173`),
**persists across page reloads and even dev-server restarts**, independent of which JS bundle
the current page load thinks it's running - it intercepts `/api/v1/*` requests at the browser's
network layer, before the page's own mode check ever runs. Any browser that had EVER loaded this
app in mock mode (the project's own default, and the mode every existing automated E2E test
deliberately uses) would keep silently serving MSW's canned fixture responses even on a later
visit genuinely configured for live mode - making "live mode" not actually live from that real
browser's perspective, with no error, no console warning, nothing to indicate why. This is a
real, confirmed, unambiguous defect in the boot sequence itself, not a one-off misconfiguration.

**Fix**: `bootApp()` now explicitly calls `worker.stop()` when `mode === 'live'` (safe no-op if
no worker was ever registered in that browser) - the smallest possible change, symmetric with
the existing `mode === 'mock'` branch, touching no other file.

**Regression tests added** (`frontend/src/app/boot.test.ts`, 2 new): one proves `worker.stop()`
is called exactly once when `VITE_API_MODE=live` and `worker.start()` is never called; the other
proves the existing mock-mode behavior (`worker.start()`, never `stop()`) is unchanged. **Verified
to actually catch the bug**: reverting the fix locally and re-running the new test fails with
"expected worker.stop() to be called 1 times, but got 0 times" - restoring the fix passes again.

**Regression**: frontend unit **319/319** (317 prior + 2 new), TypeScript/ESLint/build clean,
E2E **52/52** unaffected (the existing suite always runs in mock mode by design, so the new
`else` branch was never exercised by it before - now covered directly by the new unit tests
instead). No backend code touched.

**Practical note for anyone hitting this locally**: the fix takes effect on the *next* real page
load in an affected browser. A hard refresh (or a normal navigation to `http://localhost:5173`)
after this fix is deployed is sufficient - no manual service-worker unregistration needed.

---

## Final Numbers

**P0: 0**
**P1: 0** (BUG-005 and BUG-006 both classified P1 — a false-rejection of genuinely valid evidence
across 4 journeys, and a silent live-mode/mock-mode integrity failure respectively — both found
and fixed this session)
**P2: 1** (BUG-004 from an earlier round, fixed; plus 2 carried forward, unchanged)
**P3: 4** (carried forward; 1 reframed earlier, not newly counted)

**Backend: 477/477**
**Frontend Unit: 319/319**
**Frontend E2E: 52/52**
**Document AI: pass** (classification/extraction re-evaluation shows zero regression, exact baseline match)
**Security: pass** (unaffected by this round's changes; live isolation re-confirmed in prior rounds)

**TypeScript: PASS**
**ESLint: PASS**
**Ruff: PASS**
**Mypy: PASS**
**Import-linter: PASS**
**Production Build: PASS**

**REAL USER: YES**

## Git / Repository Final State

Working tree is **not** clean — this round's fixes, their regression tests, and this report are
present as uncommitted changes, in addition to every prior round's fixes this session (per
instructions, nothing was committed automatically):

```
 M backend/app/ai/local_ml.py
 M backend/app/ai/models.py
 M backend/app/docai/classifier.py
 M backend/app/docai/extraction.py
 M backend/app/docai/models/lending_classifier.joblib
 M backend/app/docai/models/lending_classifier.meta.json
 M backend/app/evidence/reconcile.py
 M backend/app/schemas/system.py
 M backend/data/docai/lending/reports/classifier_metrics.json
 M backend/tests/integration/test_docai_e2e_journeys.py
 M backend/tests/integration/test_system_endpoints.py
 M backend/tests/unit/test_api_system_and_packs.py
 M backend/tests/unit/test_docai_classifier.py
 M backend/tests/unit/test_docai_extraction.py
 M backend/tests/unit/test_health.py
 M contract/openapi.yaml
 M frontend/src/app/boot.test.ts
 M frontend/src/app/boot.ts
 M frontend/src/components/interactions/ConsentPanel.tsx
 M frontend/src/components/interactions/SchedulingPicker.tsx
 M frontend/src/components/interactions/VideoVerificationFlow.tsx
 M frontend/src/screens/Screen06UploadEvidence.tsx
 M frontend/src/screens/Screen07AiAnalysis.tsx
 M frontend/tests/unit/screens/Screen06UploadEvidence.test.tsx
 M frontend/tests/unit/screens/Screen07AiAnalysis.test.tsx
 M backend/docs/paytmflow_final_full_flow_audit.md
?? backend/docs/paytmflow_human_first_final_qa.md
```

No untracked scratch files remain (temporary manual browser-verification scripts and
screenshots used to gather this round's runtime evidence were removed after use).

Nothing committed. Per the task's instructions, no further phase was started after this report.
