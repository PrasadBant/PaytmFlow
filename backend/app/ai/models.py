from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIDetectedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    display_value: str
    value: Any = None


class AIConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ambiguity_id: str
    field: str
    message: str


class AIInterpretationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verified: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    detected: list[AIDetectedField]
    summary: str
    conflicts: list[AIConflict] = Field(default_factory=list)
    raw_values: dict[str, Any] = Field(default_factory=dict)
    # Cross-document-consistency phase: auxiliary facts (name, and a
    # doc_type-scoped identifier) that are NOT manifest target fields and
    # so are deliberately never surfaced in `detected`/`raw_values` (no
    # public-API/wire-contract expansion - `EvidenceInterpretation` in
    # app/schemas/evidence.py is built field-by-field from this object in
    # app/evidence/reconcile.py, never auto-serialized, so this stays
    # internal). The caller persists these into the append-only
    # `evidence.extracted_data` JSON column (never into snapshot state)
    # so a LATER evidence upload in the SAME journey can compare against
    # them - the actual cross-document consistency mechanism.
    auxiliary_facts: dict[str, Any] = Field(default_factory=dict)


class ActionRankingResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recommended_action_id: str
    why: str
    ranking_order: list[str] = Field(default_factory=list)
    # Truthful provenance of this ranking, set by GuardrailedAIProvider:
    # "AI_RANKED" when the inner provider actually answered within schema/timeout,
    # "PLANNER_FALLBACK" when any guardrail path (timeout, malformed output,
    # exception) substituted the deterministic default instead. Never set by the
    # raw provider implementations themselves.
    source: str | None = None
