from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from chirp_common.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=20)
    display_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("username")
    @classmethod
    def _valid_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError("Username may contain only letters, numbers and underscores.")
        return value.lower()

    @field_validator("password")
    @classmethod
    def _not_trivial(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password may not start or end with whitespace.")
        if len(set(value)) < 5:
            raise ValueError("Password is too repetitive.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: str


class SessionSummary(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    current: bool = False


class AccountResponse(BaseModel):
    id: str
    email: EmailStr
    is_admin: bool
    created_at: datetime
