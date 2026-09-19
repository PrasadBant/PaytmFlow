from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.schemas.errors import ErrorEnvelope
from app.schemas.review import (
    ClaimCaseRequest,
    CustomerReviewStatus,
    EscalateCaseRequest,
    RequestInformationRequest,
    ResolveCaseRequest,
    ReviewCase,
    ReviewCaseAuditResponse,
    ReviewCaseDetail,
    ReviewDashboardMetrics,
    ReviewQueueResponse,
    ReviewSummaryResponse,
    RoleSwitchRequest,
    RoleSwitchResponse,
)
from app.security.reviewer import (
    get_session_role,
    reviewer_display_name,
    set_session_role,
    verify_reviewer,
)
from app.security.session import get_current_session, verify_journey_ownership
from app.services.review_service import ReviewCaseService

router = APIRouter()


@router.post(
    "/review/role",
    response_model=RoleSwitchResponse,
    tags=["review"],
    operation_id="switchPrototypeRole",
)
async def switch_role(
    body: RoleSwitchRequest,
    _response: Response,
    session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> RoleSwitchResponse:
    """Prototype-only: flips the CURRENT session's own role. See
    app/security/reviewer.py's module docstring for why this is not
    real enterprise auth and why it is still backend-enforced."""
    updated = await set_session_role(session, body.role, db)
    return RoleSwitchResponse(role=get_session_role(updated))


@router.get(
    "/review/cases",
    response_model=ReviewQueueResponse,
    responses={403: {"model": ErrorEnvelope, "description": "Not a reviewer"}},
    tags=["review"],
    operation_id="listReviewQueue",
)
async def list_review_queue(
    status: str | None = None,
    priority: str | None = None,
    journey_type: str | None = None,
    mine: bool = False,
    session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueResponse:
    assigned_to_me = reviewer_display_name(session) if mine else None
    cases = await ReviewCaseService.list_queue(
        db,
        status=status,
        priority=priority,
        journey_type=journey_type,
        assigned_to_me=assigned_to_me,
    )
    return ReviewQueueResponse(cases=cases)


@router.get(
    "/review/dashboard",
    response_model=ReviewDashboardMetrics,
    responses={403: {"model": ErrorEnvelope, "description": "Not a reviewer"}},
    tags=["review"],
    operation_id="getReviewDashboardMetrics",
)
async def get_dashboard(
    _session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewDashboardMetrics:
    return await ReviewCaseService.get_dashboard_metrics(db)


@router.get(
    "/review/cases/{case_id}",
    response_model=ReviewCaseDetail,
    responses={
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
    },
    tags=["review"],
    operation_id="getReviewCase",
)
async def get_review_case(
    case_id: UUID,
    _session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCaseDetail:
    return await ReviewCaseService.get_case_detail(db, case_id)


@router.get(
    "/review/cases/{case_id}/customer-view",
    response_model=ReviewCaseDetail,
    responses={
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
    },
    tags=["review"],
    operation_id="getReviewCaseCustomerView",
)
async def get_review_case_customer_view(
    case_id: UUID,
    _session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCaseDetail:
    """Read-only - lets a reviewer see exactly what the customer currently sees."""
    return await ReviewCaseService.get_case_detail(db, case_id)


@router.get(
    "/review/cases/{case_id}/audit",
    response_model=ReviewCaseAuditResponse,
    responses={
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
    },
    tags=["review"],
    operation_id="getReviewCaseAudit",
)
async def get_review_case_audit(
    case_id: UUID,
    _session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCaseAuditResponse:
    entries = await ReviewCaseService.get_audit_trail(db, case_id)
    return ReviewCaseAuditResponse(entries=entries)


@router.post(
    "/review/cases/{case_id}/ai-summary",
    response_model=ReviewSummaryResponse,
    responses={
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found or AI summary disabled"},
    },
    tags=["review"],
    operation_id="summarizeReviewCase",
)
async def summarize_review_case(
    case_id: UUID,
    _session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewSummaryResponse:
    """Advisory-only AI Evidence Summary - built from the same structured
    case data the reviewer already sees. Never a decision; deterministic
    case-state rules remain authoritative (see ReviewCaseService.summarize_case)."""
    return await ReviewCaseService.summarize_case(db, case_id)


@router.post(
    "/review/cases/{case_id}/claim",
    response_model=ReviewCase,
    responses={
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Locked or invalid transition"},
    },
    tags=["review"],
    operation_id="claimReviewCase",
)
async def claim_review_case(
    case_id: UUID,
    body: ClaimCaseRequest,
    session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCase:
    return await ReviewCaseService.claim_case(db, case_id, reviewer_display_name(session), body)


@router.post(
    "/review/cases/{case_id}/resolve",
    response_model=ReviewCaseDetail,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Stale, locked, or invalid transition"},
    },
    tags=["review"],
    operation_id="resolveReviewCase",
)
async def resolve_review_case(
    case_id: UUID,
    body: ResolveCaseRequest,
    session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCaseDetail:
    return await ReviewCaseService.resolve_case(db, case_id, reviewer_display_name(session), body)


@router.post(
    "/review/cases/{case_id}/request-information",
    response_model=ReviewCase,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Stale, locked, or invalid transition"},
    },
    tags=["review"],
    operation_id="requestReviewCaseInformation",
)
async def request_review_case_information(
    case_id: UUID,
    body: RequestInformationRequest,
    session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCase:
    return await ReviewCaseService.request_information(
        db, case_id, reviewer_display_name(session), body
    )


@router.post(
    "/review/cases/{case_id}/escalate",
    response_model=ReviewCase,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        403: {"model": ErrorEnvelope, "description": "Not a reviewer"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Stale, locked, or invalid transition"},
    },
    tags=["review"],
    operation_id="escalateReviewCase",
)
async def escalate_review_case(
    case_id: UUID,
    body: EscalateCaseRequest,
    session: SessionModel = Depends(verify_reviewer),
    db: AsyncSession = Depends(get_db),
) -> ReviewCase:
    return await ReviewCaseService.escalate_case(db, case_id, reviewer_display_name(session), body)


@router.get(
    "/journeys/{journey_id}/review-status",
    response_model=CustomerReviewStatus,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["review"],
    operation_id="getJourneyReviewStatus",
)
async def get_journey_review_status(
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> CustomerReviewStatus:
    """Customer-facing, customer-safe phrasing only - never exposes internal
    case metadata, reviewer identity, or AI confidence numbers."""
    return await ReviewCaseService.get_customer_review_status(db, journey.id)
