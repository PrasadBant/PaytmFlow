from typing import Any, Protocol

from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.config import settings
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest


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
    ) -> AIInterpretationResult:
        """Interprets extracted evidence text against manifest mappings and detects conflicts.

        `ocr_meta`, when supplied by the caller, carries real signals from
        the OCR pass (`{"confidence": float, "word_count": int, "engine": str,
        "lines": [{"text", "top", "bottom"}, ...]}` - see app/docai/ocr.py)
        that a real local-inference provider (app/ai/local_ml.py) uses for
        layout-aware extraction and honest confidence composition. It is
        optional and additive: MockAI and LLMProvider both accept and
        ignore it, so this is not a breaking change to either.
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


def get_ai_provider(guardrailed: bool = True) -> AIProvider:
    """Factory retrieving the configured AI provider instance based on settings."""
    base_provider: AIProvider
    if settings.AI_PROVIDER == "llm":
        from app.ai.llm import LLMProvider

        base_provider = LLMProvider()
    elif settings.AI_PROVIDER == "local_ml":
        from app.ai.local_ml import LocalMLProvider

        base_provider = LocalMLProvider()
    else:
        from app.ai.mock import MockAI

        base_provider = MockAI()  # type: ignore

    if guardrailed:
        from app.ai.guardrails import GuardrailedAIProvider

        return GuardrailedAIProvider(base_provider)
    return base_provider
