from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import (
    FieldType,
    JourneyType,
    LifecycleStatus,
    PackIcon,
)


class GoalOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: Any
    label: str


class GoalFieldSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    type: FieldType
    label: str
    required: bool
    placeholder: str | None = None
    help_text: str | None = None
    min: float | None = None
    max: float | None = None
    options: list[GoalOption] | None = None


class JourneyPackSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    journey_type: JourneyType
    display_name: str
    description: str
    icon: PackIcon
    flagship_demo: bool
    lifecycle_status: LifecycleStatus


class JourneyPackDetail(JourneyPackSummary):
    schema_version: str
    goal_schema: list[GoalFieldSpec]
    supports_natural_language: bool
    ui_labels: dict[str, str]


class JourneyPacksListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    packs: list[JourneyPackSummary]
