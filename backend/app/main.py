import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.actions import router as actions_router
from app.api.v1.chat import router as chat_router
from app.api.v1.clarifications import router as clarifications_router
from app.api.v1.demo import router as demo_router
from app.api.v1.diff import router as diff_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.journeys import router as journeys_router
from app.api.v1.packs import router as packs_router
from app.api.v1.recommendation import router as recommendation_router
from app.api.v1.review import router as review_router
from app.api.v1.system import router as system_router
from app.api.v1.translate import router as translate_router
from app.config import settings
from app.logging import setup_logging
from app.schemas.enums import ErrorCode
from app.schemas.errors import ErrorEnvelope, ErrorObject

setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Fire-and-forget: preloads the local LLM (e.g. Ollama) into memory.

    Only runs when AI_BASE_URL points somewhere other than the default
    OpenAI host - i.e. a local server the chat feature actually depends on
    (see app/ai/local_ml.py's chat()). Scheduled as a background task, never
    awaited here: a real user's FIRST chat message should not be the thing
    that pays a ~50s cold-load cost, but a slow/unavailable local server
    must never block the API from starting or serving every other endpoint
    normally.
    """
    if settings.AI_BASE_URL.strip():
        from app.ai.llm import LLMProvider

        async def _warm() -> None:
            ok = await LLMProvider().warmup()
            logger.info("local_llm_warmup", ready=ok, base_url=settings.AI_BASE_URL)

        asyncio.create_task(_warm())

    yield


app = FastAPI(
    title="PaytmFlow API",
    version="1.0.0",
    description="Canonical API contract for PaytmFlow (spec v4.2).",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS setup
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    field_errors = {}
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", []))
        field_errors[loc] = err.get("msg", "Validation error")

    return JSONResponse(
        status_code=400,
        content=ErrorEnvelope(
            error=ErrorObject(
                code=ErrorCode.VALIDATION_ERROR,
                message="Request validation failed",
                details=field_errors,
            )
        ).model_dump(mode="json"),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    error_code = ErrorCode.VALIDATION_ERROR if exc.status_code == 400 else ErrorCode.ACTION_INVALID
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(
            error=ErrorObject(
                code=error_code,
                message=str(exc.detail),
            )
        ).model_dump(mode="json"),
    )


# Register routers under /api/v1
app.include_router(system_router, prefix="/api/v1")
app.include_router(packs_router, prefix="/api/v1")
app.include_router(journeys_router, prefix="/api/v1")
app.include_router(recommendation_router, prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")
app.include_router(actions_router, prefix="/api/v1")
app.include_router(clarifications_router, prefix="/api/v1")
app.include_router(diff_router, prefix="/api/v1")
app.include_router(demo_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(translate_router, prefix="/api/v1")
