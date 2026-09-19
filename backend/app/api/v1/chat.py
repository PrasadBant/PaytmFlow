from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.ai.sarvam import SarvamProvider
from app.ai.sarvam_client import SarvamError
from app.config import settings
from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.packs.registry import pack_registry
from app.schemas.chat import ChatRequest, ChatResponse, VoiceChatResponse
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


@router.post(
    "/journeys/{journey_id}/chat/voice",
    response_model=VoiceChatResponse,
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid or empty audio"},
        404: {"model": ErrorEnvelope, "description": "Not found or voice input not enabled"},
        504: {"model": ErrorEnvelope, "description": "Transcription timed out"},
    },
    tags=["journeys"],
    operation_id="chatWithAssistantVoice",
)
async def chat_with_assistant_voice(
    journey_id: UUID,
    file: UploadFile = File(...),
    language_code: str = Form("unknown"),
    journey: JourneyModel = Depends(verify_journey_ownership),
    db: AsyncSession = Depends(get_db),
) -> VoiceChatResponse:
    """Voice is an input modality, not an authorization mechanism: the
    transcript is fed into the SAME `AIProvider.chat()` a typed message
    already goes through (grounded strictly in server-computed
    journey_state/recommendation, advisory-only, timeout-guarded,
    banned-word-scanned). A customer saying "approve my loan" gets the same
    grounded reply a typed version of that message would - it is never
    possible for this endpoint to write journey state.
    """
    if not settings.SARVAM_ENABLED or not settings.SARVAM_SPEECH_ENABLED:
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Voice input is not enabled.",
                )
            ).model_dump(mode="json"),
        )

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

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail=ErrorEnvelope(
                error=ErrorObject(code=ErrorCode.VALIDATION_ERROR, message="Empty audio file.")
            ).model_dump(mode="json"),
        )

    # Speech transcription is Sarvam-specific (Saaras) and isn't part of the
    # AIProvider Protocol (see app/ai/sarvam.py's module docstring) - it's
    # called directly on the raw, unwrapped provider instance, same as
    # app/evidence/reconcile.py calls docai_extract_text directly.
    raw_provider = get_ai_provider(guardrailed=False)
    if not isinstance(raw_provider, SarvamProvider):
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Voice input requires the Sarvam AI provider to be configured.",
                )
            ).model_dump(mode="json"),
        )

    try:
        transcription = await raw_provider.transcribe(
            audio_bytes, file.filename or "audio", language_code
        )
    except SarvamError as exc:
        raise HTTPException(
            status_code=504,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.AI_TIMEOUT,
                    message="Could not transcribe audio. Please try again or type your question.",
                )
            ).model_dump(mode="json"),
        ) from exc

    transcript = transcription["transcript"].strip()
    if not transcript:
        raise HTTPException(
            status_code=400,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Could not make out any speech in that recording.",
                )
            ).model_dump(mode="json"),
        )

    journey_state = await JourneyService.get_journey_state(journey=journey, db=db)
    recommendation = await JourneyService.get_recommendation(journey=journey, db=db)

    ai_provider = get_ai_provider()
    reply = await ai_provider.chat(
        message=transcript,
        manifest=manifest,
        journey_state=journey_state,
        recommendation=recommendation,
    )
    return VoiceChatResponse(
        reply=reply, transcript=transcript, language_code=transcription.get("language_code")
    )
