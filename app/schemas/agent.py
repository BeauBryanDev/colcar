
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiRequest, ApiResponse

MessageRole = Literal["agent", "user", "system"]

# Chat models for the Car-Lens agent panel.

class ChatRequest(ApiRequest):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(ApiResponse):
    reply: str
    timestamp: str
    session_id: str | None = None


class ChatMessage(ApiResponse):
    id: str
    role: MessageRole
    content: str
    timestamp: str
