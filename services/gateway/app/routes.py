
from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status
from chirp_common.errors import RateLimitedError
from chirp_common.ratelimit import RateLimitPolicy
from app.dependencies import Context, CurrentUser, OptionalUser, client_ip

router = APIRouter(prefix="/api/v1", tags=["gateway"])


async def _enforce_rate_limit(context: Context, request: Request) -> None:
    if not context.settings.gateway_rate_limit_enabled:
        return
    ip = client_ip(request) or "unknown"
    result = await context.rate_limiter.check(
        "gateway",
        ip,
        RateLimitPolicy(
            limit=context.settings.gateway_rate_limit,
            window_seconds=context.settings.gateway_rate_window_seconds,
        ),
    )
    if not result.allowed:
        raise RateLimitedError(retry_after_seconds=result.retry_after_seconds)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()




@router.get("/feed", summary="Home feed with hydrated authors")
async def home_feed(
    request: Request,
    context: Context,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict:
    await _enforce_rate_limit(context, request)

    bearer = _bearer(request)

    timeline = await context.clients.timeline.request(
        "GET",
        "/internal/v1/timeline",
        params={"limit": str(limit), **({"before": before} if before else {})},
        bearer_token=bearer,
        retry=True,
    )

    post_ids = [item["post_id"] for item in (timeline or []) if "post_id" in item]
    author_ids = list({item.get("author_id") for item in (timeline or []) if item.get("author_id")})

    authors: dict[str, dict] = {}
    if author_ids:
        summaries = await context.clients.user.request(
            "POST",
            "/internal/v1/users/summaries",
            json={"user_ids": author_ids},
            bearer_token=bearer,
            retry=True,
        )
        authors = {a["id"]: a for a in (summaries or [])}

    posts: dict[str, dict] = {}
    if post_ids:
        post_results = await context.clients.post.request(
            "POST",
            "/internal/v1/posts/batch",
            json={"post_ids": post_ids},
            bearer_token=bearer,
            retry=True,
        )
        posts = {p["id"]: p for p in (post_results or [])}

    items = []
    for item in timeline or []:
        post_id = item.get("post_id")
        post = posts.get(post_id, {})
        author_id = post.get("author_id") or item.get("author_id")
        items.append({**item, **post, "author": authors.get(author_id, {})})

    return {"items": items, "next_cursor": (timeline or [{}])[-1].get("cursor") if timeline else None}


@router.get("/users/{username}/profile", summary="Public profile with recent posts")
async def user_profile(
    username: str,
    request: Request,
    context: Context,
    user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    await _enforce_rate_limit(context, request)

    bearer = _bearer(request)

    profile = await context.clients.user.request(
        "GET",
        f"/api/v1/users/{username}",
        bearer_token=bearer,
        retry=True,
    )

    user_id = profile.get("id", "")
    recent_posts = await context.clients.post.request(
        "GET",
        f"/api/v1/posts/by/{user_id}",
        params={"limit": str(limit)},
        bearer_token=bearer,
        retry=True,
    )

    return {"profile": profile, "recent_posts": recent_posts or []}




@router.post("/auth/register", status_code=status.HTTP_201_CREATED, summary="Proxy: create account")
async def register(request: Request, context: Context) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.auth.request(
        "POST", "/api/v1/auth/register", json=body, retry=False,
    )


@router.post("/auth/login", summary="Proxy: exchange credentials for tokens")
async def login(request: Request, context: Context) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.auth.request(
        "POST", "/api/v1/auth/login", json=body, retry=False,
    )


@router.post("/auth/refresh", summary="Proxy: rotate refresh token")
async def refresh(request: Request, context: Context) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.auth.request(
        "POST", "/api/v1/auth/refresh", json=body, retry=False,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: revoke refresh token",
)
async def logout(request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    await context.clients.auth.request(
        "POST", "/api/v1/auth/logout", json=body, bearer_token=_bearer(request), retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", summary="Proxy: current account")
async def auth_me(request: Request, context: Context, user: CurrentUser) -> dict:
    await _enforce_rate_limit(context, request)
    return await context.clients.auth.request(
        "GET", "/api/v1/auth/me", bearer_token=_bearer(request), retry=False,
    )




@router.post("/posts", status_code=status.HTTP_201_CREATED, summary="Proxy: create post")
async def create_post(request: Request, context: Context, user: CurrentUser) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.post.request(
        "POST", "/api/v1/posts", json=body, bearer_token=_bearer(request), retry=False,
    )


@router.get("/posts/{post_id}", summary="Proxy: get post")
async def get_post(post_id: str, request: Request, context: Context) -> dict:
    await _enforce_rate_limit(context, request)
    return await context.clients.post.request(
        "GET", f"/api/v1/posts/{post_id}", bearer_token=_bearer(request), retry=True,
    )


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: delete post",
)
async def delete_post(post_id: str, request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    await context.clients.post.request(
        "DELETE", f"/api/v1/posts/{post_id}", bearer_token=_bearer(request), retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/posts/{post_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: like post",
)
async def like_post(post_id: str, request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    await context.clients.post.request(
        "POST", f"/api/v1/posts/{post_id}/like", bearer_token=_bearer(request), retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/posts/{post_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: unlike post",
)
async def unlike_post(post_id: str, request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    await context.clients.post.request(
        "DELETE", f"/api/v1/posts/{post_id}/like", bearer_token=_bearer(request), retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)




@router.get("/users/me", summary="Proxy: own profile")
async def get_me(request: Request, context: Context, user: CurrentUser) -> dict:
    await _enforce_rate_limit(context, request)
    return await context.clients.user.request(
        "GET", "/api/v1/users/me", bearer_token=_bearer(request), retry=True,
    )


@router.patch("/users/me", summary="Proxy: update profile")
async def update_me(request: Request, context: Context, user: CurrentUser) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.user.request(
        "PATCH", "/api/v1/users/me", json=body, bearer_token=_bearer(request), retry=False,
    )


@router.get("/users/search", summary="Proxy: search users")
async def search_users(
    request: Request,
    context: Context,
    q: str = Query(min_length=1, max_length=20),
    limit: int = Query(default=10, ge=1, le=50),
) -> list:
    await _enforce_rate_limit(context, request)
    return await context.clients.user.request(
        "GET",
        "/api/v1/users/search",
        params={"q": q, "limit": str(limit)},
        bearer_token=_bearer(request),
        retry=True,
    )




@router.get("/search", summary="Proxy: search posts and users")
async def search(
    request: Request,
    context: Context,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    await _enforce_rate_limit(context, request)
    return await context.clients.search.request(
        "GET",
        "/api/v1/search",
        params={"q": q, "limit": str(limit)},
        bearer_token=_bearer(request),
        retry=True,
    )




@router.get("/notifications", summary="Proxy: list notifications")
async def list_notifications(
    request: Request,
    context: Context,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict:
    await _enforce_rate_limit(context, request)
    params: dict[str, str] = {"limit": str(limit)}
    if before:
        params["before"] = before
    return await context.clients.notification.request(
        "GET",
        "/api/v1/notifications",
        params=params,
        bearer_token=_bearer(request),
        retry=True,
    )


@router.post(
    "/notifications/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: mark notifications read",
)
async def mark_notifications_read(request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    await context.clients.notification.request(
        "POST",
        "/api/v1/notifications/read",
        json=body,
        bearer_token=_bearer(request),
        retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)




@router.post(
    "/users/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: follow user",
)
async def follow_user(user_id: str, request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    await context.clients.graph.request(
        "POST",
        f"/api/v1/users/{user_id}/follow",
        bearer_token=_bearer(request),
        retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/users/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Proxy: unfollow user",
)
async def unfollow_user(user_id: str, request: Request, context: Context, user: CurrentUser) -> Response:
    await _enforce_rate_limit(context, request)
    await context.clients.graph.request(
        "DELETE",
        f"/api/v1/users/{user_id}/follow",
        bearer_token=_bearer(request),
        retry=False,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/{user_id}/followers", summary="Proxy: list followers")
async def list_followers(
    user_id: str,
    request: Request,
    context: Context,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict:
    await _enforce_rate_limit(context, request)
    params: dict[str, str] = {"limit": str(limit)}
    if before:
        params["before"] = before
    return await context.clients.graph.request(
        "GET",
        f"/api/v1/users/{user_id}/followers",
        params=params,
        bearer_token=_bearer(request),
        retry=True,
    )


@router.get("/users/{user_id}/following", summary="Proxy: list following")
async def list_following(
    user_id: str,
    request: Request,
    context: Context,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> dict:
    await _enforce_rate_limit(context, request)
    params: dict[str, str] = {"limit": str(limit)}
    if before:
        params["before"] = before
    return await context.clients.graph.request(
        "GET",
        f"/api/v1/users/{user_id}/following",
        params=params,
        bearer_token=_bearer(request),
        retry=True,
    )




@router.get("/conversations", summary="Proxy: list conversations")
async def list_conversations(
    request: Request,
    context: Context,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list:
    await _enforce_rate_limit(context, request)
    return await context.clients.messaging.request(
        "GET",
        "/api/v1/conversations",
        params={"limit": str(limit)},
        bearer_token=_bearer(request),
        retry=True,
    )


@router.get("/conversations/{conversation_id}/messages", summary="Proxy: list messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    context: Context,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
) -> dict:
    await _enforce_rate_limit(context, request)
    params: dict[str, str] = {"limit": str(limit)}
    if before:
        params["before"] = before
    return await context.clients.messaging.request(
        "GET",
        f"/api/v1/conversations/{conversation_id}/messages",
        params=params,
        bearer_token=_bearer(request),
        retry=True,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Proxy: send message",
)
async def send_message(
    conversation_id: str,
    request: Request,
    context: Context,
    user: CurrentUser,
) -> dict:
    await _enforce_rate_limit(context, request)
    body = await request.json()
    return await context.clients.messaging.request(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages",
        json=body,
        bearer_token=_bearer(request),
        retry=False,
    )
