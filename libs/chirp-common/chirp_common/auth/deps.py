"""FastAPI authentication dependencies.

`build_auth_dependencies` returns a (required, optional) pair bound to one
codec, so services do not reach for a module-level singleton and tests can
build dependencies over a throwaway secret.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Request

from chirp_common import context
from chirp_common.auth.jwt import JWTCodec
from chirp_common.errors import ForbiddenError, UnauthorizedError


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: str
    session_id: str
    scopes: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes

    def require_admin(self) -> None:
        if not self.is_admin:
            raise ForbiddenError("Administrator access is required.")


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def build_auth_dependencies(
    codec: JWTCodec,
) -> tuple[Callable[[Request], AuthenticatedUser], Callable[[Request], AuthenticatedUser | None]]:
    def optional_user(request: Request) -> AuthenticatedUser | None:
        token = _extract_bearer(request)
        if token is None:
            return None
        claims = codec.decode_access_token(token)
        user = AuthenticatedUser(
            id=claims.user_id, session_id=claims.session_id, scopes=claims.scopes
        )
        context.set_actor_id(user.id)
        return user

    def required_user(request: Request) -> AuthenticatedUser:
        user = optional_user(request)
        if user is None:
            raise UnauthorizedError("A bearer access token is required.")
        return user

    return required_user, optional_user


# Type aliases services use after calling `app.dependency_overrides`-free
# wiring in their own `dependencies.py`.
CurrentUser = Annotated[AuthenticatedUser, Depends]
OptionalUser = Annotated[AuthenticatedUser | None, Depends]
