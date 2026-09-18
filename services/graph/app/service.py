
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.errors import ConflictError, NotFoundError
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from app.models import Block, Follow
from app.repository import BlockRepository, FollowRepository, MuteRepository
from app.schemas import (
    BlockResponse,
    CheckBlocksResponse,
    FollowResponse,
    MuteResponse,
)
from app.settings import GraphSettings

log = logging.getLogger(__name__)


class GraphService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        follows: FollowRepository,
        blocks: BlockRepository,
        mutes: MuteRepository,
        bus: EventBus,
        settings: GraphSettings,
    ) -> None:
        self._db = db
        self._follows = follows
        self._blocks = blocks
        self._mutes = mutes
        self._bus = bus
        self._settings = settings


    async def follow(self, follower_id: str, followee_id: str) -> FollowResponse:
        if follower_id == followee_id:
            raise ConflictError("You cannot follow yourself.")

        existing = await self._follows.get(follower_id, followee_id)
        if existing is not None:
            raise ConflictError("Already following this user.", code="duplicate_follow")

        follow = await self._follows.add(follower_id, followee_id)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_FOLLOWED,
                producer=self._settings.service_name,
                subject_id=followee_id,
                actor_id=follower_id,
                payload={"follower_id": follower_id, "followee_id": followee_id},
            )
        )
        log.info(
            "user followed",
            extra={"follower_id": follower_id, "followee_id": followee_id},
        )
        return _follow_to_response(follow)

    async def unfollow(self, follower_id: str, followee_id: str) -> None:
        existing = await self._follows.get(follower_id, followee_id)
        if existing is None:
            raise NotFoundError("Follow relationship does not exist.")

        await self._follows.remove(follower_id, followee_id)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_UNFOLLOWED,
                producer=self._settings.service_name,
                subject_id=followee_id,
                actor_id=follower_id,
                payload={"follower_id": follower_id, "followee_id": followee_id},
            )
        )
        log.info(
            "user unfollowed",
            extra={"follower_id": follower_id, "followee_id": followee_id},
        )

    async def list_followers(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[FollowResponse]:
        follows = await self._follows.list_followers(user_id, limit=limit, offset=offset)
        return [_follow_to_response(f) for f in follows]

    async def list_following(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[FollowResponse]:
        follows = await self._follows.list_following(user_id, limit=limit, offset=offset)
        return [_follow_to_response(f) for f in follows]

    async def is_following(self, follower_id: str, followee_id: str) -> bool:
        return await self._follows.is_following(follower_id, followee_id)


    async def block(self, blocker_id: str, blocked_id: str) -> BlockResponse:
        if blocker_id == blocked_id:
            raise ConflictError("You cannot block yourself.", code="self_block")

        if await self._blocks.is_blocked(blocker_id, blocked_id):
            rows = await self._db.scalars(
                select(Block).where(
                    Block.blocker_id == blocker_id,
                    Block.blocked_id == blocked_id,
                )
            )
            existing = rows.one()
            return BlockResponse(
                blocker_id=existing.blocker_id,
                blocked_id=existing.blocked_id,
                created_at=existing.created_at,
            )

        block = await self._blocks.add(blocker_id, blocked_id)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_BLOCKED,
                producer=self._settings.service_name,
                subject_id=blocked_id,
                actor_id=blocker_id,
                payload={"blocker_id": blocker_id, "blocked_id": blocked_id},
            )
        )
        log.info(
            "user blocked",
            extra={"blocker_id": blocker_id, "blocked_id": blocked_id},
        )
        return BlockResponse(
            blocker_id=block.blocker_id,
            blocked_id=block.blocked_id,
            created_at=block.created_at,
        )

    async def unblock(self, blocker_id: str, blocked_id: str) -> None:
        existing = await self._blocks.is_blocked(blocker_id, blocked_id)
        if not existing:
            raise NotFoundError("Block relationship does not exist.")

        await self._blocks.remove(blocker_id, blocked_id)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_UNBLOCKED,
                producer=self._settings.service_name,
                subject_id=blocked_id,
                actor_id=blocker_id,
                payload={"blocker_id": blocker_id, "blocked_id": blocked_id},
            )
        )
        log.info(
            "user unblocked",
            extra={"blocker_id": blocker_id, "blocked_id": blocked_id},
        )

    async def is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        return await self._blocks.is_blocked(blocker_id, blocked_id)

    async def check_blocks(
        self, user_id: str, other_ids: list[str]
    ) -> CheckBlocksResponse:
        capped = other_ids[: self._settings.max_follow_batch]
        blocked_ids = await self._blocks.get_blocks_between(user_id, capped)
        return CheckBlocksResponse(blocked_ids=blocked_ids)

    async def list_blocks(self, user_id: str) -> list[BlockResponse]:
        rows = await self._db.scalars(
            select(Block)
            .where(Block.blocker_id == user_id)
            .order_by(Block.created_at.desc())
        )
        return [
            BlockResponse(
                blocker_id=b.blocker_id,
                blocked_id=b.blocked_id,
                created_at=b.created_at,
            )
            for b in rows
        ]


    async def mute(self, user_id: str, muted_id: str) -> MuteResponse:
        if user_id == muted_id:
            raise ConflictError("You cannot mute yourself.", code="self_mute")

        existing = await self._mutes.add(user_id, muted_id)
        return MuteResponse(
            user_id=existing.user_id,
            muted_id=existing.muted_id,
            created_at=existing.created_at,
        )

    async def unmute(self, user_id: str, muted_id: str) -> None:
        await self._mutes.remove(user_id, muted_id)


def _follow_to_response(follow: Follow) -> FollowResponse:
    return FollowResponse(
        follower_id=follow.follower_id,
        followee_id=follow.followee_id,
        created_at=follow.created_at,
    )
