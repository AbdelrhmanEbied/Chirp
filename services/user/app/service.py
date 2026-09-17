"""User service domain logic."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.cache import Cache
from chirp_common.errors import ConflictError, ForbiddenError, NotFoundError
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.timeutil import ensure_utc, utcnow
from app.models import UserProfile
from app.repository import ProfileRepository
from app.schemas import (
    ChangeUsernameRequest,
    CreateProfileRequest,
    ProfileResponse,
    ProfileSummary,
    SetAvatarRequest,
    UpdateProfileRequest,
)
from app.settings import UserSettings

log = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        profiles: ProfileRepository,
        cache: Cache,
        bus: EventBus,
        settings: UserSettings,
    ) -> None:
        self._db = db
        self._profiles = profiles
        self._cache = cache
        self._bus = bus
        self._settings = settings

    # ---------------------------------------------------------------- create

    async def create_profile(self, payload: CreateProfileRequest) -> ProfileResponse:
        """Idempotent on `user_id`.

        The auth service may retry this call after a timeout, so a second call
        with the same id must return the existing profile rather than a 409.
        A different id claiming a taken username is still a conflict.
        """
        existing = await self._profiles.get(payload.user_id)
        if existing is not None:
            return _to_response(existing)

        if await self._profiles.username_taken(payload.username):
            raise ConflictError("That username is taken.", code="username_taken")

        profile = UserProfile(
            id=payload.user_id,
            username=payload.username,
            display_name=payload.display_name,
        )
        try:
            await self._profiles.add(profile)
        except IntegrityError as exc:
            # Two concurrent registrations raced for the same username; the
            # unique index is the arbiter, not the check above.
            raise ConflictError("That username is taken.", code="username_taken") from exc

        log.info(
            "profile created",
            extra={"user_id": profile.id, "username": profile.username},
        )
        return _to_response(profile)

    # ------------------------------------------------------------------ read

    async def get_by_username(self, username: str) -> ProfileResponse:
        cached = await self._cache.get(f"username:{username.lower()}")
        if cached is not None:
            return ProfileResponse.model_validate(cached)

        profile = await self._profiles.get_by_username(username)
        if profile is None:
            raise NotFoundError("No such user.")

        response = _to_response(profile)
        await self._cache.set(
            f"username:{profile.username}",
            response.model_dump(mode="json"),
            self._settings.profile_cache_ttl_seconds,
        )
        return response

    async def get_by_id(self, user_id: str) -> ProfileResponse:
        profile = await self._profiles.get(user_id)
        if profile is None or profile.deleted_at is not None:
            raise NotFoundError("No such user.")
        return _to_response(profile)

    async def get_summaries(self, user_ids: list[str]) -> list[ProfileSummary]:
        capped = user_ids[: self._settings.max_profile_batch]
        profiles = await self._profiles.get_many(capped)
        return [
            ProfileSummary(
                id=p.id,
                username=p.username,
                display_name=p.display_name,
                avatar_media_id=p.avatar_media_id,
            )
            for p in profiles
        ]

    async def search(self, query: str, limit: int) -> list[ProfileSummary]:
        profiles = await self._profiles.search(query, limit)
        return [
            ProfileSummary(
                id=p.id,
                username=p.username,
                display_name=p.display_name,
                avatar_media_id=p.avatar_media_id,
            )
            for p in profiles
        ]

    # ---------------------------------------------------------------- update

    async def update_profile(
        self, user_id: str, payload: UpdateProfileRequest
    ) -> ProfileResponse:
        profile = await self._require_own(user_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(profile, field, value)

        await self._invalidate(profile.username)
        await self._publish_profile_updated(profile, list(changes))
        return _to_response(profile)

    async def change_username(
        self, user_id: str, payload: ChangeUsernameRequest
    ) -> ProfileResponse:
        profile = await self._require_own(user_id)
        if profile.username == payload.username:
            return _to_response(profile)

        cooldown = timedelta(days=self._settings.username_change_cooldown_days)
        if profile.username_changed_at is not None:
            elapsed = utcnow() - ensure_utc(profile.username_changed_at)
            if elapsed < cooldown:
                remaining = (cooldown - elapsed).days + 1
                raise ForbiddenError(
                    f"You can change your username again in {remaining} days.",
                    code="username_cooldown",
                )

        if await self._profiles.username_taken(payload.username):
            raise ConflictError("That username is taken.", code="username_taken")

        previous = profile.username
        await self._profiles.record_username_release(profile.id, previous)
        profile.username = payload.username
        profile.username_changed_at = utcnow()

        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise ConflictError("That username is taken.", code="username_taken") from exc

        await self._invalidate(previous, payload.username)
        await self._publish_profile_updated(profile, ["username"])
        log.info(
            "username changed",
            extra={"user_id": profile.id, "from": previous, "to": profile.username},
        )
        return _to_response(profile)

    async def set_media(self, user_id: str, payload: SetAvatarRequest) -> ProfileResponse:
        profile = await self._require_own(user_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(profile, field, value)
        await self._invalidate(profile.username)
        await self._publish_profile_updated(profile, list(changes))
        return _to_response(profile)

    async def soft_delete(self, user_id: str) -> None:
        profile = await self._require_own(user_id)
        profile.deleted_at = utcnow()
        await self._invalidate(profile.username)
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_DELETED,
                producer=self._settings.service_name,
                subject_id=profile.id,
                actor_id=profile.id,
            )
        )

    # ------------------------------------------------------- event consumers

    async def apply_counter_delta(self, user_id: str, field: str, delta: int) -> None:
        await self._profiles.adjust_counter(user_id, field, delta)
        profile = await self._profiles.get(user_id)
        if profile is not None:
            await self._invalidate(profile.username)

    # --------------------------------------------------------------- helpers

    async def _require_own(self, user_id: str) -> UserProfile:
        profile = await self._profiles.get(user_id)
        if profile is None or profile.deleted_at is not None:
            raise NotFoundError("No such user.")
        return profile

    async def _invalidate(self, *usernames: str) -> None:
        # Invalidate rather than overwrite: a failed delete costs one stale TTL
        # window, a failed write could leave a wrong value cached indefinitely.
        await self._cache.delete(*[f"username:{u.lower()}" for u in usernames])

    async def _publish_profile_updated(
        self, profile: UserProfile, fields: list[str]
    ) -> None:
        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.USER_PROFILE_UPDATED,
                producer=self._settings.service_name,
                subject_id=profile.id,
                actor_id=profile.id,
                payload={
                    "username": profile.username,
                    "display_name": profile.display_name,
                    "avatar_media_id": profile.avatar_media_id,
                    "changed_fields": fields,
                },
            )
        )


def _to_response(profile: UserProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        username=profile.username,
        display_name=profile.display_name,
        bio=profile.bio,
        location=profile.location,
        website=profile.website,
        avatar_media_id=profile.avatar_media_id,
        banner_media_id=profile.banner_media_id,
        followers_count=profile.followers_count,
        following_count=profile.following_count,
        posts_count=profile.posts_count,
        created_at=profile.created_at,
    )
