"""Moderation domain logic."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.errors import NotFoundError
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.ids import new_ulid
from app.models import ModerationAction, Report
from app.repository import ActionRepository, ReportRepository
from app.schemas import (
    ModerationActionRequest,
    ModerationActionResponse,
    ReportListResponse,
    ReportRequest,
    ReportResponse,
)
from app.settings import ModerationSettings

log = logging.getLogger(__name__)


class ModerationService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        reports: ReportRepository,
        actions: ActionRepository,
        bus: EventBus,
        settings: ModerationSettings,
    ) -> None:
        self._db = db
        self._reports = reports
        self._actions = actions
        self._bus = bus
        self._settings = settings

    async def create_report(
        self,
        reporter_id: str,
        target_type: str,
        target_id: str,
        reason: str,
    ) -> ReportResponse:
        report = Report(
            id=new_ulid(),
            reporter_id=reporter_id,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
        )
        await self._reports.add(report)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.REPORT_CREATED,
                producer=self._settings.service_name,
                subject_id=report.id,
                actor_id=reporter_id,
                payload={
                    "report_id": report.id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "reason": reason,
                },
            )
        )
        log.info(
            "report created",
            extra={"report_id": report.id, "reporter_id": reporter_id},
        )
        return _report_to_response(report)

    async def list_reports(
        self,
        state: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> ReportListResponse:
        items = await self._reports.list_reports(
            state=state, limit=limit, cursor=cursor
        )
        has_next = len(items) > limit
        reports = [_report_to_response(r) for r in items[:limit]]
        next_cursor = reports[-1].id if has_next and reports else None
        return ReportListResponse(reports=reports, next_cursor=next_cursor)

    async def review_report(
        self,
        report_id: str,
        admin_id: str,
        resolution: str,
    ) -> ReportResponse:
        report = await self._reports.get(report_id)
        if report is None:
            raise NotFoundError("Report not found.")
        report.state = "reviewed"
        report.reviewed_by = admin_id
        report.reviewed_at = datetime.now(UTC)
        report.resolution = resolution
        log.info(
            "report reviewed",
            extra={"report_id": report_id, "admin_id": admin_id},
        )
        return _report_to_response(report)

    async def take_action(
        self,
        admin_id: str,
        action_type: str,
        target_type: str,
        target_id: str,
        reason: str,
    ) -> ModerationActionResponse:
        action = ModerationAction(
            id=new_ulid(),
            admin_id=admin_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
        )
        await self._actions.add(action)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.CONTENT_ACTIONED,
                producer=self._settings.service_name,
                subject_id=action.id,
                actor_id=admin_id,
                payload={
                    "action_id": action.id,
                    "action_type": action_type,
                    "target_type": target_type,
                    "target_id": target_id,
                    "reason": reason,
                },
            )
        )
        log.info(
            "moderation action taken",
            extra={"action_id": action.id, "admin_id": admin_id},
        )
        return _action_to_response(action)


def _report_to_response(r: Report) -> ReportResponse:
    return ReportResponse(
        id=r.id,
        reporter_id=r.reporter_id,
        target_type=r.target_type,
        target_id=r.target_id,
        reason=r.reason,
        state=r.state,
        reviewed_by=r.reviewed_by,
        reviewed_at=r.reviewed_at,
        resolution=r.resolution,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _action_to_response(a: ModerationAction) -> ModerationActionResponse:
    return ModerationActionResponse(
        id=a.id,
        admin_id=a.admin_id,
        action_type=a.action_type,
        target_type=a.target_type,
        target_id=a.target_id,
        reason=a.reason,
        created_at=a.created_at,
    )
