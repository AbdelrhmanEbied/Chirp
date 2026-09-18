
from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from chirp_common.errors import NotFoundError
from app.dependencies import CurrentUser, Posts
from app.schemas import CreatePostRequest, PostResponse, PostSummary

router = APIRouter(prefix="/api/v1/posts", tags=["posts"])
internal_router = APIRouter(prefix="/internal/v1", tags=["internal"], include_in_schema=False)


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(payload: CreatePostRequest, user: CurrentUser, service: Posts) -> PostResponse:
    return await service.create_post(user.id, payload)


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str, service: Posts) -> PostResponse:
    return await service.get_post(post_id)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.delete_post(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def like_post(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.like_post(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_post(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.unlike_post(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/repost", status_code=status.HTTP_204_NO_CONTENT)
async def repost(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.repost(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{post_id}/repost", status_code=status.HTTP_204_NO_CONTENT)
async def unrepost(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.unrepost(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def bookmark(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.bookmark(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{post_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def unbookmark(post_id: str, user: CurrentUser, service: Posts) -> Response:
    await service.unbookmark(user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/by/{author_id}", response_model=list[PostSummary])
async def list_user_posts(
    author_id: str,
    service: Posts,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> list[PostSummary]:
    return await service.list_user_posts(author_id, limit=limit, before=before)


@router.get("/{post_id}/replies", response_model=list[PostSummary])
async def list_replies(
    post_id: str,
    service: Posts,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[PostSummary]:
    return await service.list_replies(post_id, limit=limit)


@internal_router.get("/posts/{post_id}", response_model=PostResponse)
async def internal_get_post(post_id: str, service: Posts) -> PostResponse:
    return await service.get_post(post_id)


@internal_router.get("/posts/by/{author_id}", response_model=list[PostSummary])
async def internal_list_user_posts(
    author_id: str,
    service: Posts,
    limit: int = Query(default=20, ge=1, le=100),
    before: str | None = Query(default=None),
) -> list[PostSummary]:
    return await service.list_user_posts(author_id, limit=limit, before=before)
