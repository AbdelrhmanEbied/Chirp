from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.auth.deps import AuthenticatedUser, build_auth_dependencies
from chirp_common.auth.jwt import JWTCodec
from chirp_common.db.session import Database
from chirp_common.events.bus import EventBus
from chirp_common.events.worker import build_event_bus
from app.repository import BookmarkRepository, LikeRepository, PostRepository, RepostRepository
from app.service import PostService
from app.settings import PostSettings


@dataclass(slots=True)
class ServiceContext:
    settings: PostSettings
    database: Database
    bus: EventBus
    codec: JWTCodec

    @classmethod
    def create(cls, settings: PostSettings) -> "ServiceContext":
        return cls(
            settings=settings,
            database=Database(settings),
            bus=build_event_bus(settings, service_name=settings.service_name),
            codec=JWTCodec(
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                access_ttl_seconds=settings.access_token_ttl_seconds,
            ),
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


def get_post_service(context: Context, session: DbSession) -> PostService:
    return PostService(
        db=session,
        posts=PostRepository(session),
        likes=LikeRepository(session),
        reposts=RepostRepository(session),
        bookmarks=BookmarkRepository(session),
        bus=context.bus,
        settings=context.settings,
    )


Posts = Annotated[PostService, Depends(get_post_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
