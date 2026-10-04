from pydantic import BaseModel, ConfigDict, Field

# Outbox event ids are UUID4 strings; accept any short opaque token of the same alphabet.
EVENT_ID_PATTERN = r"^[A-Za-z0-9._:-]{1,64}$"


class ReceiptClaimRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(pattern=EVENT_ID_PATTERN)
    event_type: str = Field(default="", max_length=50)


class ReceiptClaimResponse(BaseModel):
    event_id: str
    claimed: bool
    status: str


class ReceiptCompleteResponse(BaseModel):
    event_id: str
    status: str


class ReceiptReleaseResponse(BaseModel):
    event_id: str
    released: bool
