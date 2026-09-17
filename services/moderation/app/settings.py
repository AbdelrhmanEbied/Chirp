from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class ModerationSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "moderation-service"
    port: int = 8010

    max_reports_per_page: int = 100


@lru_cache(maxsize=1)
def get_settings() -> ModerationSettings:
    return ModerationSettings()
