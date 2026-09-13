from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.schemas.errors import ErrorEnvelope
from app.schemas.journeys import ActionResponse, ApplyActionRequest
from app.security.session import get_current_session, verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/actions",
    response_model=ActionResponse,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
        409: {"model": ErrorEnvelope, "description": "Action stale"},
        422: {"model": ErrorEnvelope, "description": "Action invalid"},
    },
    tags=["journeys"],
    operation_id="applyAction",
)
async def apply_action(
    journey_id: UUID,
    body: ApplyActionRequest,
    journey: JourneyModel = Depends(verify_journey_ownership),
    session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ActionResponse:
    return await JourneyService.apply_action(
        journey=journey,
        session=session,
        action_id=body.action_id,
        expected_snapshot_id=body.expected_snapshot_id,
        idempotency_key=body.idempotency_key,
        action_input=body.input,
        db=db,
    )
