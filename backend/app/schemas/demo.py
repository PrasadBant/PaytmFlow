from pydantic import BaseModel, ConfigDict


class DemoResetResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reset: bool | None = True
    elapsed_ms: int | None = 0
