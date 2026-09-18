
from __future__ import annotations

import pytest
from httpx import AsyncClient

from chirp_common.events.envelope import EventEnvelope, EventType
from app.worker import CounterProjector
from tests.conftest import ADA_ID

BOB_ID = "01J0000000000000000000BOB0"


@pytest.fixture
def projector(context) -> CounterProjector:
    return CounterProjector(context)


def follow_event(follower: str, followee: str) -> EventEnvelope:
    return EventEnvelope(
        type=EventType.USER_FOLLOWED,
        producer="graph-service",
        subject_id=followee,
        actor_id=follower,
        payload={"follower_id": follower, "followee_id": followee},
    )


async def test_follow_event_increments_both_sides(
    client: AsyncClient, ada, projector
) -> None:
    await client.post(
        "/internal/v1/users",
        json={"user_id": BOB_ID, "username": "bob", "display_name": "Bob"},
    )

    await projector.on_followed(follow_event(BOB_ID, ADA_ID))

    assert (await client.get("/api/v1/users/ada")).json()["followers_count"] == 1
    assert (await client.get("/api/v1/users/bob")).json()["following_count"] == 1


async def test_duplicate_delivery_is_ignored(client: AsyncClient, ada, projector) -> None:
    event = follow_event(BOB_ID, ADA_ID)
    await projector.on_followed(event)
    await projector.on_followed(event)

    assert (await client.get("/api/v1/users/ada")).json()["followers_count"] == 1


async def test_unfollow_decrements_and_never_goes_negative(
    client: AsyncClient, ada, projector
) -> None:
    await projector.on_unfollowed(
        EventEnvelope(
            type=EventType.USER_UNFOLLOWED,
            producer="graph-service",
            subject_id=ADA_ID,
            payload={"follower_id": BOB_ID, "followee_id": ADA_ID},
        )
    )
    assert (await client.get("/api/v1/users/ada")).json()["followers_count"] == 0


async def test_post_events_move_the_post_count(
    client: AsyncClient, ada, projector
) -> None:
    await projector.on_post_created(
        EventEnvelope(
            type=EventType.POST_CREATED,
            producer="post-service",
            subject_id="01JPOST00000000000000000P1",
            actor_id=ADA_ID,
            payload={"author_id": ADA_ID},
        )
    )
    assert (await client.get("/api/v1/users/ada")).json()["posts_count"] == 1

    await projector.on_post_deleted(
        EventEnvelope(
            type=EventType.POST_DELETED,
            producer="post-service",
            subject_id="01JPOST00000000000000000P1",
            actor_id=ADA_ID,
            payload={"author_id": ADA_ID},
        )
    )
    assert (await client.get("/api/v1/users/ada")).json()["posts_count"] == 0
