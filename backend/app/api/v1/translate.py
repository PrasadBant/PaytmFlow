from fastapi import APIRouter, Depends, HTTPException

from app.ai.provider import get_ai_provider
from app.ai.sarvam import SarvamProvider
from app.ai.sarvam_client import SarvamError
from app.config import settings
from app.db.models import SessionModel
from app.schemas.enums import ErrorCode
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.schemas.translate import TranslateRequest, TranslateResponse
from app.security.session import get_current_session

router = APIRouter()


@router.post(
    "/translate",
    response_model=TranslateResponse,
    responses={
        404: {"model": ErrorEnvelope, "description": "Not found or translation not enabled"},
        504: {"model": ErrorEnvelope, "description": "Translation timed out"},
    },
    tags=["ai"],
    operation_id="translateText",
)
async def translate_text(
    body: TranslateRequest,
    _session: SessionModel = Depends(get_current_session),
) -> TranslateResponse:
    """Translates ONE already-generated canonical explanation/chat string
    (Sarvam Mayura). Never applied to amounts, statuses, display_value, or
    resume_screen - the frontend calls this per free-text block, never on
    the whole API response, so numbers and journey state are never at risk
    of being altered by translation (spec: translation must preserve
    amounts, statuses, and system decisions exactly).
    """
    if not settings.SARVAM_ENABLED or not settings.SARVAM_TRANSLATION_ENABLED:
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Translation is not enabled.",
                )
            ).model_dump(mode="json"),
        )

    raw_provider = get_ai_provider(guardrailed=False)
    if not isinstance(raw_provider, SarvamProvider):
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Translation requires the Sarvam AI provider to be configured.",
                )
            ).model_dump(mode="json"),
        )

    try:
        translated = await raw_provider.translate_text(
            body.text, body.target_language_code, body.source_language_code
        )
    except SarvamError as exc:
        raise HTTPException(
            status_code=504,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.AI_TIMEOUT,
                    message="Translation is temporarily unavailable. Please try again.",
                )
            ).model_dump(mode="json"),
        ) from exc

    return TranslateResponse(translated_text=translated)
