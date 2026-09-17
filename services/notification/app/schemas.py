from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    recipient_id: str
    actor_id: str
    notification_type: str
    subject_id: str
    is_read: bool
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int
