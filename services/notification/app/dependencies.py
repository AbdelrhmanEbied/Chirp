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
from app.repository import NotificationRepository
from app.service import NotificationService
from app.settings import NotificationSettings


@dataclass(slots=True)
class ServiceContext:
    settings: NotificationSettings
    database: Database
    bus: EventBus
    codec: JWTCodec

    @classmethod
    def create(cls, settings: NotificationSettings) -> "ServiceContext":
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


def get_notification_service(context: Context, session: DbSession) -> NotificationService:
    return NotificationService(
        db=session,
        notifications=NotificationRepository(session),
        settings=context.settings,
    )


Notifier = Annotated[NotificationService, Depends(get_notification_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
