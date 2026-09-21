import json
from typing import Any

import httpx
import structlog

from app.ai.chat_context import build_diff_context, build_other_valid_actions
from app.ai.mock import MockAI
from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.ai.provider import AIProvider
from app.config import settings
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest
from app.schemas.journeys import JourneyDiff, JourneyStateResponse, RecommendationResponse

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
        resolved_base_url = base_url or settings.AI_BASE_URL.strip() or "https://api.openai.com/v1"
        self.base_url = resolved_base_url.rstrip("/")
        self.fallback_provider = fallback_provider or MockAI()

    async def warmup(self) -> bool:
        """Best-effort: sends a trivial completion to load the model into memory.

        Local servers like Ollama unload an idle model from RAM after a few
        minutes, and the very first request after that takes tens of seconds
        to reload it - long enough to blow past the guardrail timeout and
        silently fall back to the deterministic reply for a real user's
        first message. Called from the app startup hook so that cold load
        happens once, before any user request, not during one. Never raises;
        returns whether it succeeded, purely for startup logging.
        """
        try:
            await self._call_llm(
                system_prompt="You are a helpful assistant.",
                user_prompt="Reply with a single word: ready.",
                max_tokens=5,
                # Cold-loading a multi-GB model into RAM can genuinely take
                # tens of seconds - the request-time guardrail timeout
                # (AI_TIMEOUT_SECONDS) stays short for real users; this
                # one-time startup call can afford to wait much longer.
                timeout_seconds=120.0,
            )
            return True
        except Exception as exc:
            logger.warning("llm_warmup_failed", error=str(exc), base_url=self.base_url)
            return False

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
        timeout_seconds: float | None = None,
    ) -> str:
        """Executes an async HTTP request to the LLM completion endpoint.

        A missing `api_key` is only fatal against the default OpenAI host -
        local OpenAI-compatible servers (Ollama, LM Studio, ...) reached via
        `AI_BASE_URL` take no credential at all, so the Authorization header
        is simply omitted for them rather than raising.
        """
        if not self.api_key and self.base_url == "https://api.openai.com/v1":
            raise ValueError("AI_API_KEY is not configured for LLMProvider")

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else float(settings.AI_TIMEOUT_SECONDS)
        )
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
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
        raw_file: bytes | None = None,
        filename: str | None = None,
    ) -> AIInterpretationResult:
        """Interprets evidence text against pack mappings and detects conflicts.

        `ocr_meta`/`raw_file`/`filename` are accepted for AIProvider Protocol
        compatibility and unused here - the hosted LLM reasons over the text
        itself, not local OCR bounding-box layout or the original file bytes.
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

    async def chat(
        self,
        message: str,
        manifest: JourneyPackManifest,
        journey_state: JourneyStateResponse,
        recommendation: RecommendationResponse | None,
        diff: JourneyDiff | None = None,
    ) -> str:
        """Answers a free-form question about the user's own journey via LLM,

        grounded strictly in the server-computed journey_state/recommendation
        JSON handed in - the model is instructed to answer only from that data.
        """
        try:
            top_action = recommendation.recommendation if recommendation else None
            context = {
                "journey_title": journey_state.display.title,
                "readiness": journey_state.readiness.value,
                "progress": journey_state.progress.model_dump(mode="json"),
                "fields": [
                    {
                        "label": f.label,
                        "status": f.status.value,
                        "explanation": f.explanation,
                    }
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
                "other_valid_actions": build_other_valid_actions(recommendation),
            }
            diff_context = build_diff_context(diff)
            if diff_context is not None:
                context["journey_diff"] = diff_context

            system_prompt = (
                "You are a helpful assistant answering a user's question about their OWN "
                "financial-journey application. Answer ONLY using the JSON context provided - "
                "never invent a status, document, or requirement that isn't in it. If the "
                "context includes a 'journey_diff', use it to explain what changed and why "
                "when asked - never invent a cause that isn't in it, and never claim something "
                "changed if there is no journey_diff. Keep the answer to 1-3 sentences, plain "
                "and friendly. "
                "Do not use banned terms: 'approved', 'approval', 'probability', 'credit score', "
                "'eligibility score', 'readiness score', 'guaranteed'. "
                "Never claim to have taken any action - you are advisory only."
            )
            user_prompt = (
                f"Journey Context:\n{json.dumps(context, indent=2)}\n\nUser Question: {message}\n"
            )

            reply = await self._call_llm(
                system_prompt, user_prompt, temperature=0.2, max_tokens=200
            )
            return reply.strip()
        except Exception as exc:
            logger.warning("llm_chat_fallback_to_mock", error=str(exc))

        return await self.fallback_provider.chat(
            message=message,
            manifest=manifest,
            journey_state=journey_state,
            recommendation=recommendation,
            diff=diff,
        )

    async def general_chat(self, message: str) -> str:
        """Answers a free-form question with no journey context via LLM -

        used before any application exists (e.g. the goal-creation form),
        where there is no journey_state/recommendation to ground against.
        """
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
            reply = await self._call_llm(system_prompt, message, temperature=0.3, max_tokens=200)
            return reply.strip()
        except Exception as exc:
            logger.warning("llm_general_chat_fallback_to_mock", error=str(exc))

        return await self.fallback_provider.general_chat(message)
