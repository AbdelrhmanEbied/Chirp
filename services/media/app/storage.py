
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from app.settings import MediaSettings

log = logging.getLogger(__name__)


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


class S3MediaStorage:
    def __init__(self, settings: MediaSettings) -> None:
        import boto3

        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix
        self._base_url = settings.media_base_url
        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        import asyncio

        s3_key = f"{self._prefix}{key}"
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
        )
        log.info("s3 put", extra={"s3_key": s3_key, "size": len(data)})

    async def delete(self, key: str) -> None:
        import asyncio

        s3_key = f"{self._prefix}{key}"
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=s3_key,
        )
        log.info("s3 delete", extra={"s3_key": s3_key})

    def url_for(self, key: str) -> str:
        if self._base_url:
            return f"{self._base_url}/{self._prefix}{key}"
        return f"https://{self._bucket}.s3.amazonaws.com/{self._prefix}{key}"
