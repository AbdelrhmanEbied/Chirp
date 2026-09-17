"""Timeline service domain logic."""

from __future__ import annotations

import logging
from typing import Any

from chirp_common.http.client import ServiceClient
from app.repository import TimelineRepository
from app.schemas import FeedResponse, TimelineEntry
from app.settings import TimelineSettings

log = logging.getLogger(__name__)


class TimelineService:
    def __init__(
        self,
        *,
        repository: TimelineRepository,
        user_client: ServiceClient,
        settings: TimelineSettings,
    ) -> None:
        self._repo = repository
        self._user_client = user_client
        self._settings = settings

    async def get_home_feed(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Build the authenticated user's home feed.

        Fan-out on write: reads from pre-computed feed_entries table.
        """
        return await self._repo.get_home_feed(user_id, limit, cursor)

    async def get_user_timeline(
        self, user_id: str, limit: int, cursor: str | None
    ) -> FeedResponse:
        """Posts by a specific user."""
        return await self._repo.get_user_timeline(user_id, limit, cursor)
