from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class UserSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "user-service"
    port: int = 8002

    profile_cache_ttl_seconds: int = 60
    username_change_cooldown_days: int = 30
    max_profile_batch: int = 100


@lru_cache(maxsize=1)
def get_settings() -> UserSettings:
    return UserSettings()
