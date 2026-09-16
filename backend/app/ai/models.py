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
    # Human-first real-browser QA finding: an action can legitimately
    # accept MULTIPLE doc_types (e.g. Lending's UPLOAD_INCOME_PROOF takes
    # either SALARY_SLIP or BANK_STATEMENT - two separate
    # evidence_mappings entries, same action_id, same target_field,
    # independently thresholded - a real, pre-existing, deliberate
    # manifest design, not something invented for this fix). The client
    # only ever declares ONE doc_type when uploading (the frontend has no
    # way to know in advance which of several accepted types the user's
    # real file is); a genuinely correct document of the OTHER accepted
    # type was being flagged WRONG_DOCUMENT purely because it didn't match
    # the single declared string. When the local classifier's real
    # prediction lands on a DIFFERENT doc_type than the client declared
    # but that type is still accepted for the same action, this carries
    # the classifier's own actual prediction back to the caller
    # (app/evidence/reconcile.py) so the confidence-threshold/target-field
    # lookup uses the document's REAL type, not the client's guess. Never
    # set by MockAI/LLM providers (both stay internal="ignore"; wire
    # response is unaffected - see EvidenceInterpretation in
    # app/schemas/evidence.py, which does not expose this).
    resolved_doc_type: str | None = None


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
