
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.errors import ConflictError, ForbiddenError, NotFoundError
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.ids import new_ulid
from app.models import Bookmark, Like, Post, Repost
from app.repository import BookmarkRepository, LikeRepository, PostRepository, RepostRepository
from app.schemas import CreatePostRequest, PostResponse, PostSummary
from app.settings import PostSettings

log = logging.getLogger(__name__)


class PostService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        posts: PostRepository,
        likes: LikeRepository,
        reposts: RepostRepository,
        bookmarks: BookmarkRepository,
        bus: EventBus,
        settings: PostSettings,
    ) -> None:
        self._db = db
        self._posts = posts
        self._likes = likes
        self._reposts = reposts
        self._bookmarks = bookmarks
        self._bus = bus
        self._settings = settings

    async def create_post(
        self, author_id: str, payload: CreatePostRequest
    ) -> PostResponse:
        post = Post(
            id=new_ulid(),
            author_id=author_id,
            text=payload.text,
            reply_to_id=payload.reply_to_id,
            quote_of_id=payload.quote_of_id,
            media_ids=json.dumps(payload.media_ids) if payload.media_ids else None,
        )
        await self._posts.add(post)

        if post.reply_to_id:
            await self._posts.adjust_counter(post.reply_to_id, "replies_count", 1)

        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.POST_CREATED,
                producer=self._settings.service_name,
                subject_id=post.id,
                actor_id=author_id,
                payload={
                    "author_id": author_id,
                    "text": post.text,
                    "reply_to_id": post.reply_to_id,
                    "hashtags": _extract_hashtags(post.text),
                    "mentions": _extract_mentions(post.text),
                },
            )
        )
        return _to_response(post)

    async def get_post(self, post_id: str) -> PostResponse:
        post = await self._posts.get(post_id)
        if post is None or post.is_deleted:
            raise NotFoundError("Post not found.")
        return _to_response(post)

    async def delete_post(self, user_id: str, post_id: str) -> None:
        post = await self._posts.get(post_id)
        if post is None or post.is_deleted:
            raise NotFoundError("Post not found.")
        if post.author_id != user_id:
            raise ForbiddenError("You can only delete your own posts.")

        await self._posts.delete(post)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.POST_DELETED,
                producer=self._settings.service_name,
                subject_id=post_id,
                actor_id=user_id,
                payload={"author_id": user_id},
            )
        )

    async def like_post(self, user_id: str, post_id: str) -> None:
        post = await self._posts.get(post_id)
        if post is None or post.is_deleted:
            raise NotFoundError("Post not found.")

        like = Like(user_id=user_id, post_id=post_id, post_author_id=post.author_id)
        added = await self._likes.add(like)
        if not added:
            raise ConflictError("Already liked.")

        await self._posts.adjust_counter(post_id, "likes_count", 1)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.POST_LIKED,
                producer=self._settings.service_name,
                subject_id=post_id,
                actor_id=user_id,
                payload={"author_id": post.author_id, "actor_id": user_id},
            )
        )

    async def unlike_post(self, user_id: str, post_id: str) -> None:
        post = await self._posts.get(post_id)
        removed = await self._likes.remove(user_id, post_id)
        if not removed:
            raise NotFoundError("Not liked.")
        await self._posts.adjust_counter(post_id, "likes_count", -1)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.POST_UNLIKED,
                producer=self._settings.service_name,
                subject_id=post_id,
                actor_id=user_id,
                payload={"author_id": post.author_id if post else "", "actor_id": user_id},
            )
        )

    async def repost(self, user_id: str, post_id: str) -> None:
        post = await self._posts.get(post_id)
        if post is None or post.is_deleted:
            raise NotFoundError("Post not found.")

        r = Repost(user_id=user_id, post_id=post_id, post_author_id=post.author_id)
        added = await self._reposts.add(r)
        if not added:
            raise ConflictError("Already reposted.")

        await self._posts.adjust_counter(post_id, "reposts_count", 1)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.POST_REPOSTED,
                producer=self._settings.service_name,
                subject_id=post_id,
                actor_id=user_id,
                payload={"author_id": post.author_id},
            )
        )

    async def unrepost(self, user_id: str, post_id: str) -> None:
        removed = await self._reposts.remove(user_id, post_id)
        if not removed:
            raise NotFoundError("Not reposted.")
        await self._posts.adjust_counter(post_id, "reposts_count", -1)

    async def bookmark(self, user_id: str, post_id: str) -> None:
        post = await self._posts.get(post_id)
        if post is None or post.is_deleted:
            raise NotFoundError("Post not found.")
        bm = Bookmark(user_id=user_id, post_id=post_id)
        added = await self._bookmarks.add(bm)
        if not added:
            raise ConflictError("Already bookmarked.")

    async def unbookmark(self, user_id: str, post_id: str) -> None:
        removed = await self._bookmarks.remove(user_id, post_id)
        if not removed:
            raise NotFoundError("Not bookmarked.")

    async def list_user_posts(self, user_id: str, limit: int = 20, before: str | None = None) -> list[PostSummary]:
        posts = await self._posts.list_by_author(user_id, limit=limit, before=before)
        return [_to_summary(p) for p in posts]

    async def list_replies(self, post_id: str, limit: int = 20) -> list[PostSummary]:
        posts = await self._posts.list_replies(post_id, limit=limit)
        return [_to_summary(p) for p in posts]


def _to_response(post: Post) -> PostResponse:
    media_ids = []
    if post.media_ids:
        try:
            media_ids = json.loads(post.media_ids)
        except (json.JSONDecodeError, TypeError):
            pass
    return PostResponse(
        id=post.id,
        author_id=post.author_id,
        text=post.text,
        reply_to_id=post.reply_to_id,
        quote_of_id=post.quote_of_id,
        media_ids=media_ids,
        likes_count=post.likes_count,
        reposts_count=post.reposts_count,
        replies_count=post.replies_count,
        quotes_count=post.quotes_count,
        created_at=post.created_at,
    )


def _to_summary(post: Post) -> PostSummary:
    return PostSummary(
        id=post.id,
        author_id=post.author_id,
        text=post.text,
        likes_count=post.likes_count,
        reposts_count=post.reposts_count,
        replies_count=post.replies_count,
        created_at=post.created_at,
    )


def _extract_hashtags(text: str) -> list[str]:
    import re
    return re.findall(r"#(\w+)", text)


def _extract_mentions(text: str) -> list[str]:
    import re
    return re.findall(r"@(\w+)", text)
