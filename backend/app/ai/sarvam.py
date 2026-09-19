"""SarvamProvider - real Sarvam AI integration behind the existing AIProvider
Protocol (app/ai/provider.py).

Scope (mirrors LocalMLProvider's own disclosed-scope pattern in
app/ai/local_ml.py): this provider's actual document-intelligence work is in
`reconcile_evidence`, calling Sarvam's real Document AI Extract API
(https://docs.sarvam.ai - `POST /doc-ai/v1/job/extract`, an async job:
create -> poll status -> download result) with a JSON Schema built directly
from the journey pack manifest's OWN `evidence_mappings`/`state_schema` - no
new field vocabulary invented. `chat`/`general_chat` call Sarvam's real
chat-completions endpoint for advisory summaries (used by the Review
Center's "AI Evidence Summary" and the customer assistant). `parse_goal` /
`select_action` / `explain` are out of Sarvam's document/speech/translate
mission and are delegated straight to `fallback_provider` (LocalMLProvider),
same disclosed-scope decision LocalMLProvider itself already makes for its
own out-of-scope methods.

Failure handling (spec: Sarvam must never be a single point of failure):
ANY Sarvam error - disabled/unconfigured, timeout, rate limit, malformed
response, unexpected exception - falls back to `fallback_provider`
(constructed as LocalMLProvider by app/ai/provider.py's factory, NOT
MockAI), and the returned `AIInterpretationResult.provider` is corrected to
reflect which engine actually answered ("sarvam" vs "local_ml"), so source
traceability in the Review Center is never a lie. This provider is then
wrapped by the SAME GuardrailedAIProvider every other provider goes
through (untrusted-content wrapping, banned-word scanning, timeout,
action-id membership checks) - none of that is touched or bypassed here.

Extract job result shape (verified live against a real Sarvam account,
2026-09-19 - see docs/sarvam_integration.md): the downloaded result is a
ZIP archive (not raw JSON, despite `output_format=json`), containing:
- `extraction.json` - the schema-scoped result actually used here:
  `{"data": {field: value}, "field_confidence": {field: 0-1},
  "field_sources": {field: {document_id, filename, page_num}},
  "no_extractable_content": bool}`.
- `pages/<document_id>/page_NNN.json` - a broader, non-schema-scoped
  per-page extraction (every label Sarvam's vision model found on that
  page, not just the requested schema fields) - not consumed here; the
  schema-scoped `extraction.json` already gives per-field confidence and
  per-field page/document source traceability, which is what
  `reconcile_evidence`/`AIInterpretationResult` need.
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any

import structlog

from app.ai.local_ml import LocalMLProvider
from app.ai.models import ActionRankingResult, AIConflict, AIDetectedField, AIInterpretationResult
from app.ai.provider import AIProvider
from app.ai.sarvam_client import (
    SUCCESSFUL_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    SarvamClient,
    SarvamError,
    SarvamInvalidResponseError,
    SarvamJobStatus,
    SarvamProviderError,
    SarvamTimeoutError,
)
from app.config import settings
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest
from app.schemas.enums import FieldType
from app.schemas.journeys import JourneyStateResponse, RecommendationResponse

logger = structlog.get_logger(__name__)

_JSON_TYPE_BY_FIELD_TYPE: dict[FieldType, str] = {
    FieldType.MONEY: "number",
    FieldType.NUMBER: "number",
    FieldType.BOOLEAN: "boolean",
    FieldType.TEXT: "string",
    FieldType.DATE: "string",
    FieldType.ENUM: "string",
}


@dataclass
class SarvamExtraction:
    values: dict[str, Any]
    field_confidence: dict[str, float]
    field_sources: dict[str, dict[str, Any]]
    no_extractable_content: bool


def _parse_extract_payload(raw_bytes: bytes) -> SarvamExtraction:
    """Unzips a Document AI Extract job's downloaded result and parses its
    `extraction.json` - see the module docstring for the verified real
    shape."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile as exc:
        raise SarvamInvalidResponseError(
            "Sarvam extract result was not a valid ZIP archive"
        ) from exc

    try:
        raw_json = archive.read("extraction.json")
    except KeyError as exc:
        raise SarvamInvalidResponseError(
            "Sarvam extract result ZIP has no extraction.json"
        ) from exc

    try:
        payload = json.loads(raw_json)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SarvamInvalidResponseError("Sarvam extraction.json was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise SarvamInvalidResponseError("Sarvam extraction.json was not a JSON object")

    return SarvamExtraction(
        values=payload.get("data") or {},
        field_confidence=payload.get("field_confidence") or {},
        field_sources=payload.get("field_sources") or {},
        no_extractable_content=bool(payload.get("no_extractable_content", False)),
    )


class SarvamProvider:
    """Real Sarvam AI AIProvider - Document AI Extract for evidence
    reconciliation, Sarvam chat for advisory summaries, falling back to a
    genuine local provider (never a stub) on any failure."""

    def __init__(
        self,
        fallback_provider: AIProvider | None = None,
        client: SarvamClient | None = None,
    ) -> None:
        self.fallback_provider = fallback_provider or LocalMLProvider()
        self.client = client or SarvamClient()

    # ---- Out-of-scope methods: delegate to the fallback provider ---------

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        return await self.fallback_provider.parse_goal(journey_type, natural_language, goal_schema)

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        return await self.fallback_provider.select_action(snapshot, candidate_actions, manifest)

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        return await self.fallback_provider.explain(
            field_key, from_status, to_status, action_id, manifest
        )

    # ---- Document AI (the real integration point) -------------------------

    def _build_extract_schema(
        self, doc_type: str, manifest: JourneyPackManifest
    ) -> tuple[dict[str, Any], dict[str, str]] | None:
        """Builds a Sarvam Extract JSON Schema straight from this manifest's
        OWN evidence_mappings/state_schema for the given doc_type - no new
        field vocabulary invented. Returns (schema, {field_key: label})."""
        mappings = [m for m in manifest.evidence_mappings if m.doc_type.upper() == doc_type.upper()]
        if not mappings:
            return None
        field_specs = {f.key: f for f in manifest.state_schema}
        properties: dict[str, Any] = {}
        labels: dict[str, str] = {}
        for mapping in mappings:
            keys = [mapping.target_field, *(mapping.extraction_keys or [])]
            for key in keys:
                spec = field_specs.get(key)
                label = spec.label if spec else key.replace("_", " ").title()
                json_type = _JSON_TYPE_BY_FIELD_TYPE.get(
                    spec.type if spec else FieldType.TEXT, "string"
                )
                properties[key] = {"type": json_type, "description": label}
                labels[key] = label
        if not properties:
            return None
        return {"type": "object", "properties": properties}, labels

    async def _poll_until_terminal(self, job_id: str) -> SarvamJobStatus:
        for _ in range(settings.SARVAM_MAX_POLL_ATTEMPTS):
            status = await self.client.poll_job_status(job_id)
            if status.status in TERMINAL_JOB_STATUSES:
                return status
            await asyncio.sleep(settings.SARVAM_POLL_INTERVAL_SECONDS)
        raise SarvamTimeoutError(
            f"Sarvam extract job {job_id} did not reach a terminal state "
            f"within {settings.SARVAM_MAX_POLL_ATTEMPTS} polls"
        )

    def _detect_conflicts(
        self,
        raw_values: dict[str, Any],
        existing_fields: dict[str, Any],
        manifest: JourneyPackManifest,
    ) -> list[AIConflict]:
        """Deterministic mismatch check between Sarvam's extraction and
        values already on the journey - the AI never decides what a
        conflict MEANS, it only surfaces the disagreement for the
        deterministic layer/reviewer to act on."""
        conflicts: list[AIConflict] = []
        rules_by_field = {r.field: r for r in (manifest.ambiguity_rules or [])}
        for key, new_value in raw_values.items():
            old_value = existing_fields.get(key)
            if old_value is None:
                continue
            mismatched = False
            if isinstance(new_value, int | float) and isinstance(old_value, int | float):
                if old_value != 0 and abs(new_value - old_value) / abs(old_value) > 0.15:
                    mismatched = True
            elif str(new_value).strip().lower() != str(old_value).strip().lower():
                mismatched = True
            if mismatched:
                rule = rules_by_field.get(key)
                ambiguity_id = rule.ambiguity_id if rule else f"SARVAM_MISMATCH_{key.upper()}"
                field_label = key.replace("_", " ")
                conflicts.append(
                    AIConflict(
                        ambiguity_id=ambiguity_id,
                        field=key,
                        message=f"Extracted {field_label} differs from the recorded value.",
                    )
                )
        return conflicts

    async def _fallback_reconcile(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None,
        ocr_meta: dict[str, Any] | None,
        reason: str,
    ) -> AIInterpretationResult:
        logger.info("sarvam_reconcile_evidence_fallback", doc_type=doc_type, reason=reason)
        result = await self.fallback_provider.reconcile_evidence(
            doc_type=doc_type,
            extracted_text=extracted_text,
            manifest=manifest,
            existing_fields=existing_fields,
            ocr_meta=ocr_meta,
        )
        return result.model_copy(update={"provider": "local_ml"})

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
        ocr_meta: dict[str, Any] | None = None,
        raw_file: bytes | None = None,
        filename: str | None = None,
    ) -> AIInterpretationResult:
        if not settings.SARVAM_ENABLED:
            return await self._fallback_reconcile(
                doc_type,
                extracted_text,
                manifest,
                existing_fields,
                ocr_meta,
                reason="sarvam_disabled",
            )
        if not settings.SARVAM_DOCUMENT_ENABLED:
            return await self._fallback_reconcile(
                doc_type,
                extracted_text,
                manifest,
                existing_fields,
                ocr_meta,
                reason="sarvam_document_ai_disabled",
            )
        if not settings.SARVAM_API_KEY:
            return await self._fallback_reconcile(
                doc_type,
                extracted_text,
                manifest,
                existing_fields,
                ocr_meta,
                reason="sarvam_api_key_not_configured",
            )
        if raw_file is None:
            # Manual-details entry path (no uploaded file) - Sarvam's vision
            # model has nothing to look at, so there is genuinely nothing
            # for it to add here; this is not a failure to log loudly about.
            return await self._fallback_reconcile(
                doc_type,
                extracted_text,
                manifest,
                existing_fields,
                ocr_meta,
                reason="no_source_file_for_vision_extraction",
            )

        built_schema = self._build_extract_schema(doc_type, manifest)
        if built_schema is None:
            return await self._fallback_reconcile(
                doc_type,
                extracted_text,
                manifest,
                existing_fields,
                ocr_meta,
                reason="no_evidence_mapping_for_doc_type",
            )
        schema, labels = built_schema

        try:
            job = await self.client.create_extract_job(raw_file, filename or "document", schema)
            status = await self._poll_until_terminal(job.job_id)
            if status.status not in SUCCESSFUL_JOB_STATUSES:
                raise SarvamProviderError(f"Sarvam extract job ended with status={status.status}")

            download_url = await self.client.get_download_url(job.job_id)
            result_bytes = await self.client.download_result(download_url)
            extraction = _parse_extract_payload(result_bytes)

            detected: list[AIDetectedField] = []
            raw_values: dict[str, Any] = {}
            field_confidences: list[float] = []
            for key, label in labels.items():
                if key not in extraction.values:
                    continue
                value = extraction.values[key]
                if value is None:
                    continue
                raw_values[key] = value
                is_money = "income" in key or "amount" in key or "salary" in key
                display_value = (
                    f"₹{int(value):,}"
                    if is_money and isinstance(value, int | float)
                    else str(value)
                )
                detected.append(
                    AIDetectedField(key=key, label=label, display_value=display_value, value=value)
                )
                field_conf = extraction.field_confidence.get(key)
                if isinstance(field_conf, int | float):
                    field_confidences.append(float(field_conf))

            if extraction.no_extractable_content:
                overall_confidence = 0.0
            elif field_confidences:
                overall_confidence = sum(field_confidences) / len(field_confidences)
            elif status.pages_total:
                overall_confidence = (status.pages_succeeded or 0) / status.pages_total
            else:
                overall_confidence = 0.85 if detected else 0.0

            conflicts = self._detect_conflicts(raw_values, existing_fields or {}, manifest)
            verified = (
                bool(detected)
                and status.status == "completed"
                and not conflicts
                and not extraction.no_extractable_content
            )
            doc_label = doc_type.replace("_", " ").title()
            if extraction.no_extractable_content:
                summary = (
                    f"Sarvam Document AI could not read this {doc_label} "
                    "(poor scan quality or no legible text)."
                )
            elif detected:
                summary = (
                    f"Sarvam Document AI extracted {len(detected)} field(s) from this {doc_label}."
                )
            else:
                summary = (
                    f"Sarvam Document AI could not confidently extract fields "
                    f"from this {doc_label} document."
                )

            return AIInterpretationResult(
                verified=verified,
                confidence=round(overall_confidence, 4),
                detected=detected,
                summary=summary,
                conflicts=conflicts,
                raw_values=raw_values,
                provider="sarvam",
            )
        except SarvamError as exc:
            logger.warning(
                "sarvam_reconcile_evidence_provider_error", doc_type=doc_type, error=str(exc)
            )
        except Exception as exc:  # defensive: never let an unexpected error skip the fallback
            logger.warning(
                "sarvam_reconcile_evidence_unexpected_error", doc_type=doc_type, error=str(exc)
            )

        return await self._fallback_reconcile(
            doc_type,
            extracted_text,
            manifest,
            existing_fields,
            ocr_meta,
            reason="sarvam_call_failed",
        )

    # ---- Chat (reviewer summaries, customer assistant) --------------------

    async def chat(
        self,
        message: str,
        manifest: JourneyPackManifest,
        journey_state: JourneyStateResponse,
        recommendation: RecommendationResponse | None,
    ) -> str:
        if (
            not settings.SARVAM_ENABLED
            or not settings.SARVAM_CHAT_ENABLED
            or not settings.SARVAM_API_KEY
        ):
            return await self.fallback_provider.chat(
                message=message,
                manifest=manifest,
                journey_state=journey_state,
                recommendation=recommendation,
            )
        try:
            top_action = recommendation.recommendation if recommendation else None
            context = {
                "journey_title": journey_state.display.title,
                "readiness": journey_state.readiness.value,
                "progress": journey_state.progress.model_dump(mode="json"),
                "fields": [
                    {"label": f.label, "status": f.status.value, "explanation": f.explanation}
                    for f in journey_state.fields
                ],
                "pending_clarification_question": (
                    journey_state.pending_clarification.ambiguity.question
                    if journey_state.pending_clarification
                    and journey_state.pending_clarification.ambiguity
                    else None
                ),
                "recommended_action": (
                    {
                        "title": top_action.title,
                        "why": top_action.why,
                        "kind": top_action.kind.value,
                        "accepts": top_action.accepts,
                        "unlocks": top_action.unlocks,
                    }
                    if top_action
                    else None
                ),
            }
            system_prompt = (
                "You are a helpful assistant answering a user's question about their OWN "
                "financial-journey application. Answer ONLY using the JSON context provided - "
                "never invent a status, document, or requirement that isn't in it. Keep the "
                "answer to 1-3 sentences, plain and friendly. "
                "Do not use banned terms: 'approved', 'approval', 'probability', 'credit score', "
                "'eligibility score', 'readiness score', 'guaranteed'. "
                "Never claim to have taken any action - you are advisory only."
            )
            user_prompt = (
                f"Journey Context:\n{json.dumps(context, indent=2)}\n\nUser Question: {message}\n"
            )
            reply = await self.client.chat_completion(
                system_prompt, user_prompt, temperature=0.2, max_tokens=200
            )
            return reply.strip()
        except Exception as exc:
            logger.warning("sarvam_chat_fallback", error=str(exc))
        return await self.fallback_provider.chat(
            message=message,
            manifest=manifest,
            journey_state=journey_state,
            recommendation=recommendation,
        )

    async def general_chat(self, message: str) -> str:
        if (
            not settings.SARVAM_ENABLED
            or not settings.SARVAM_CHAT_ENABLED
            or not settings.SARVAM_API_KEY
        ):
            return await self.fallback_provider.general_chat(message)
        try:
            system_prompt = (
                "You are PaytmFlow's helpful assistant. The user has not started an "
                "application yet, so you have no specific data about them - answer "
                "general questions about filling out financial application forms "
                "(loans, insurance, KYC, credit cards, accounts, investments) helpfully "
                "and concisely, in 1-3 sentences. "
                "Do not use banned terms: 'approved', 'approval', 'probability', "
                "'credit score', 'eligibility score', 'readiness score', 'guaranteed'. "
                "Never claim to know specifics about a user's own application - "
                "they have none yet."
            )
            reply = await self.client.chat_completion(
                system_prompt, message, temperature=0.3, max_tokens=200
            )
            return reply.strip()
        except Exception as exc:
            logger.warning("sarvam_general_chat_fallback", error=str(exc))
        return await self.fallback_provider.general_chat(message)

    # ---- Speech / Translate (called directly by the API layer, not part of
    # the AIProvider Protocol - see app/api/v1/chat.py and the translate
    # endpoint for callers) -------------------------------------------------

    async def transcribe(
        self, audio_bytes: bytes, filename: str, language_code: str = "unknown"
    ) -> dict[str, Any]:
        if (
            not settings.SARVAM_ENABLED
            or not settings.SARVAM_SPEECH_ENABLED
            or not settings.SARVAM_API_KEY
        ):
            raise SarvamProviderError("Sarvam speech-to-text is disabled or unconfigured")
        result = await self.client.speech_to_text(audio_bytes, filename, language_code)
        transcript = result.get("transcript")
        if transcript is None:
            raise SarvamInvalidResponseError("Sarvam speech-to-text response missing 'transcript'")
        return {"transcript": transcript, "language_code": result.get("language_code")}

    async def translate_text(
        self, text: str, target_language_code: str, source_language_code: str = "auto"
    ) -> str:
        if (
            not settings.SARVAM_ENABLED
            or not settings.SARVAM_TRANSLATION_ENABLED
            or not settings.SARVAM_API_KEY
        ):
            raise SarvamProviderError("Sarvam translation is disabled or unconfigured")
        result = await self.client.translate(text, target_language_code, source_language_code)
        translated = result.get("translated_text")
        if not translated:
            raise SarvamInvalidResponseError("Sarvam translate response missing 'translated_text'")
        return str(translated)
