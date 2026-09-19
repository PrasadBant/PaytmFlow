from typing import Any, Protocol

from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.config import settings
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest
from app.schemas.journeys import JourneyStateResponse, RecommendationResponse


class AIProvider(Protocol):
    """Protocol for PaytmFlow AI providers (MockAI and LLM adapter).

    Invariant: AI NEVER writes state directly. All AI functions return
    advisory, schema-validated results that are passed through the deterministic
    engine and choke points.
    """

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        """Parses natural language prompt into structured goal field values."""
        ...

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
        """Interprets extracted evidence text against manifest mappings and detects conflicts.

        `ocr_meta`, when supplied by the caller, carries real signals from
        the OCR pass (`{"confidence": float, "word_count": int, "engine": str,
        "lines": [{"text", "top", "bottom"}, ...]}` - see app/docai/ocr.py)
        that a real local-inference provider (app/ai/local_ml.py) uses for
        layout-aware extraction and honest confidence composition. It is
        optional and additive: MockAI and LLMProvider both accept and
        ignore it, so this is not a breaking change to either.

        `raw_file`/`filename`, when supplied, carry the ORIGINAL uploaded
        document bytes (before local OCR ran) - additive for the same
        reason as `ocr_meta`: a vision-based provider that does its own
        document understanding (app/ai/sarvam.py's SarvamProvider, calling
        Sarvam's real Document AI Extract API) needs the source file, not
        just its locally-OCR'd text, to get any benefit from running its
        own OCR/layout model. Every other provider (Mock/LLM/LocalML)
        accepts and ignores these two params.
        """
        ...

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        """Selects and ranks candidate actions with plain-text rationale."""
        ...

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        """Generates friendly, human-readable explanation of state changes or blockers."""
        ...

    async def chat(
        self,
        message: str,
        manifest: JourneyPackManifest,
        journey_state: JourneyStateResponse,
        recommendation: RecommendationResponse | None,
    ) -> str:
        """Answers a free-form question about the user's OWN journey.

        Grounded strictly in the already-computed journey_state/recommendation
        data supplied by the caller - advisory only, never writes state, and
        must never invent facts about the user's application.
        """
        ...

    async def general_chat(self, message: str) -> str:
        """Answers a free-form question with NO journey context at all.

        Used before any journey exists yet (e.g. while filling out the goal
        form) - same advisory-only invariant, but with no application data
        to ground against, so it must never claim to know specifics about a
        user's own (nonexistent) application.
        """
        ...


def get_ai_provider(guardrailed: bool = True) -> AIProvider:
    """Factory retrieving the configured AI provider instance based on settings."""
    base_provider: AIProvider
    guardrail_timeout: float | None = None
    if settings.AI_PROVIDER == "llm":
        from app.ai.llm import LLMProvider

        base_provider = LLMProvider()
    elif settings.AI_PROVIDER == "local_ml":
        from app.ai.local_ml import LocalMLProvider

        base_provider = LocalMLProvider()
    elif settings.AI_PROVIDER == "sarvam":
        from app.ai.local_ml import LocalMLProvider
        from app.ai.sarvam import SarvamProvider

        # Falls back to the real local Document AI pipeline (not MockAI) on
        # any Sarvam failure/timeout/rate-limit - see SarvamProvider's own
        # docstring. Document AI is a genuine async job API and needs more
        # time per call than the generic AI_TIMEOUT_SECONDS (tuned for a
        # single hosted-LLM completion), so this branch gives
        # GuardrailedAIProvider a larger, Sarvam-specific timeout instead.
        base_provider = SarvamProvider(fallback_provider=LocalMLProvider())
        guardrail_timeout = float(settings.SARVAM_TIMEOUT_SECONDS)
    else:
        from app.ai.mock import MockAI

        base_provider = MockAI()  # type: ignore

    if guardrailed:
        from app.ai.guardrails import GuardrailedAIProvider

        return GuardrailedAIProvider(base_provider, timeout_seconds=guardrail_timeout)
    return base_provider
