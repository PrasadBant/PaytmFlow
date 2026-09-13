from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.enums import ErrorCode


class ErrorObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None
    current_snapshot_id: UUID | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: ErrorObject
