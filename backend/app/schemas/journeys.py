from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    ActionKind,
    AnswerType,
    FieldStatus,
    JourneyStatus,
    JourneyType,
    Readiness,
    RecommendationSource,
    ResumeScreen,
)
from app.schemas.packs import GoalFieldSpec


class ProgressCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    completed: int
    pending: int
    blockers: int
    total: int


class AmbiguityChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Any
    label: str


class AmbiguityInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ambiguity_id: str
    reason: str
    question: str
    answer_type: AnswerType
    choices: list[AmbiguityChoice] | None = None


class FieldState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    status: FieldStatus
    value: Any | None = None
    display_value: str | None = None
    explanation: str | None = None
    resolve_action_id: str | None = None
    mandatory: bool | None = None
    ambiguity: AmbiguityInfo | None = None


class DisplayInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    summary: str


class ActionOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_id: str
    title: str
    kind: ActionKind
    why: str | None = None
    unlocks: list[str]
    accepts: list[str] | None = None
    input_schema: list[GoalFieldSpec] | None = None


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    snapshot_id: UUID
    readiness: Readiness
    recommendation: ActionOption | None = None
    alternatives: list[ActionOption]
    minimum_path_length: int
    source: RecommendationSource | None = None


class NewlySatisfied(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str | None = None
    label: str | None = None


class NewlyUnlocked(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_id: str | None = None
    title: str | None = None


class StillBlocked(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str | None = None
    label: str | None = None


class SimulationPreview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    newly_satisfied: list[NewlySatisfied]
    newly_unlocked: list[NewlyUnlocked]
    still_blocked: list[StillBlocked]
    predicted_readiness: Readiness
    progress_before: ProgressCounts
    progress_after: ProgressCounts


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    from_status: FieldStatus
    to_status: FieldStatus
    display_value: str | None = None
    cause: str | None = None
    cascaded: bool | None = None


class ReadinessDiff(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: Readiness | None = Field(None, alias="from")
    to: Readiness | None = None


class ProgressDiff(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: ProgressCounts | None = Field(None, alias="from")
    to: ProgressCounts | None = None


class JourneyDiff(BaseModel):
    model_config = ConfigDict(extra="ignore")

    from_version: int
    to_version: int
    fields_changed: list[FieldChange]
    actions_unlocked: list[str]
    actions_removed: list[str]
    readiness: ReadinessDiff | None = None
    progress: ProgressDiff | None = None


class JourneyStateResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_id: UUID
    journey_type: JourneyType
    schema_version: str
    snapshot_id: UUID
    version_number: int
    readiness: Readiness
    status: JourneyStatus
    fields: list[FieldState]
    progress: ProgressCounts
    pending_clarification: FieldState | None = None
    display: DisplayInfo
    updated_at: datetime | None = None


class ActionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey: JourneyStateResponse
    diff: JourneyDiff
    next_recommendation: RecommendationResponse | None = None


class JourneyListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_id: UUID
    journey_type: JourneyType
    display_name: str
    icon: str
    title: str
    summary: str
    status: JourneyStatus
    readiness: Readiness
    progress: ProgressCounts | None = None
    updated_at: datetime
    resume_screen: ResumeScreen | None = None


class JourneysListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journeys: list[JourneyListItem]


class CreateJourneyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_type: JourneyType
    goal: dict[str, Any]
    natural_language: str | None = None


class ApplyActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_id: str
    expected_snapshot_id: UUID
    idempotency_key: UUID
    input: dict[str, Any] | None = None


class SubmitClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ambiguity_id: str
    field: str
    answer: Any
    expected_snapshot_id: UUID
