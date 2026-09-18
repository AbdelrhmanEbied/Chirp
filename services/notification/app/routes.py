
from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from chirp_common.errors import NotFoundError
from app.dependencies import CurrentUser, Notifier
from app.schemas import NotificationResponse, UnreadCountResponse

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    user: CurrentUser,
    service: Notifier,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> list[NotificationResponse]:
    return await service.list_notifications(user.id, limit=limit, cursor=cursor)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(user: CurrentUser, service: Notifier) -> UnreadCountResponse:
    return await service.get_unread_count(user.id)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: str, user: CurrentUser, service: Notifier
) -> Response:
    await service.mark_read(user.id, notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUser, service: Notifier) -> Response:
    await service.mark_all_read(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
