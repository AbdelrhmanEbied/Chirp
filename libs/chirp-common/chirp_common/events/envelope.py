from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field

from chirp_common import context
from chirp_common.ids import new_ulid

class EventType(StrEnum):

    USER_REGISTERED = "user.registered"
    USER_PROFILE_UPDATED = "user.profile_updated"
    USER_DELETED = "user.deleted"

    POST_CREATED = "post.created"
    POST_DELETED = "post.deleted"
    POST_LIKED = "post.liked"
    POST_UNLIKED = "post.unliked"
    POST_REPOSTED = "post.reposted"
    POST_UNREPOSTED = "post.unreposted"
    REPLY_CREATED = "post.reply_created"
    QUOTE_CREATED = "post.quote_created"
    USER_MENTIONED = "post.user_mentioned"
    HASHTAG_USED = "post.hashtag_used"

    USER_FOLLOWED = "graph.user_followed"
    USER_UNFOLLOWED = "graph.user_unfollowed"
    USER_BLOCKED = "graph.user_blocked"
    USER_UNBLOCKED = "graph.user_unblocked"

    MESSAGE_SENT = "messaging.message_sent"

    REPORT_CREATED = "moderation.report_created"
    CONTENT_ACTIONED = "moderation.content_actioned"

    MEDIA_UPLOADED = "media.uploaded"
    MEDIA_DELETED = "media.deleted"

class EventEnvelope(BaseModel):

    id: str = Field(default_factory=new_ulid)
    type: EventType
    version: int = 1
    producer: str
    subject_id: str = Field(description="Id of the aggregate the event is about.")
    actor_id: str | None = Field(
        default=None, description="User who caused the event, when there is one."
    )
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        type: EventType,
        producer: str,
        subject_id: str,
        payload: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> Self:
        return cls(
            type=type,
            producer=producer,
            subject_id=subject_id,
            actor_id=actor_id or context.get_actor_id(),
            payload=payload or {},
            correlation_id=context.get_correlation_id(),
            causation_id=context.get_request_id(),
        )

    def stream_name(self, prefix: str) -> str:
        return f"{prefix}.{self.type.value}"
