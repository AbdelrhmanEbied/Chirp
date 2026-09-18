
from __future__ import annotations

import logging

from chirp_common.errors import ForbiddenError, NotFoundError, ValidationError
from chirp_common.ids import new_ulid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media
from app.repository import MediaRepository
from app.schemas import MediaResponse
from app.settings import MediaSettings
from app.storage import MediaStorage

log = logging.getLogger(__name__)

_MAGIC_BYTES: dict[bytes, str] = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "video/webm",
    b"%PDF": "application/pdf",
}

_RIFF_OFFSET = 8
_WEBP_SUFFIX = b"WEBP"


class MediaService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        media: MediaRepository,
        storage: MediaStorage,
        settings: MediaSettings,
    ) -> None:
        self._db = db
        self._media = media
        self._storage = storage
        self._settings = settings

    async def upload(
        self,
        owner_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> MediaResponse:
        detected = self._sniff_content_type(data, filename)
        if detected is None:
            raise ValidationError("Could not determine file type from content.")
        content_type = detected

        if len(data) > self._settings.media_max_size_bytes:
            max_mb = self._settings.media_max_size_bytes // (1024 * 1024)
            raise ValidationError(f"File exceeds maximum size of {max_mb} MB.")

        if content_type not in self._settings.media_allowed_types:
            raise ValidationError(f"Content type '{content_type}' is not allowed.")

        media_id = new_ulid()
        ext = self._ext_for(content_type, filename)
        storage_key = f"{media_id}{ext}"

        width, height = self._extract_dimensions(content_type, data)

        await self._storage.put(storage_key, data, content_type)

        m = Media(
            id=media_id,
            owner_id=owner_id,
            content_type=content_type,
            file_size=len(data),
            storage_key=storage_key,
            state="ready",
            width=width,
            height=height,
        )
        await self._media.add(m)
        await self._db.commit()
        log.info("media uploaded", extra={"media_id": media_id, "owner_id": owner_id})
        return self._to_response(m)

    async def get(self, media_id: str) -> MediaResponse:
        m = await self._media.get(media_id)
        if m is None:
            raise NotFoundError("Media not found.")
        return self._to_response(m)

    async def delete(self, owner_id: str, media_id: str) -> None:
        m = await self._media.get(media_id)
        if m is None:
            raise NotFoundError("Media not found.")
        if m.owner_id != owner_id:
            raise ForbiddenError("You do not own this media.")
        await self._storage.delete(m.storage_key)
        await self._media.delete(m)
        await self._db.commit()
        log.info("media deleted", extra={"media_id": media_id})

    async def get_url(self, media_id: str) -> str:
        m = await self._media.get(media_id)
        if m is None:
            raise NotFoundError("Media not found.")
        return self._storage.url_for(m.storage_key)

    @staticmethod
    def _sniff_content_type(data: bytes, filename: str) -> str | None:
        for magic, ct in _MAGIC_BYTES.items():
            if data[: len(magic)] == magic:
                if ct == "video/webm" and len(data) > 12:
                    if data[_RIFF_OFFSET : _RIFF_OFFSET + 4] != _WEBP_SUFFIX:
                        return "video/webm"
                return ct
        if (
            data[:4] == b"RIFF"
            and len(data) > 12
            and data[_RIFF_OFFSET : _RIFF_OFFSET + 4] == _WEBP_SUFFIX
        ):
            return "image/webp"
        if "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            ext_map = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "gif": "image/gif",
                "webp": "image/webp",
                "mp4": "video/mp4",
                "webm": "video/webm",
                "pdf": "application/pdf",
            }
            return ext_map.get(ext)
        return None

    @staticmethod
    def _ext_for(content_type: str, filename: str) -> str:
        if "." in filename:
            return "." + filename.rsplit(".", 1)[-1]
        ct_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "application/pdf": ".pdf",
        }
        return ct_map.get(content_type, ".bin")

    def _extract_dimensions(
        self, content_type: str, data: bytes
    ) -> tuple[int | None, int | None]:
        if content_type == "image/png" and len(data) > 24:
            try:
                import struct

                w = struct.unpack(">I", data[16:20])[0]
                h = struct.unpack(">I", data[20:24])[0]
                if (
                    w <= self._settings.media_max_width
                    and h <= self._settings.media_max_height
                ):
                    return w, h
                raise ValidationError(
                    f"Image dimensions {w}x{h} exceed maximum "
                    f"{self._settings.media_max_width}x{self._settings.media_max_height}."
                )
            except (struct.error, IndexError):
                pass
        return None, None

    @staticmethod
    def _to_response(m: Media) -> MediaResponse:
        return MediaResponse(
            id=m.id,
            owner_id=m.owner_id,
            content_type=m.content_type,
            file_size=m.file_size,
            url=f"/files/{m.storage_key}",
            state=m.state,
            width=m.width,
            height=m.height,
            created_at=m.created_at,
        )
