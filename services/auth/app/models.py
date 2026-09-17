"""Tables owned by the auth service.

Nothing about a user's public identity lives here: no username, no bio, no
avatar. Auth owns *credentials and sessions only*. The public profile is owned
by the user service and joined by id at the application layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from chirp_common.db.base import Base, SoftDeleteMixin, TimestampMixin, ULIDPrimaryKeyMixin
from chirp_common.idempotency import ProcessedEvent  # noqa: F401 - registered on metadata
from chirp_common.ids import ULID_LENGTH
from chirp_common.timeutil import ensure_utc


class Account(ULIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Login credentials for one user. `id` is the user id across all services."""

    __tablename__ = "accounts"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Set once the user service has confirmed the profile exists. Until then
    # the account cannot log in: see `AuthService.register` for why
    # registration is two steps across two services.
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_active(self) -> bool:
        return self.activated_at is not None and self.deleted_at is None


class Session(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    """One refresh token / logged-in device.

    Only the SHA-256 of the refresh token is stored. A database dump therefore
    does not hand an attacker usable sessions.
    """

    __tablename__ = "sessions"

    account_id: Mapped[str] = mapped_column(String(ULID_LENGTH), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Refresh token rotation: the id of the session that replaced this one.
    # Presenting a rotated token is evidence of theft and revokes the chain.
    rotated_to_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH), nullable=True)

    __table_args__ = (
        Index("ix_sessions_account_active", "account_id", "revoked_at"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    def is_usable(self, now: datetime) -> bool:
        return self.revoked_at is None and ensure_utc(self.expires_at) > ensure_utc(now)


__all__ = ["Account", "ProcessedEvent", "Session", "func"]
