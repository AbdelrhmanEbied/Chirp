from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class PostSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "post-service"
    port: int = 8003

    user_service_url: str = "http://user:8002"
    max_post_length: int = 500
    max_posts_per_page: int = 100


@lru_cache(maxsize=1)
def get_settings() -> PostSettings:
    return PostSettings()
