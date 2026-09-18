
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.auth.jwt import JWTCodec
from chirp_common.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.http.client import ServiceClient
from chirp_common.security import (
    generate_opaque_token,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from app.models import Account, Session
from app.repository import AccountRepository, SessionRepository
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.settings import AuthSettings

log = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        accounts: AccountRepository,
        sessions: SessionRepository,
        codec: JWTCodec,
        settings: AuthSettings,
        user_client: ServiceClient,
        bus: EventBus,
    ) -> None:
        self._db = db
        self._accounts = accounts
        self._sessions = sessions
        self._codec = codec
        self._settings = settings
        self._users = user_client
        self._bus = bus


    async def register(
        self, payload: RegisterRequest, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        existing = await self._accounts.get_by_email(payload.email)
        if existing is not None:
            raise ConflictError(
                "That email or username is already in use.", code="account_exists"
            )

        account = Account(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
        )
        await self._accounts.add(account)

        await self._users.request(
            "POST",
            "/internal/v1/users",
            json={
                "user_id": account.id,
                "username": payload.username,
                "display_name": payload.display_name,
            },
            retry=True,  # safe: the user service upserts on user_id
        )

        await self._accounts.activate(account)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_REGISTERED,
                producer=self._settings.service_name,
                subject_id=account.id,
                actor_id=account.id,
                payload={"username": payload.username, "display_name": payload.display_name},
            )
        )
        log.info("account registered", extra={"account_id": account.id})
        issued = await self._issue_tokens(account, user_agent=user_agent, ip=ip)
        return issued.pair


    async def login(
        self, payload: LoginRequest, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        account = await self._accounts.get_by_email(payload.email)

        password_hash = account.password_hash if account else _DUMMY_HASH
        matched = verify_password(payload.password, password_hash)

        if account is None or not matched:
            raise UnauthorizedError("Email or password is incorrect.", code="invalid_credentials")
        if not account.is_active:
            raise ForbiddenError(
                "This account is not finished being set up.", code="account_inactive"
            )

        if needs_rehash(account.password_hash):
            account.password_hash = hash_password(payload.password)

        await self._accounts.touch_login(account)
        issued = await self._issue_tokens(account, user_agent=user_agent, ip=ip)
        return issued.pair


    async def refresh(
        self, payload: RefreshRequest, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        token_hash = hash_token(payload.refresh_token)
        session = await self._sessions.get_by_token_hash(token_hash)
        if session is None:
            raise UnauthorizedError("Refresh token is not recognised.", code="invalid_refresh")

        if session.rotated_to_id is not None:
            revoked = await self._sessions.revoke_all(session.account_id)
            await self._db.commit()
            log.warning(
                "refresh token reuse detected, revoked all sessions",
                extra={"account_id": session.account_id, "revoked": revoked},
            )
            raise UnauthorizedError(
                "Refresh token has already been used.", code="refresh_reuse"
            )

        if not session.is_usable(datetime.now(UTC)):
            raise UnauthorizedError("Refresh token has expired.", code="refresh_expired")

        account = await self._accounts.get(session.account_id)
        if account is None or not account.is_active:
            raise UnauthorizedError("Account is no longer active.", code="account_inactive")

        issued = await self._issue_tokens(account, user_agent=user_agent, ip=ip)
        session.rotated_to_id = issued.session_id
        await self._sessions.revoke(session)
        return issued.pair


    async def logout(self, refresh_token: str) -> None:
        session = await self._sessions.get_by_token_hash(hash_token(refresh_token))
        if session is None:
            return
        await self._sessions.revoke(session)

    async def logout_everywhere(self, account_id: str, *, keep_session_id: str | None) -> int:
        return await self._sessions.revoke_all(account_id, except_id=keep_session_id)


    async def change_password(self, account_id: str, payload: ChangePasswordRequest) -> int:
        account = await self._accounts.get(account_id)
        if account is None or not account.is_active:
            raise NotFoundError("Account not found.")
        if not verify_password(payload.current_password, account.password_hash):
            raise UnauthorizedError("Current password is incorrect.", code="invalid_credentials")
        account.password_hash = hash_password(payload.new_password)
        return await self._sessions.revoke_all(account_id)

    async def get_account(self, account_id: str) -> Account:
        account = await self._accounts.get(account_id)
        if account is None or account.deleted_at is not None:
            raise NotFoundError("Account not found.")
        return account

    async def list_sessions(self, account_id: str) -> list[Session]:
        return await self._sessions.list_active(account_id)


    async def _issue_tokens(
        self, account: Account, *, user_agent: str | None, ip: str | None
    ) -> "_IssuedTokens":
        refresh_token = generate_opaque_token()
        session = Session(
            account_id=account.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self._settings.refresh_token_ttl_seconds),
            user_agent=(user_agent or "")[:255] or None,
            ip_address=(ip or "")[:45] or None,
        )
        await self._sessions.add(session)
        await self._sessions.prune_oldest(
            account.id, keep=self._settings.max_active_sessions_per_user
        )

        scopes = ("admin",) if account.is_admin else ()
        access_token, claims = self._codec.issue_access_token(
            user_id=account.id, session_id=session.id, scopes=scopes
        )
        del claims  # the encoded token is what the client needs
        pair = TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._settings.access_token_ttl_seconds,
            user_id=account.id,
        )
        return _IssuedTokens(pair=pair, session_id=session.id)


@dataclass(frozen=True, slots=True)
class _IssuedTokens:

    pair: TokenPair
    session_id: str


_DUMMY_HASH = hash_password("chirp-timing-equaliser-placeholder")
