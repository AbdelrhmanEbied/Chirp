from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    participant_ids: list[str] = Field(min_length=1, max_length=50)


class ConversationResponse(BaseModel):
    id: str
    title: str | None = None
    participant_ids: list[str] = Field(default_factory=list)
    last_message_text: str | None = None
    last_message_sender_id: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    created_at: datetime


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    text: str
    created_at: datetime
