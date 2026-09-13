from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.schemas.errors import ErrorEnvelope
from app.schemas.journeys import ActionResponse, SubmitClarificationRequest
from app.security.session import get_current_session, verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/clarifications",
    response_model=ActionResponse,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Action stale"},
        422: {"model": ErrorEnvelope, "description": "Action invalid"},
    },
    tags=["journeys"],
    operation_id="submitClarification",
)
async def submit_clarification(
    journey_id: UUID,
    body: SubmitClarificationRequest,
    journey: JourneyModel = Depends(verify_journey_ownership),
    session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    return await JourneyService.submit_clarification(
        journey=journey,
        session=session,
        ambiguity_id=body.ambiguity_id,
        field=body.field,
        answer=body.answer,
        expected_snapshot_id=body.expected_snapshot_id,
        db=db,
    )
