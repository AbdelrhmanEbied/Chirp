"""HTTP surface of the timeline service."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, Timeline
from app.schemas import FeedResponse

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])


@router.get("/home", response_model=FeedResponse, summary="Home feed")
async def home_feed(
    user: CurrentUser,
    service: Timeline,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> FeedResponse:
    return await service.get_home_feed(user.id, limit, cursor)


@router.get(
    "/user/{user_id}",
    response_model=FeedResponse,
    summary="User's post timeline",
)
async def user_timeline(
    user_id: str,
    user: CurrentUser,
    service: Timeline,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> FeedResponse:
    return await service.get_user_timeline(user_id, limit, cursor)
