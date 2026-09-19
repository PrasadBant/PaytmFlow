from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    reply: str


class VoiceChatResponse(ChatResponse):
    # The transcribed text the assistant actually answered from - shown back
    # to the customer so they can confirm they were heard correctly. Never
    # used for anything beyond display; the reply itself is generated the
    # SAME way a typed message would be (see chat_with_assistant_voice).
    transcript: str
    language_code: str | None = None
