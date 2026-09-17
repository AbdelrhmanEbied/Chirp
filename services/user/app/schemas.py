from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")

# Handles the platform reserves for itself, so that nobody can register
# /admin or /settings and shadow a real route or impersonate the service.
RESERVED_USERNAMES = frozenset(
    {
        "admin", "administrator", "api", "chirp", "explore", "help", "home",
        "login", "logout", "messages", "notifications", "root", "search",
        "settings", "signup", "support", "system", "about", "terms", "privacy",
    }
)


def normalise_username(value: str) -> str:
    candidate = value.strip().lower()
    if not USERNAME_PATTERN.match(candidate):
        raise ValueError("Username may contain only letters, numbers and underscores.")
    if candidate in RESERVED_USERNAMES:
        raise ValueError("That username is reserved.")
    return candidate


class CreateProfileRequest(BaseModel):
    """Internal: called by the auth service during registration."""

    user_id: str = Field(min_length=26, max_length=26)
    username: str
    display_name: str = Field(min_length=1, max_length=50)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return normalise_username(value)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    bio: str | None = Field(default=None, max_length=280)
    location: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=200)

    @field_validator("website")
    @classmethod
    def _safe_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("Website must start with http:// or https://")
        return value


class ChangeUsernameRequest(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return normalise_username(value)


class SetAvatarRequest(BaseModel):
    avatar_media_id: str | None = Field(default=None, min_length=26, max_length=26)
    banner_media_id: str | None = Field(default=None, min_length=26, max_length=26)


class ProfileResponse(BaseModel):
    id: str
    username: str
    display_name: str
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    avatar_media_id: str | None = None
    banner_media_id: str | None = None
    followers_count: int = 0
    following_count: int = 0
    posts_count: int = 0
    created_at: datetime


class ProfileSummary(BaseModel):
    """The shape other services embed when they hydrate an author."""

    id: str
    username: str
    display_name: str
    avatar_media_id: str | None = None
