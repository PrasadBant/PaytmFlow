from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    # Scoped to already-generated canonical explanation/chat text (spec:
    # translation must never touch amounts, statuses, or display_value) -
    # the frontend calls this per-string for customer-facing explanation
    # blocks, never for the whole API response. See app/api/v1/translate.py.
    text: str = Field(..., min_length=1, max_length=2000)
    target_language_code: str = Field(..., min_length=2, max_length=10)
    source_language_code: str = "auto"


class TranslateResponse(BaseModel):
    translated_text: str
