import json
from typing import Any

import httpx
import structlog

from app.ai.mock import MockAI
from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.ai.provider import AIProvider
from app.config import settings
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest

logger = structlog.get_logger(__name__)


class LLMProvider:
    """Real LLM Provider adapter for PaytmFlow using OpenAI-compatible API.

    Activated when AI_PROVIDER=llm.
    Features:
    - Structured prompt formatting for goal parsing, evidence reconciliation, and ranking.
    - Resilient fallback to MockAI on missing API key, network degradation, or errors.
    - Full compliance with AIProvider Protocol and pure separation of concerns.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        fallback_provider: AIProvider | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.AI_API_KEY
        self.model = model if model is not None else (settings.AI_MODEL.strip() or "gpt-4o-mini")
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.fallback_provider = fallback_provider or MockAI()

    def _clean_json_text(self, text: str) -> str:
        """Strips markdown code blocks from model response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Executes an async HTTP request to the LLM completion endpoint."""
        if not self.api_key:
            raise ValueError("AI_API_KEY is not configured for LLMProvider")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=float(settings.AI_TIMEOUT_SECONDS)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        """Parses natural language prompt into structured goal fields via LLM."""
        try:
            fields_desc = [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type.value if hasattr(f.type, "value") else str(f.type),
                    "required": f.required,
                    "options": [opt.value for opt in f.options] if f.options else None,
                    "min": f.min,
                    "max": f.max,
                }
                for f in goal_schema
            ]

            system_prompt = (
                "You are an expert financial journey assistant. "
                "Extract structured goal parameters from the user's natural language request. "
                "Respond ONLY with a valid JSON object mapping goal keys to parsed values. "
                "Do not include conversational preamble or markdown backticks."
            )
            user_prompt = (
                f"Journey Type: {journey_type}\n"
                f"Goal Schema: {json.dumps(fields_desc, indent=2)}\n"
                f"User Request: {natural_language}\n"
            )

            raw_text = await self._call_llm(system_prompt, user_prompt)
            clean_text = self._clean_json_text(raw_text)
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.warning(
                "llm_parse_goal_fallback_to_mock",
                journey_type=journey_type,
                error=str(exc),
            )

        return await self.fallback_provider.parse_goal(
            journey_type=journey_type,
            natural_language=natural_language,
            goal_schema=goal_schema,
        )

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
        ocr_meta: dict[str, Any] | None = None,
    ) -> AIInterpretationResult:
        """Interprets evidence text against pack mappings and detects conflicts.

        `ocr_meta` is accepted for AIProvider Protocol compatibility and
        unused here - the hosted LLM reasons over the text itself, not
        local OCR bounding-box layout.
        """
        try:
            mappings_desc = [
                {
                    "doc_type": m.doc_type,
                    "target_field": m.target_field,
                    "confidence_threshold": m.confidence_threshold,
                    "action_id": m.action_id,
                }
                for m in manifest.evidence_mappings
                if m.doc_type == doc_type
            ]

            ambiguities_desc = [
                {
                    "ambiguity_id": a.ambiguity_id,
                    "field": a.field,
                    "reason": a.reason,
                    "question": a.question,
                }
                for a in (manifest.ambiguity_rules or [])
            ]

            system_prompt = (
                "You are an automated financial document verification agent. "
                "Analyze document text against target fields, evaluate confidence, "
                "and identify conflicts against recorded values or ambiguity rules.\n"
                "IMPORTANT: Do NOT make prohibited claims "
                "('approved', 'guaranteed', 'credit score').\n"
                "Respond ONLY with JSON matching schema:\n"
                "{\n"
                '  "verified": true|false,\n'
                '  "confidence": 0.0-1.0,\n'
                '  "detected": [{"key": "k", "label": "L", "display_value": "V", "value": val}],\n'
                '  "summary": "1-sentence factual description",\n'
                '  "conflicts": [{"ambiguity_id": "ID", "field": "k", "message": "msg"}],\n'
                '  "raw_values": {"k": val}\n'
                "}"
            )
            user_prompt = (
                f"Document Type: {doc_type}\n"
                f"Evidence Mappings: {json.dumps(mappings_desc, indent=2)}\n"
                f"Ambiguity Rules: {json.dumps(ambiguities_desc, indent=2)}\n"
                f"Existing Fields: {json.dumps(existing_fields or {}, indent=2)}\n"
                f"Document Content:\n{extracted_text}\n"
            )

            raw_text = await self._call_llm(system_prompt, user_prompt)
            clean_text = self._clean_json_text(raw_text)
            parsed_json = json.loads(clean_text)
            return AIInterpretationResult.model_validate(parsed_json)
        except Exception as exc:
            logger.warning(
                "llm_reconcile_evidence_fallback_to_mock",
                doc_type=doc_type,
                error=str(exc),
            )

        return await self.fallback_provider.reconcile_evidence(
            doc_type=doc_type,
            extracted_text=extracted_text,
            manifest=manifest,
            existing_fields=existing_fields,
            ocr_meta=ocr_meta,
        )

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        """Ranks candidate actions and supplies advisory rationale via LLM."""
        try:
            candidates_desc = [
                {
                    "action_id": a.action_id,
                    "title": a.title,
                    "why": a.why,
                    "satisfies": a.satisfies,
                    "preconditions": a.preconditions,
                }
                for a in candidate_actions
            ]
            fields_summary = {
                k: {
                    "status": (f.status.value if hasattr(f.status, "value") else str(f.status)),
                    "value": f.value,
                }
                for k, f in snapshot.fields.items()
            }

            system_prompt = (
                "You are an AI financial journey guide recommending optimal next action.\n"
                "CRITICAL INVARIANT: Choose recommended_action_id strictly from candidate list.\n"
                "Respond ONLY with JSON:\n"
                "{\n"
                '  "recommended_action_id": "SELECTED_ACTION_ID",\n'
                '  "why": "1-sentence user-facing rationale",\n'
                '  "ranking_order": ["ID1", "ID2"]\n'
                "}"
            )
            readiness_str = (
                snapshot.readiness.value
                if hasattr(snapshot.readiness, "value")
                else str(snapshot.readiness)
            )
            user_prompt = (
                f"Journey Type: {snapshot.journey_type}\n"
                f"Current Readiness: {readiness_str}\n"
                f"Fields: {json.dumps(fields_summary, indent=2)}\n"
                f"Candidate Actions: {json.dumps(candidates_desc, indent=2)}\n"
            )

            raw_text = await self._call_llm(system_prompt, user_prompt)
            clean_text = self._clean_json_text(raw_text)
            parsed_json = json.loads(clean_text)
            return ActionRankingResult.model_validate(parsed_json)
        except Exception as exc:
            logger.warning(
                "llm_select_action_fallback_to_mock",
                error=str(exc),
            )

        return await self.fallback_provider.select_action(
            snapshot=snapshot,
            candidate_actions=candidate_actions,
            manifest=manifest,
        )

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        """Generates friendly, human-readable explanations of status transitions via LLM."""
        try:
            spec = next((f for f in manifest.state_schema if f.key == field_key), None)
            field_label = spec.label if spec else field_key

            system_prompt = (
                "You are a helpful assistant explaining status updates to users. "
                "Provide a concise 1-2 sentence explanation. "
                "Do not use banned terms: 'approved', 'guaranteed', 'credit score', "
                "'eligibility score'."
            )
            user_prompt = (
                f"Field: {field_label} ({field_key})\n"
                f"Transition: From {from_status} to {to_status}\n"
                f"Triggered by Action: {action_id or 'System derivation'}\n"
            )

            explanation = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=150,
            )
            return explanation.strip()
        except Exception as exc:
            logger.warning(
                "llm_explain_fallback_to_mock",
                field_key=field_key,
                error=str(exc),
            )

        return await self.fallback_provider.explain(
            field_key=field_key,
            from_status=from_status,
            to_status=to_status,
            action_id=action_id,
            manifest=manifest,
        )
