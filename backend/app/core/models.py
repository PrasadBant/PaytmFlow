from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class CoreFieldStatus(StrEnum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CoreReadiness(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DEAD_END = "DEAD_END"


@dataclass(frozen=True)
class CoreAmbiguity:
    ambiguity_id: str
    field: str
    reason: str
    question: str
    answer_type: str
    choices: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class CoreFieldState:
    key: str
    label: str
    status: CoreFieldStatus
    value: Any = None
    display_value: str | None = None
    explanation: str | None = None
    resolve_action_id: str | None = None
    mandatory: bool = True
    derived: bool = False
    display: bool = True
    ambiguity: CoreAmbiguity | None = None


@dataclass(frozen=True)
class CoreProgressCounts:
    completed: int
    pending: int
    blockers: int
    total: int


@dataclass(frozen=True)
class CoreSnapshot:
    snapshot_id: UUID
    journey_id: UUID
    journey_type: str
    version_number: int
    readiness: CoreReadiness
    fields: dict[str, CoreFieldState]
    goal: dict[str, Any] = field(default_factory=dict)
    pending_clarification: CoreFieldState | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class CoreFieldChange:
    key: str
    label: str
    from_status: CoreFieldStatus
    to_status: CoreFieldStatus
    display_value: str | None = None
    cause: str | None = None
    cascaded: bool | None = None


@dataclass(frozen=True)
class CoreReadinessDiff:
    from_readiness: CoreReadiness | None = None
    to_readiness: CoreReadiness | None = None


@dataclass(frozen=True)
class CoreProgressDiff:
    from_progress: CoreProgressCounts | None = None
    to_progress: CoreProgressCounts | None = None


@dataclass(frozen=True)
class CoreJourneyDiff:
    from_version: int
    to_version: int
    fields_changed: list[CoreFieldChange] = field(default_factory=list)
    actions_unlocked: list[str] = field(default_factory=list)
    actions_removed: list[str] = field(default_factory=list)
    readiness: CoreReadinessDiff | None = None
    progress: CoreProgressDiff | None = None


@dataclass(frozen=True)
class CheckToken:
    token_id: UUID
    journey_id: UUID
    journey_type: str
    action_id: str
    previous_snapshot_id: UUID
    action_input: dict[str, Any]
    new_values: dict[str, Any]
    direct_fields: list[str]
    created_at: datetime
