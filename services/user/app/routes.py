"""HTTP surface of the user service.

Two routers, because they have different audiences and different exposure:
`/api/v1/users/...` is reachable through the gateway, `/internal/v1/...` is
called only by sibling services and is not routed publicly.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Response, status

from app.dependencies import CurrentUser, Users
from app.schemas import (
    ChangeUsernameRequest,
    CreateProfileRequest,
    ProfileResponse,
    ProfileSummary,
    SetAvatarRequest,
    UpdateProfileRequest,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])
internal_router = APIRouter(prefix="/internal/v1", tags=["internal"], include_in_schema=False)


@internal_router.post(
    "/users", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED
)
async def create_profile(payload: CreateProfileRequest, service: Users) -> ProfileResponse:
    """Called by the auth service during registration. Idempotent on user_id."""
    return await service.create_profile(payload)


@internal_router.post("/users/summaries", response_model=list[ProfileSummary])
async def summaries(
    service: Users, user_ids: list[str] = Body(embed=True)
) -> list[ProfileSummary]:
    """Batch author hydration for timelines, notifications and search."""
    return await service.get_summaries(user_ids)


@router.get("/me", response_model=ProfileResponse, summary="Own profile")
async def get_me(user: CurrentUser, service: Users) -> ProfileResponse:
    return await service.get_by_id(user.id)


@router.patch("/me", response_model=ProfileResponse, summary="Edit profile fields")
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, service: Users
) -> ProfileResponse:
    return await service.update_profile(user.id, payload)


@router.put("/me/username", response_model=ProfileResponse, summary="Change username")
async def change_username(
    payload: ChangeUsernameRequest, user: CurrentUser, service: Users
) -> ProfileResponse:
    return await service.change_username(user.id, payload)


@router.put("/me/media", response_model=ProfileResponse, summary="Set avatar or banner")
async def set_media(
    payload: SetAvatarRequest, user: CurrentUser, service: Users
) -> ProfileResponse:
    return await service.set_media(user.id, payload)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, summary="Deactivate account")
async def delete_me(user: CurrentUser, service: Users) -> Response:
    await service.soft_delete(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search", response_model=list[ProfileSummary], summary="Prefix user lookup")
async def search(
    service: Users,
    q: str = Query(min_length=1, max_length=20),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[ProfileSummary]:
    return await service.search(q, limit)


@router.get("/{username}", response_model=ProfileResponse, summary="Public profile")
async def get_profile(username: str, service: Users) -> ProfileResponse:
    return await service.get_by_username(username)
