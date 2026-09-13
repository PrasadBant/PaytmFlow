from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel
from app.db.session import get_db
from app.schemas.errors import ErrorEnvelope
from app.schemas.journeys import JourneyDiff
from app.security.session import verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.get(
    "/journeys/{journey_id}/diff",
    response_model=JourneyDiff,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["journeys"],
    operation_id="getDiff",
)
async def get_diff(
    journey_id: UUID,
    from_ver: int = Query(..., alias="from"),
    to_ver: int = Query(..., alias="to"),
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> JourneyDiff:
    return await JourneyService.get_diff(
        journey=journey,
        from_ver=from_ver,
        to_ver=to_ver,
        db=db,
    )
