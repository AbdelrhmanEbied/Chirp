from __future__ import annotations

from functools import lru_cache

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)
from pydantic_settings import SettingsConfigDict


class SearchSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "search-service"
    port: int = 8006
    max_search_results: int = 50


@lru_cache(maxsize=1)
def get_settings() -> SearchSettings:
    return SearchSettings()
