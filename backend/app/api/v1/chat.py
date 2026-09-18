from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.packs.registry import pack_registry
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.enums import ErrorCode
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.security.session import get_current_session, verify_journey_ownership
from app.services.journey_service import JourneyService

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["journeys"],
    operation_id="generalChat",
)
async def general_chat(
    body: ChatRequest,
    current_session: SessionModel = Depends(get_current_session),
) -> ChatResponse:
    """Advisory-only Q&A with NO journey context.

    Used before any application exists (e.g. the goal-creation form) - there
    is no journey_state/recommendation to ground against yet, so this never
    claims to know anything specific about the caller's own application.
    """
    ai_provider = get_ai_provider()
    reply = await ai_provider.general_chat(message=body.message)
    return ChatResponse(reply=reply)


@router.post(
    "/journeys/{journey_id}/chat",
    response_model=ChatResponse,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["journeys"],
    operation_id="chatWithAssistant",
)
async def chat_with_assistant(
    journey_id: UUID,
    body: ChatRequest,
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Advisory-only Q&A about the caller's own journey.

    Grounded in the same server-computed journey_state/recommendation data
    the status/recommendation screens already render - never writes state.
    """
    manifest = pack_registry.get_pack(journey.journey_type)
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.INVALID_JOURNEY_TYPE,
                    message=f"Journey pack '{journey.journey_type}' not found",
                )
            ).model_dump(mode="json"),
        )

    journey_state = await JourneyService.get_journey_state(journey=journey, db=db)
    recommendation = await JourneyService.get_recommendation(journey=journey, db=db)

    ai_provider = get_ai_provider()
    reply = await ai_provider.chat(
        message=body.message,
        manifest=manifest,
        journey_state=journey_state,
        recommendation=recommendation,
    )
    return ChatResponse(reply=reply)
