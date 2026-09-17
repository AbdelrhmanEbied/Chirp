from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModerationAction, Report


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, report: Report) -> Report:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get(self, report_id: str) -> Report | None:
        return await self._session.get(Report, report_id)

    async def list_reports(
        self,
        state: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> list[Report]:
        stmt = select(Report).order_by(Report.created_at.desc())
        if state is not None:
            stmt = stmt.where(Report.state == state)
        if cursor is not None:
            stmt = stmt.where(Report.id < cursor)
        stmt = stmt.limit(limit + 1)
        rows = await self._session.scalars(stmt)
        return list(rows)


class ActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, action: ModerationAction) -> ModerationAction:
        self._session.add(action)
        await self._session.flush()
        return action

    async def list_for_target(
        self, target_type: str, target_id: str
    ) -> list[ModerationAction]:
        stmt = (
            select(ModerationAction)
            .where(
                ModerationAction.target_type == target_type,
                ModerationAction.target_id == target_id,
            )
            .order_by(ModerationAction.created_at.desc())
        )
        rows = await self._session.scalars(stmt)
        return list(rows)
