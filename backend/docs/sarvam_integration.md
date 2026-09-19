# Sarvam AI Integration

## Why Sarvam

PaytmFlow already has a real, local Document AI pipeline (Tesseract/PyMuPDF OCR,
label-anchored regex extraction, a trained document classifier - see
`docai_report.md`). Sarvam AI (India's sovereign AI platform) is integrated as an
**alternative intelligence layer** for the same job, plus three capabilities the
local pipeline doesn't cover: real speech-to-text for Indic languages, translation
of customer-facing explanations, and an advisory reviewer summary. It never
becomes the only option - every Sarvam capability falls back to the existing
local pipeline or a deterministic default on any failure.

## Architecture

```
Customer / Reviewer
        |
        v
     FastAPI
        |
        v
   AIProvider Protocol (app/ai/provider.py)
        |
   +----+---------+--------------+
   |              |              |
MockAI      LocalMLProvider  SarvamProvider (app/ai/sarvam.py)
                                   |
                                   +-- fallback_provider = LocalMLProvider
        |
        v (all three wrapped identically)
  GuardrailedAIProvider (app/ai/guardrails.py)
   - timeout, untrusted-content wrapping, banned-word scan,
     action-id membership check - UNCHANGED for Sarvam
        |
        v
  Evidence Normalizer (app/evidence/reconcile.py)
        |
        v
  Deterministic Validator / Journey Engine (app/core/**)
          /       \
         /         \
   Continue      Ambiguous
                    |
                    v
              Review Center
                    |
                    v
              Human Review
```

`SarvamProvider` is a peer of `LocalMLProvider`/`LLMProvider` behind the exact
same `AIProvider` Protocol - selected via `AI_PROVIDER=sarvam`. It is never a
new architectural layer, and it never bypasses `deterministic_check()` or
writes journey state.

## Supported operations

| Capability | Sarvam API used | Where it's wired in |
|---|---|---|
| Document extraction | Document AI Extract (`POST /doc-ai/v1/job/extract`, async job) | `SarvamProvider.reconcile_evidence` |
| Reviewer AI summary | Chat completions (`POST /chat/completions`) | `ReviewCaseService.summarize_case` |
| Customer assistant (voice) | Speech-to-text (`POST /speech-to-text`, Saaras) | `POST /journeys/{id}/chat/voice` |
| Multilingual explanations | Translation (`POST /translate`, Mayura) | `POST /translate` |

All four endpoint paths were verified against the live Sarvam API
documentation (docs.sarvam.ai) before implementation - none are invented.

## Document AI (priority 1)

`SarvamProvider.reconcile_evidence`:
1. Builds a JSON Schema from the journey pack manifest's own
   `evidence_mappings`/`state_schema` for the submitted `doc_type` - no new
   field vocabulary, reusing exactly the canonical fields (`monthly_income`,
   `employer_name`, etc.) every other provider already targets.
2. Submits the ORIGINAL uploaded file bytes (not the locally-OCR'd text) to
   Sarvam's Extract job - this is why `AIProvider.reconcile_evidence` gained
   two new, purely-additive optional parameters, `raw_file`/`filename`
   (every other provider accepts and ignores them, same precedent as the
   existing `ocr_meta` parameter).
3. Polls the job (bounded by `SARVAM_POLL_INTERVAL_SECONDS` /
   `SARVAM_MAX_POLL_ATTEMPTS`) until a terminal status.
4. Normalizes the result into the existing `AIInterpretationResult` contract
   - same `detected`/`confidence`/`summary`/`conflicts`/`raw_values` shape
   every provider already produces, so nothing downstream changes.
5. On ANY failure (disabled, unconfigured, timeout, rate limit, malformed
   response, failed/rejected job, or no source file at all - e.g. the
   manual-entry path) - falls back to `LocalMLProvider`, the real local
   pipeline, and honestly labels the result's `provider` field
   `"local_ml"` rather than `"sarvam"`.

### Remaining limitation (disclosed, not hidden)

Sarvam's public docs confirm the Extract job's *request* schema precisely,
but do not publish a worked example of the downloaded *result* JSON's
field-wrapping. `app/ai/sarvam.py`'s `_parse_extract_payload`/
`_extract_field_value` are written defensively to accept the most likely
shapes (a flat object matching the schema, or one nested under
`fields`/`data`/`extracted`/`result`, each field either a bare value or a
`{"value", "confidence"}` object) - **this should be verified against a
real Sarvam account's actual response** before being relied on in
production. All 15 unit tests in `tests/unit/test_ai_sarvam.py` mock the
HTTP boundary and therefore validate the provider's own logic, not
Sarvam's real response shape.

## Source traceability / provider metadata

- `EvidenceModel.provider` (new column, migration `005_evidence_provider`)
  records which engine actually produced each evidence row's extraction.
- `ReviewEvidenceSummary.provider` surfaces it to the Review Center.
- The frontend (`EvidenceComparisonWorkspace.tsx`, `WhySeeingCase.tsx`) shows
  a plain "Source: Sarvam Vision" / "Source: Local Document AI" line next to
  the existing AI-confidence badge - never a "Powered by AI" banner.

## Reviewer AI summary (advisory only)

`POST /review/cases/{case_id}/ai-summary` builds a summary request entirely
from the already-loaded `ReviewCaseDetail` (customer declaration, extracted
evidence, flagged reason, current status) and calls the SAME
`AIProvider.chat()` every other assistant call uses. The response always
carries a fixed disclaimer ("AI-generated summary. Review system evidence
and deterministic assessment before taking action.") and is rendered in the
Review Center as a clearly separate advisory card, never as a recommended
action.

## Voice input (Saaras)

`POST /journeys/{journey_id}/chat/voice` transcribes the uploaded audio via
Sarvam Saaras, then feeds the transcript into the exact same
`AIProvider.chat()` a typed message already goes through - grounded strictly
in server-computed `journey_state`/`recommendation`, timeout-guarded,
banned-word-scanned. This is what makes "voice cannot bypass business
rules" true by construction: a spoken "approve my loan" produces the same
kind of grounded, advisory reply a typed version would, because it is
answered by the identical code path. Verified in
`tests/integration/test_chat_voice.py::test_voice_cannot_bypass_business_rules`.

## Translation (Mayura)

`POST /translate` translates exactly ONE already-generated free-text string
per call (a chat reply or explanation block) - never a whole API response,
never `display_value`/amount/status fields. The frontend's `AssistantModal`
calls it per-reply when a non-English language is selected in a small
language picker, with a best-effort fallback to the original English text on
any translation failure (never blocks the conversation).

## Failure / fallback matrix

| Failure | Behavior |
|---|---|
| `SARVAM_ENABLED=false` / capability flag off | Falls back immediately (Document AI) or returns a clean 404 (voice/translate/summary) |
| `SARVAM_API_KEY` unset | Same as above |
| Sarvam timeout | `SarvamTimeoutError` -> Document AI falls back to `LocalMLProvider`; voice/translate return 504 |
| Sarvam rate limit (429) | `SarvamRateLimitError` -> same fallback/504 behavior |
| Sarvam 5xx / unreachable | `SarvamProviderError` -> same fallback/504 behavior |
| Malformed/invalid response | `SarvamInvalidResponseError` -> same fallback/504 behavior |
| Extract job `failed`/`rejected` | Falls back to `LocalMLProvider` |
| Extract job `partially_completed` | Treated as a genuine (if lower-confidence) result, not a hard failure |
| No source file (manual-entry evidence path) | Falls back to `LocalMLProvider` immediately, no Sarvam call attempted |

## Security

- `SARVAM_API_KEY` is a backend-only setting (`app/config.py`), read only by
  `app/ai/sarvam_client.py`, sent only as the `api-subscription-key` request
  header. It is never included in any response model, never logged (only
  operation name/status code/duration are logged), and never dumped via
  `settings.model_dump()` anywhere in the codebase.
- Every new endpoint reuses the existing session/reviewer authorization
  dependencies (`verify_journey_ownership`, `verify_reviewer`,
  `get_current_session`) - no new auth mechanism was introduced.

## Configuration

```
AI_PROVIDER=sarvam   # or mock | llm | local_ml
SARVAM_ENABLED=true
SARVAM_API_KEY=<real key>
SARVAM_BASE_URL=https://api.sarvam.ai
SARVAM_DOCUMENT_ENABLED=true
SARVAM_SPEECH_ENABLED=true
SARVAM_TRANSLATION_ENABLED=true
SARVAM_CHAT_ENABLED=true
SARVAM_TIMEOUT_SECONDS=25
SARVAM_POLL_INTERVAL_SECONDS=1.5
SARVAM_MAX_POLL_ATTEMPTS=12
SARVAM_STT_MODEL=saaras:v3
```

Setting `AI_PROVIDER` back to `mock`/`llm`/`local_ml` (or `SARVAM_ENABLED=false`)
disables Sarvam entirely - the rest of PaytmFlow is unaffected either way.

## Testing

- `tests/unit/test_ai_sarvam.py` - 15 tests: successful/partial/failed
  extraction, invalid response, timeout, rate limit, provider error,
  disabled/unconfigured/no-file fallback, confidence/source preservation
  through `GuardrailedAIProvider`, API-key protection.
- `tests/integration/test_review_ai_summary.py` - 3 tests: advisory summary
  content, reviewer-role authorization, disabled-returns-404.
- `tests/integration/test_chat_voice.py` - 6 tests: disabled, wrong
  provider, empty audio, transcription timeout, success, and the explicit
  "voice cannot bypass business rules" property.
- `tests/integration/test_translate.py` - 4 tests: disabled, wrong provider,
  timeout, and text-boundary preservation (numbers pass through unaltered
  inside the translated string).
- Full existing suite (623 backend tests, 374 frontend tests as of this
  integration) re-run and passing - see the final report for the exact
  commands and results.

## AI vs. deterministic responsibilities

Sarvam interprets: it OCRs/extracts document fields, transcribes speech, and
translates/explains. It never approves, rejects, or determines eligibility.
Every Sarvam result is normalized into the same `AIInterpretationResult`
contract as every other provider, passed through the unmodified
`GuardrailedAIProvider` safety net, and only ever reaches
`deterministic_check()` / the journey engine as ordinary evidence - exactly
like a `LocalMLProvider` or `MockAI` result would. If the evidence is clear,
the journey continues; if it's ambiguous or inconsistent, the case still
routes to the Review Center for human resolution, unchanged.
