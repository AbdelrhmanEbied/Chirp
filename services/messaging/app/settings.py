from __future__ import annotations

from functools import lru_cache

from pydantic_settings import SettingsConfigDict

from chirp_common.config import (
    DatabaseSettings,
    EventBusSettings,
    RedisSettings,
    ServiceSettings,
)


class MessagingSettings(ServiceSettings, DatabaseSettings, RedisSettings, EventBusSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str = "messaging-service"
    port: int = 8008

    graph_service_url: str = "http://graph:8004"
    max_message_length: int = 5000
    max_messages_per_page: int = 100
    max_conversations_per_page: int = 50


@lru_cache(maxsize=1)
def get_settings() -> MessagingSettings:
    return MessagingSettings()
