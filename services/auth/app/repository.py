"""Data access for the auth service.

Keeping SQL behind a repository means the service layer is testable without a
database and the query shapes are all visible in one file when tuning indexes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Session


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> Account | None:
        return await self._session.get(Account, account_id)

    async def get_by_email(self, email: str) -> Account | None:
        return await self._session.scalar(
            select(Account).where(
                func.lower(Account.email) == email.lower(), Account.deleted_at.is_(None)
            )
        )

    async def add(self, account: Account) -> Account:
        self._session.add(account)
        await self._session.flush()
        return account

    async def activate(self, account: Account) -> None:
        account.activated_at = datetime.now(UTC)

    async def touch_login(self, account: Account) -> None:
        account.last_login_at = datetime.now(UTC)

    async def delete(self, account: Account) -> None:
        await self._session.delete(account)
        await self._session.flush()

    async def soft_delete(self, account: Account) -> None:
        account.deleted_at = datetime.now(UTC)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: Session) -> Session:
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        return await self._session.scalar(
            select(Session).where(Session.token_hash == token_hash)
        )

    async def list_active(self, account_id: str) -> list[Session]:
        rows = await self._session.scalars(
            select(Session)
            .where(
                Session.account_id == account_id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(UTC),
            )
            .order_by(Session.created_at.desc())
        )
        return list(rows)

    async def revoke(self, record: Session) -> None:
        record.revoked_at = datetime.now(UTC)

    async def revoke_all(self, account_id: str, *, except_id: str | None = None) -> int:
        stmt = (
            update(Session)
            .where(Session.account_id == account_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        if except_id:
            stmt = stmt.where(Session.id != except_id)
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def prune_oldest(self, account_id: str, keep: int) -> int:
        """Cap concurrent sessions so a stolen credential cannot accumulate
        an unbounded number of long-lived refresh tokens."""
        active = await self.list_active(account_id)
        surplus = active[keep:]
        for record in surplus:
            record.revoked_at = datetime.now(UTC)
        return len(surplus)
