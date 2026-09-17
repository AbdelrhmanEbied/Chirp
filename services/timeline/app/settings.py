from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class TimelineSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "timeline-service"
    port: int = 8005
    user_service_url: str = "http://user:8002"
    post_service_url: str = "http://post:8003"
    graph_service_url: str = "http://graph:8004"
    max_feed_size: int = 100


@lru_cache(maxsize=1)
def get_settings() -> TimelineSettings:
    return TimelineSettings()
