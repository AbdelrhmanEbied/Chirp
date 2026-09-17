from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    post_id: str
    author_id: str
    text: str
    likes_count: int = 0
    reposts_count: int = 0
    replies_count: int = 0
    created_at: datetime
    author_username: str | None = None
    author_display_name: str | None = None
    author_avatar_media_id: str | None = None


class FeedResponse(BaseModel):
    entries: list[TimelineEntry]
    next_cursor: str | None = None
    has_more: bool = False
