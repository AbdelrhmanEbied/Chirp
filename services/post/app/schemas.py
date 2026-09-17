from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreatePostRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    reply_to_id: str | None = Field(default=None, min_length=26, max_length=26)
    quote_of_id: str | None = Field(default=None, min_length=26, max_length=26)
    media_ids: list[str] = Field(default_factory=list, max_length=4)


class PostResponse(BaseModel):
    id: str
    author_id: str
    text: str
    reply_to_id: str | None = None
    quote_of_id: str | None = None
    media_ids: list[str] = Field(default_factory=list)
    likes_count: int = 0
    reposts_count: int = 0
    replies_count: int = 0
    quotes_count: int = 0
    liked_by_me: bool = False
    reposted_by_me: bool = False
    created_at: datetime


class PostSummary(BaseModel):
    id: str
    author_id: str
    text: str
    likes_count: int = 0
    reposts_count: int = 0
    replies_count: int = 0
    created_at: datetime
