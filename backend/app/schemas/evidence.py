from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.journeys import JourneyDiff, SimulationPreview


class EvidenceConflict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ambiguity_id: str | None = None
    field: str | None = None
    message: str | None = None


class EvidenceDetectedField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str | None = None
    label: str | None = None
    display_value: str | None = None


class EvidenceInterpretation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verified: bool
    confidence: float
    detected: list[EvidenceDetectedField]
    summary: str
    conflicts: list[EvidenceConflict]


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: UUID
    filename: str
    uploaded_at: datetime
    size_bytes: int | None = None
    interpretation: EvidenceInterpretation
    proposed_action_id: str | None = None
    consequence_preview: SimulationPreview | None = None
    diff_preview: JourneyDiff | None = None
    requires_review: bool | None = None
