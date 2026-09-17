from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MediaResponse(BaseModel):
    id: str
    owner_id: str
    content_type: str
    file_size: int
    url: str
    state: str
    width: int | None
    height: int | None
    created_at: datetime
