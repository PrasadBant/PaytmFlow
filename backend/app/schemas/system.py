from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "degraded"]
    db: bool
    packs_loaded: int
    packs_supported: int | None = 6
    ai_provider: Literal["mock", "llm"]
    git_sha: str | None = "dev"


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    created: bool
