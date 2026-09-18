
from __future__ import annotations

from fastapi import APIRouter, Response, UploadFile, status

from app.dependencies import CurrentUser, MediaSvc
from app.schemas import MediaResponse

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.post("", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    user: CurrentUser,
    service: MediaSvc,
    file: UploadFile,
) -> MediaResponse:
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    return await service.upload(
        owner_id=user.id,
        filename=file.filename or "upload",
        content_type=content_type,
        data=data,
    )


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(media_id: str, service: MediaSvc) -> MediaResponse:
    return await service.get(media_id)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: str,
    user: CurrentUser,
    service: MediaSvc,
) -> Response:
    await service.delete(user.id, media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
