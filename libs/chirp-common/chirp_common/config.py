from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]

class ServiceSettings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "chirp-service"
    environment: Environment = "local"
    log_level: str = "INFO"
    log_json: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    jwt_secret: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "chirp.auth"
    jwt_audience: str = "chirp.api"
    access_token_ttl_seconds: int = 900

    http_timeout_seconds: float = 3.0
    http_connect_timeout_seconds: float = 1.0
    http_max_retries: int = 2

    request_max_bytes: int = 2 * 1024 * 1024
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    metrics_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")

class DatabaseSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: float = 5.0
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False
    db_statement_timeout_ms: int = 5000
    db_application_name: str = "chirp"

class RedisSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 1.0
    cache_enabled: bool = True
    cache_default_ttl_seconds: int = 60

class EventBusSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    event_bus_backend: Literal["redis", "memory"] = "redis"
    event_bus_url: str = "redis://localhost:6379/1"
    event_stream_prefix: str = "chirp.events"
    event_max_delivery_attempts: int = 5
    event_retry_base_delay_seconds: float = 0.5
    event_retry_max_delay_seconds: float = 30.0
    event_claim_idle_ms: int = 60_000
    event_batch_size: int = 32
    event_block_ms: int = 5_000
    event_max_stream_length: int = 100_000

def cached_settings[T: BaseSettings](factory: type[T]):

    @lru_cache(maxsize=1)
    def _load() -> T:
        return factory()

    return _load
