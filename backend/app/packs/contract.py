from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import (
    ActionKind,
    AnswerType,
    FieldStatus,
    FieldType,
    JourneyType,
    LifecycleStatus,
    PackIcon,
)
from app.schemas.journeys import AmbiguityChoice
from app.schemas.packs import GoalFieldSpec, GoalOption


class ManifestMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_type: JourneyType
    schema_version: str = "1.0.0"
    display_name: str
    description: str
    icon: PackIcon
    flagship_demo: bool = False
    lifecycle_status: LifecycleStatus = LifecycleStatus.SUPPORTED
    supports_natural_language: bool = False


class StateFieldSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    type: FieldType
    mandatory: bool = True
    derived: bool = False
    display: bool = True
    explanation: str | None = None
    default_status: FieldStatus | None = FieldStatus.BLOCKED
    # Matches GoalFieldSpec.options. No current manifest sets this on a state field
    # (extra="ignore" would otherwise have silently dropped it), but app/ai/mock.py's
    # deterministic extraction already reads field_spec.options for ENUM-typed state
    # fields (e.g. LENDING's employment_type) - without this, that read would raise
    # AttributeError instead of a schema-driven value the moment a manifest ever adds
    # options to an enum state field.
    options: list[GoalOption] | None = None


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    target: str
    condition: dict[str, Any] | None = None


class ActionSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_id: str
    title: str
    kind: ActionKind
    why: str | None = None
    satisfies: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    accepts: list[str] | None = None
    input_schema: list[GoalFieldSpec] | None = None
    action_group: str | None = None


class ActionGroupSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    primary: str
    members: list[str]


class EvidenceMappingSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_type: str
    target_field: str
    confidence_threshold: float = 0.80
    action_id: str
    extraction_keys: list[str] | None = None


class AmbiguityRuleSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ambiguity_id: str
    field: str
    reason: str
    question: str
    answer_type: AnswerType
    choices: list[AmbiguityChoice] | None = None
    trigger_condition: dict[str, Any] | None = None


class ReadinessRulesSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mandatory_fields: list[str] = Field(default_factory=list)
    dead_end_conditions: list[dict[str, Any]] | None = None


class JourneyPackManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metadata: ManifestMetadata
    goal_schema: list[GoalFieldSpec]
    state_schema: list[StateFieldSpec]
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    action_groups: dict[str, ActionGroupSpec] | None = None
    evidence_mappings: list[EvidenceMappingSpec] = Field(default_factory=list)
    ambiguity_rules: list[AmbiguityRuleSpec] = Field(default_factory=list)
    readiness_rules: ReadinessRulesSpec
    ui_labels: dict[str, str] = Field(default_factory=dict)
    prohibited_claims: list[str] = Field(default_factory=list)
    simulation_defaults: dict[str, Any] = Field(default_factory=dict)
