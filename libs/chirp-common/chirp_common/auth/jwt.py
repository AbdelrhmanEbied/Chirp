"""Access token encoding and verification.

Only the auth service mints tokens. Every other service verifies them locally
with the same shared secret, which keeps the hot path free of a network call
to auth on every request.

Tradeoff, recorded in docs/decisions.md: a shared HS256 secret means any
service holding it could mint tokens. The production-grade version is RS256
with auth publishing a JWKS endpoint and services caching public keys. The
seam for that change is this file only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from chirp_common.errors import UnauthorizedError
from chirp_common.ids import new_ulid

TOKEN_TYPE_ACCESS = "access"


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: str
    session_id: str
    issued_at: datetime
    expires_at: datetime
    token_id: str
    scopes: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes


class JWTCodec:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str = "HS256",
        issuer: str = "chirp.auth",
        audience: str = "chirp.api",
        access_ttl_seconds: int = 900,
        leeway_seconds: int = 10,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._access_ttl = timedelta(seconds=access_ttl_seconds)
        self._leeway = leeway_seconds

    def issue_access_token(
        self,
        *,
        user_id: str,
        session_id: str,
        scopes: tuple[str, ...] = (),
    ) -> tuple[str, AccessTokenClaims]:
        now = datetime.now(UTC)
        expires_at = now + self._access_ttl
        token_id = new_ulid()
        payload: dict[str, Any] = {
            "sub": user_id,
            "sid": session_id,
            "jti": token_id,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "typ": TOKEN_TYPE_ACCESS,
            "scopes": list(scopes),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        claims = AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            issued_at=now,
            expires_at=expires_at,
            token_id=token_id,
            scopes=scopes,
        )
        return token, claims

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except ExpiredSignatureError as exc:
            raise UnauthorizedError(
                "Access token has expired.", code="token_expired"
            ) from exc
        except InvalidTokenError as exc:
            raise UnauthorizedError(
                "Access token is invalid.", code="token_invalid"
            ) from exc

        if payload.get("typ") != TOKEN_TYPE_ACCESS:
            raise UnauthorizedError(
                "Wrong token type for this endpoint.", code="token_invalid"
            )

        return AccessTokenClaims(
            user_id=str(payload["sub"]),
            session_id=str(payload.get("sid", "")),
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            token_id=str(payload.get("jti", "")),
            scopes=tuple(payload.get("scopes") or ()),
        )
