from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import (
    JourneyType,
    ReviewCasePriority,
    ReviewCaseStatus,
    ReviewerRole,
    ReviewResolutionType,
)
from app.schemas.journeys import JourneyDiff, JourneyStateResponse


class ReviewEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evidence_id: UUID
    doc_type: str
    filename: str
    uploaded_at: datetime
    verified: bool
    confidence: float | None = None
    extracted_values: dict[str, Any] = {}


class ReviewCase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: UUID
    case_number: str
    journey_id: UUID
    journey_type: JourneyType
    journey_display_name: str
    field_key: str
    reason_code: str
    reason_title: str
    reason_description: str
    priority: ReviewCasePriority
    status: ReviewCaseStatus
    case_version: int
    assigned_reviewer: str | None = None
    is_locked: bool = False
    resolution_type: ReviewResolutionType | None = None
    resolution_reason: str | None = None
    resolution_notes: str | None = None
    requested_information: dict[str, Any] | None = None
    escalation_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class ReviewCaseDetail(ReviewCase):
    model_config = ConfigDict(extra="ignore")

    journey_context: JourneyStateResponse
    evidence: list[ReviewEvidenceSummary]
    impact_preview: JourneyDiff | None = None


class ReviewQueueResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cases: list[ReviewCase]


class ReviewDashboardMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pending_review: int
    under_review: int
    waiting_customer: int
    escalated: int
    resolved_today: int


class ClaimCaseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    expected_case_version: int


class ResolveCaseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resolution_type: ReviewResolutionType
    resolution_reason: str
    resolution_notes: str | None = None
    resolution_value: Any | None = None
    expected_case_version: int


class RequestInformationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requested_docs: list[str]
    customer_message: str
    expected_case_version: int


class EscalateCaseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    escalation_reason: str
    expected_case_version: int


class ReviewCaseAuditEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class ReviewCaseAuditResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entries: list[ReviewCaseAuditEntry]


class RoleSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: ReviewerRole


class RoleSwitchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: ReviewerRole


class CustomerReviewStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    has_open_case: bool
    case_number: str | None = None
    status: ReviewCaseStatus | None = None
    title: str | None = None
    description: str | None = None
    requested_information: dict[str, Any] | None = None
    updated_at: datetime | None = None
