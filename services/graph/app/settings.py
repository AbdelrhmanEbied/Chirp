from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class GraphSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "graph-service"
    port: int = 8004

    max_follow_batch: int = 100


@lru_cache(maxsize=1)
def get_settings() -> GraphSettings:
    return GraphSettings()
