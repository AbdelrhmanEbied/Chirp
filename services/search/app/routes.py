
from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import Search
from app.schemas import SearchResponse, TrendingHashtag

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("/posts", response_model=SearchResponse)
async def search_posts(
    service: Search,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    sort: str = Query(default="relevance", pattern="^(relevance|recent|similarity)$"),
) -> SearchResponse:
    return await service.search_posts(q, limit=limit, cursor=cursor, sort=sort)


@router.get("/users")
async def search_users(
    service: Search,
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    return await service.search_users(q, limit=limit)


@router.get("/trending", response_model=list[TrendingHashtag])
async def get_trending(
    service: Search,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[TrendingHashtag]:
    return await service.get_trending(limit=limit)
