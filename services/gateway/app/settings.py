from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import RedisSettings, ServiceSettings


class GatewaySettings(ServiceSettings, RedisSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "gateway"
    port: int = 8000

    auth_service_url: str = "http://auth:8001"
    user_service_url: str = "http://user:8002"
    post_service_url: str = "http://post:8003"
    graph_service_url: str = "http://graph:8004"
    timeline_service_url: str = "http://timeline:8005"
    search_service_url: str = "http://search:8006"
    notification_service_url: str = "http://notification:8007"
    messaging_service_url: str = "http://messaging:8008"
    media_service_url: str = "http://media:8009"
    moderation_service_url: str = "http://moderation:8010"

    gateway_rate_limit: int = 120
    gateway_rate_window_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings()
