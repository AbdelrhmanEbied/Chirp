
from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.dependencies import AdminUser, CurrentUser, Moderation
from app.schemas import (
    ModerationActionRequest,
    ModerationActionResponse,
    ReportListResponse,
    ReportRequest,
    ReportResponse,
    ReviewReportRequest,
)

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


@router.post(
    "/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a report",
)
async def create_report(
    payload: ReportRequest,
    user: CurrentUser,
    service: Moderation,
) -> ReportResponse:
    return await service.create_report(
        reporter_id=user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
    )


@router.get(
    "/reports",
    response_model=ReportListResponse,
    summary="List reports (admin only)",
)
async def list_reports(
    admin: AdminUser,
    service: Moderation,
    state: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ReportListResponse:
    return await service.list_reports(state=state, limit=limit, cursor=cursor)


@router.post(
    "/reports/{report_id}/review",
    response_model=ReportResponse,
    summary="Review a report (admin only)",
)
async def review_report(
    report_id: str,
    payload: ReviewReportRequest,
    admin: AdminUser,
    service: Moderation,
) -> ReportResponse:
    return await service.review_report(
        report_id=report_id,
        admin_id=admin.id,
        resolution=payload.resolution,
    )


@router.post(
    "/actions",
    response_model=ModerationActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Take a moderation action (admin only)",
)
async def take_action(
    payload: ModerationActionRequest,
    admin: AdminUser,
    service: Moderation,
) -> ModerationActionResponse:
    return await service.take_action(
        admin_id=admin.id,
        action_type=payload.action_type,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
    )
