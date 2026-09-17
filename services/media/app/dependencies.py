from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from chirp_common.auth.deps import AuthenticatedUser, build_auth_dependencies
from chirp_common.auth.jwt import JWTCodec
from chirp_common.db.session import Database
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import MediaRepository
from app.service import MediaService
from app.settings import MediaSettings
from app.storage import LocalMediaStorage, MediaStorage


@dataclass(slots=True)
class ServiceContext:
    settings: MediaSettings
    database: Database
    storage: MediaStorage
    codec: JWTCodec

    @classmethod
    def create(cls, settings: MediaSettings) -> ServiceContext:
        return cls(
            settings=settings,
            database=Database(settings),
            storage=LocalMediaStorage(settings),
            codec=JWTCodec(
                secret=settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
                issuer=settings.jwt_issuer,
                audience=settings.jwt_audience,
                access_ttl_seconds=settings.access_token_ttl_seconds,
            ),
        )

    async def close(self) -> None:
        await self.database.dispose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


async def get_session(context: Context) -> AsyncIterator[AsyncSession]:
    async with context.database.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_media_service(context: Context, session: DbSession) -> MediaService:
    return MediaService(
        db=session,
        media=MediaRepository(session),
        storage=context.storage,
        settings=context.settings,
    )


MediaSvc = Annotated[MediaService, Depends(get_media_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
