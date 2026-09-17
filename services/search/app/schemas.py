from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: str
    post_id: str
    author_id: str
    text: str
    created_at: datetime


class TrendingHashtag(BaseModel):
    hashtag: str
    usage_count: int


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    limit: int
    next_cursor: str | None = None
    has_more: bool = False
