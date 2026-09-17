from __future__ import annotations

from functools import lru_cache

from chirp_common.config import DatabaseSettings, RedisSettings, ServiceSettings
from pydantic_settings import SettingsConfigDict


class MediaSettings(ServiceSettings, DatabaseSettings, RedisSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "media-service"
    port: int = 8009

    media_storage_backend: str = "local"
    media_local_path: str = "/tmp/chirp-media"
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


@lru_cache(maxsize=1)
def get_settings() -> MediaSettings:
    return MediaSettings()
