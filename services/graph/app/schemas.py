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
    blocker_id: str
    target_ids: list[str] = Field(max_length=100)


class CheckBlocksResponse(BaseModel):
    blocked_ids: list[str]


class UserSummary(BaseModel):

    id: str
    username: str
    display_name: str
