from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "degraded"]
    db: bool
    packs_loaded: int
    packs_supported: int | None = 6
    # "local_ml" (the real, local, offline Document AI provider - see
    # app/ai/provider.py / app/ai/local_ml.py) is a fully-supported,
    # production-used AI_PROVIDER value, not a dev-only mode - omitting
    # it here made GET /health itself 500 whenever the app was actually
    # configured to run its own real Document AI pipeline (found by
    # starting the app with AI_PROVIDER=local_ml, final QA phase). "sarvam"
    # (app/ai/sarvam.py) is the same class of fully-supported value, added
    # for the same reason.
    ai_provider: Literal["mock", "llm", "local_ml", "sarvam"]
    git_sha: str | None = "dev"


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    created: bool
    # Never a login credential - purely a contact address for n8n customer
    # notifications, optionally provided at journey creation. None for
    # every session that never supplied one (the overwhelming majority).
    customer_email: str | None = None
