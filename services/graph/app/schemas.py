from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FollowResponse(BaseModel):
    follower_id: str
    followee_id: str
    created_at: datetime


class BlockResponse(BaseModel):
    blocker_id: str
    blocked_id: str
    created_at: datetime


class MuteResponse(BaseModel):
    user_id: str
    muted_id: str
    created_at: datetime


class CheckBlocksRequest(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)
    other_ids: list[str] = Field(max_length=100)


class CheckBlocksResponse(BaseModel):
    blocked_ids: list[str]


class UserSummary(BaseModel):
    """The shape other services embed when they hydrate an author."""

    id: str
    username: str
    display_name: str
