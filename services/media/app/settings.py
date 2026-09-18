from __future__ import annotations

from functools import lru_cache

from chirp_common.config import DatabaseSettings, RedisSettings, ServiceSettings
from pydantic_settings import SettingsConfigDict


class MediaSettings(ServiceSettings, DatabaseSettings, RedisSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "media-service"
    port: int = 8009

    media_storage_backend: str = "local"
    media_local_path: str = "/srv/uploads"
    media_max_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    media_allowed_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "application/pdf",
    ]
    media_max_width: int = 8192
    media_max_height: int = 8192

    media_base_url: str = "http://localhost:8009"

    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None  # For S3-compatible services (MinIO, etc.)
    s3_prefix: str = "media/"


@lru_cache(maxsize=1)
def get_settings() -> MediaSettings:
    return MediaSettings()
