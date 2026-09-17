from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
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
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> JourneyStateResponse:
    if idempotency_key:
        import hashlib

        from app.db.repositories.idempotency import IdempotencyRepository

        idemp_repo = IdempotencyRepository(db)
        existing = await idemp_repo.get(idempotency_key)
        if existing and existing.session_id == session.id and existing.action_id == "CREATE":
            from app.db.repositories.journeys import JourneyRepository

            repo = JourneyRepository(db)
            journey = await repo.get_by_id(existing.journey_id)
            if journey:
                return await JourneyService.get_journey_state(journey=journey, db=db)

    result = await JourneyService.create_journey(
        session=session,
        journey_type=body.journey_type,
        goal=body.goal,
        natural_language=body.natural_language,
        db=db,
    )

    if idempotency_key:
        import hashlib

        from app.db.repositories.idempotency import IdempotencyRepository

        idemp_repo = IdempotencyRepository(db)
        request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        await idemp_repo.create(
            key=idempotency_key,
            session_id=session.id,
            journey_id=result.journey_id,
            action_id="CREATE",
            request_hash=request_hash,
            response_body=result.model_dump(mode="json"),
            status_code=201,
        )

    return result


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
