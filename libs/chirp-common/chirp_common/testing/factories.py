from __future__ import annotations

from typing import Any

from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.ids import new_ulid

TEST_JWT_SECRET = "test-secret-value-not-for-production"


def make_settings_env(**overrides: str) -> dict[str, str]:
    """Environment for constructing settings objects inside tests."""
    env = {
        "SERVICE_NAME": "test-service",
        "ENVIRONMENT": "test",
        "JWT_SECRET": TEST_JWT_SECRET,
        "EVENT_BUS_BACKEND": "memory",
        "CACHE_ENABLED": "false",
        "LOG_JSON": "false",
    }
    env.update(overrides)
    return env


def make_event(
    event_type: EventType,
    *,
    subject_id: str | None = None,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
    producer: str = "test",
) -> EventEnvelope:
    return EventEnvelope(
        type=event_type,
        producer=producer,
        subject_id=subject_id or new_ulid(),
        actor_id=actor_id,
        payload=payload or {},
    )
