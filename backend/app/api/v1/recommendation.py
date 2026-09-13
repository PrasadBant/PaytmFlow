from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel
from app.db.session import get_db
from app.schemas.errors import ErrorEnvelope
from app.schemas.journeys import RecommendationResponse
from app.security.session import verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.get(
    "/journeys/{journey_id}/recommendation",
    response_model=RecommendationResponse,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["journeys"],
    operation_id="getRecommendation",
)
async def get_recommendation(
    journey_id: UUID,
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    return await JourneyService.get_recommendation(journey=journey, db=db)
