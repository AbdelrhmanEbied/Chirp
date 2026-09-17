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
from chirp_common.http.client import ServiceClient
from app.repository import ConversationRepository, MessageRepository
from app.service import MessagingService
from app.settings import MessagingSettings


@dataclass(slots=True)
class ServiceContext:
    settings: MessagingSettings
    database: Database
    bus: EventBus
    codec: JWTCodec
    graph_client: ServiceClient

    @classmethod
    def create(cls, settings: MessagingSettings) -> "ServiceContext":
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
            graph_client=ServiceClient(
                base_url=settings.graph_service_url,
                dependency="graph-service",
                service_name=settings.service_name,
                timeout_seconds=settings.http_timeout_seconds,
                connect_timeout_seconds=settings.http_connect_timeout_seconds,
                max_retries=settings.http_max_retries,
            ),
        )

    async def close(self) -> None:
        await self.bus.close()
        await self.database.dispose()
        await self.graph_client.aclose()


def get_context(request: Request) -> ServiceContext:
    return request.app.state.context


Context = Annotated[ServiceContext, Depends(get_context)]


async def get_session(context: Context) -> AsyncIterator[AsyncSession]:
    async with context.database.session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_messaging_service(context: Context, session: DbSession) -> MessagingService:
    return MessagingService(
        db=session,
        conversations=ConversationRepository(session),
        messages=MessageRepository(session),
        bus=context.bus,
        settings=context.settings,
        graph_client=context.graph_client,
    )


Messaging = Annotated[MessagingService, Depends(get_messaging_service)]


def _current_user(request: Request) -> AuthenticatedUser:
    required, _ = build_auth_dependencies(get_context(request).codec)
    return required(request)


CurrentUser = Annotated[AuthenticatedUser, Depends(_current_user)]
