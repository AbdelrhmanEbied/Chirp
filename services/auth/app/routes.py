"""HTTP surface of the auth service."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from chirp_common.errors import RateLimitedError
from chirp_common.ratelimit import RateLimitPolicy
from app.dependencies import Auth, Context, CurrentUser, client_ip
from app.schemas import (
    AccountResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SessionSummary,
    TokenPair,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _enforce_limit(
    context: Context, request: Request, scope: str, limit: int, window: int
) -> None:
    identity = client_ip(request) or "unknown"
    result = await context.rate_limiter.check(
        scope, identity, RateLimitPolicy(limit=limit, window_seconds=window)
    )
    if not result.allowed:
        raise RateLimitedError(retry_after_seconds=result.retry_after_seconds)


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
)
async def register(
    payload: RegisterRequest, request: Request, context: Context, service: Auth
) -> TokenPair:
    await _enforce_limit(
        context,
        request,
        "register",
        context.settings.register_rate_limit,
        context.settings.register_rate_window_seconds,
    )
    return await service.register(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
async def login(
    payload: LoginRequest, request: Request, context: Context, service: Auth
) -> TokenPair:
    await _enforce_limit(
        context,
        request,
        "login",
        context.settings.login_rate_limit,
        context.settings.login_rate_window_seconds,
    )
    return await service.login(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(payload: RefreshRequest, request: Request, service: Auth) -> TokenPair:
    return await service.refresh(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one refresh token",
)
async def logout(payload: RefreshRequest, service: Auth) -> Response:
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout-all",
    summary="Revoke every session except the current one",
)
async def logout_all(user: CurrentUser, service: Auth) -> dict[str, int]:
    revoked = await service.logout_everywhere(user.id, keep_session_id=user.session_id)
    return {"revoked_sessions": revoked}


@router.get("/me", response_model=AccountResponse, summary="Current account")
async def me(user: CurrentUser, service: Auth) -> AccountResponse:
    account = await service.get_account(user.id)
    return AccountResponse(
        id=account.id,
        email=account.email,
        is_admin=account.is_admin,
        created_at=account.created_at,
    )


@router.get(
    "/sessions",
    response_model=list[SessionSummary],
    summary="Active sessions for the current account",
)
async def sessions(user: CurrentUser, service: Auth) -> list[SessionSummary]:
    records = await service.list_sessions(user.id)
    return [
        SessionSummary(
            id=record.id,
            created_at=record.created_at,
            expires_at=record.expires_at,
            user_agent=record.user_agent,
            ip_address=record.ip_address,
            current=record.id == user.session_id,
        )
        for record in records
    ]


@router.post(
    "/password",
    summary="Change password and sign out every device",
)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, service: Auth
) -> dict[str, int]:
    revoked = await service.change_password(user.id, payload)
    return {"revoked_sessions": revoked}
