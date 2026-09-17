from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class AuthSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "auth-service"
    port: int = 8001

    user_service_url: str = "http://user:8002"

    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30
    max_active_sessions_per_user: int = 10

    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    register_rate_limit: int = 5
    register_rate_window_seconds: int = 3600


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    return AuthSettings()
