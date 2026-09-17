"""Pluggable storage backend for media files."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.settings import MediaSettings


class MediaStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    def url_for(self, key: str) -> str: ...


class LocalMediaStorage:
    def __init__(self, settings: MediaSettings) -> None:
        self._base = Path(settings.media_local_path)
        self._base.mkdir(parents=True, exist_ok=True)
        self._base_url = settings.media_base_url

    async def put(self, key: str, data: bytes, content_type: str) -> None:  # noqa: ARG002
        dest = self._base / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    async def delete(self, key: str) -> None:
        path = self._base / key
        path.unlink(missing_ok=True)

    def url_for(self, key: str) -> str:
        return f"{self._base_url}/files/{key}"
