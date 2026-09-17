"""Per-request ambient context.

`request_id` identifies a single inbound HTTP request or a single consumed
event. `correlation_id` identifies a whole user-initiated operation as it
crosses service and event boundaries: it is generated at the edge (gateway)
and propagated through HTTP headers and event envelopes.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_actor_id: ContextVar[str | None] = ContextVar("actor_id", default=None)

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_ID_HEADER = "x-correlation-id"
ACTOR_ID_HEADER = "x-actor-id"


def new_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return _request_id.get()


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def get_actor_id() -> str | None:
    return _actor_id.get()


def log_fields() -> dict[str, Any]:
    """Context fields that every log line should carry, when present."""
    fields: dict[str, Any] = {}
    if rid := _request_id.get():
        fields["request_id"] = rid
    if cid := _correlation_id.get():
        fields["correlation_id"] = cid
    if aid := _actor_id.get():
        fields["actor_id"] = aid
    return fields


@dataclass(slots=True)
class _Tokens:
    request: Token[str | None]
    correlation: Token[str | None]
    actor: Token[str | None]


class bind_context:
    """Context manager that binds ids for the duration of a block.

    Used by HTTP middleware and by the event worker so that consumed events
    log with the same correlation id as the request that produced them.
    """

    def __init__(
        self,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        self._request_id = request_id or new_id()
        self._correlation_id = correlation_id or self._request_id
        self._actor_id = actor_id
        self._tokens: _Tokens | None = None

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    def __enter__(self) -> bind_context:
        self._tokens = _Tokens(
            request=_request_id.set(self._request_id),
            correlation=_correlation_id.set(self._correlation_id),
            actor=_actor_id.set(self._actor_id),
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._tokens is not None:
            _request_id.reset(self._tokens.request)
            _correlation_id.reset(self._tokens.correlation)
            _actor_id.reset(self._tokens.actor)
            self._tokens = None


def set_actor_id(actor_id: str | None) -> None:
    """Set the authenticated actor once auth middleware has resolved it."""
    _actor_id.set(actor_id)
