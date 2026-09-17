from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    target_type: str = Field(min_length=1, max_length=20)
    target_id: str = Field(min_length=1, max_length=26)
    reason: str = Field(min_length=1, max_length=2000)


class ReportResponse(BaseModel):
    id: str
    reporter_id: str
    target_type: str
    target_id: str
    reason: str
    state: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime


class ReportListResponse(BaseModel):
    reports: list[ReportResponse]
    next_cursor: str | None = None


class ModerationActionRequest(BaseModel):
    action_type: str = Field(min_length=1, max_length=50)
    target_type: str = Field(min_length=1, max_length=20)
    target_id: str = Field(min_length=1, max_length=26)
    reason: str = Field(min_length=1, max_length=2000)


class ModerationActionResponse(BaseModel):
    id: str
    admin_id: str
    action_type: str
    target_type: str
    target_id: str
    reason: str
    created_at: datetime


class ReviewReportRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=2000)
