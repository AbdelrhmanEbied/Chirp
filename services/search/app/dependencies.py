from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from chirp_common.db.session import Database
from chirp_common.events.bus import EventBus
from chirp_common.events.worker import build_event_bus
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import HashtagRepository, PostSearchRepository
from app.service import SearchService
from app.settings import SearchSettings


@dataclass(slots=True)
class ServiceContext:
    settings: SearchSettings
    database: Database
    bus: EventBus

    @classmethod
    def create(cls, settings: SearchSettings) -> ServiceContext:
        return cls(
            settings=settings,
            database=Database(settings),
            bus=build_event_bus(settings, service_name=settings.service_name),
        )

    async def close(self) -> None:
        await self.bus.close()
        await self.database.dispose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


async def get_session(context: Context) -> AsyncIterator[AsyncSession]:
    async with context.database.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_search_service(context: Context, session: DbSession) -> SearchService:
    return SearchService(
        db=session,
        posts=PostSearchRepository(session),
        hashtags=HashtagRepository(session),
        settings=context.settings,
    )


Search = Annotated[SearchService, Depends(get_search_service)]
