from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.schemas.enums import JourneyStatus, JourneyType
from app.schemas.errors import ErrorEnvelope
from app.schemas.journeys import (
    CreateJourneyRequest,
    JourneysListResponse,
    JourneyStateResponse,
)
from app.security.session import get_current_session, verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.get(
    "/journeys",
    response_model=JourneysListResponse,
    tags=["journeys"],
    operation_id="listJourneys",
)
async def list_journeys(
    status_filter: JourneyStatus | None = Query(None, alias="status"),
    journey_type: JourneyType | None = Query(None),
    limit: int = Query(50, le=200),
    session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JourneysListResponse:
    items = await JourneyService.list_journeys(
        session=session,
        status_filter=status_filter,
        journey_type=journey_type,
        limit=limit,
        db=db,
    )
    return JourneysListResponse(journeys=items)


@router.post(
    "/journeys",
    response_model=JourneyStateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        404: {"model": ErrorEnvelope, "description": "Not found"},
    },
    tags=["journeys"],
    operation_id="createJourney",
)
async def create_journey(
    body: CreateJourneyRequest,
    session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JourneyStateResponse:
    return await JourneyService.create_journey(
        session=session,
        journey_type=body.journey_type,
        goal=body.goal,
        natural_language=body.natural_language,
        db=db,
    )


@router.get(
    "/journeys/{journey_id}",
    response_model=JourneyStateResponse,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["journeys"],
    operation_id="getJourney",
)
async def get_journey(
    journey_id: UUID,
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> JourneyStateResponse:
    return await JourneyService.get_journey_state(journey=journey, db=db)
