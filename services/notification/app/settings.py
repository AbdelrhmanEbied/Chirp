from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class NotificationSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "notification-service"
    port: int = 8007

    max_notifications_per_page: int = 100


@lru_cache(maxsize=1)
def get_settings() -> NotificationSettings:
    return NotificationSettings()
