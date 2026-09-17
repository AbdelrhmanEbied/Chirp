"""HTTP surface of the graph service.

Two routers, because they have different audiences and different exposure:
`/api/v1/graph/...` is reachable through the gateway, `/internal/v1/...` is
called only by sibling services and is not routed publicly.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Response, status

from app.dependencies import CurrentUser, Graph
from app.schemas import (
    BlockResponse,
    CheckBlocksRequest,
    CheckBlocksResponse,
    FollowResponse,
    MuteResponse,
)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])
internal_router = APIRouter(
    prefix="/internal/v1", tags=["internal"], include_in_schema=False
)


@router.post(
    "/{user_id}/follow",
    response_model=FollowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Follow a user",
)
async def follow_user(
    user_id: str, user: CurrentUser, service: Graph
) -> FollowResponse:
    return await service.follow(user.id, user_id)


@router.delete(
    "/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unfollow a user",
)
async def unfollow_user(
    user_id: str, user: CurrentUser, service: Graph
) -> Response:
    await service.unfollow(user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{user_id}/followers",
    response_model=list[FollowResponse],
    summary="List followers",
)
async def list_followers(
    user_id: str,
    service: Graph,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[FollowResponse]:
    return await service.list_followers(user_id, limit=limit, offset=offset)


@router.get(
    "/{user_id}/following",
    response_model=list[FollowResponse],
    summary="List following",
)
async def list_following(
    user_id: str,
    service: Graph,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[FollowResponse]:
    return await service.list_following(user_id, limit=limit, offset=offset)


@router.post(
    "/{user_id}/block",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Block a user",
)
async def block_user(
    user_id: str, user: CurrentUser, service: Graph
) -> BlockResponse:
    return await service.block(user.id, user_id)


@router.delete(
    "/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock a user",
)
async def unblock_user(
    user_id: str, user: CurrentUser, service: Graph
) -> Response:
    await service.unblock(user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{user_id}/mute",
    response_model=MuteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mute a user",
)
async def mute_user(
    user_id: str, user: CurrentUser, service: Graph
) -> MuteResponse:
    return await service.mute(user.id, user_id)


@router.delete(
    "/{user_id}/mute",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unmute a user",
)
async def unmute_user(
    user_id: str, user: CurrentUser, service: Graph
) -> Response:
    await service.unmute(user.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/blocks", response_model=list[BlockResponse], summary="List my blocks")
async def list_my_blocks(
    user: CurrentUser, service: Graph
) -> list[BlockResponse]:
    return await service.list_blocks(user.id)


@internal_router.post(
    "/graph/check-blocks",
    response_model=CheckBlocksResponse,
    summary="Batch block check",
)
async def check_blocks(
    payload: CheckBlocksRequest, service: Graph
) -> CheckBlocksResponse:
    # Internal endpoint: user_id comes from the request body, not auth.
    # This is called by other services to check if a set of users are blocked
    # by a specific user.
    return await service.check_blocks(
        payload.user_ids[0] if payload.user_ids else "", payload.user_ids
    )


@internal_router.get(
    "/graph/{user_id}/following",
    response_model=list[FollowResponse],
    summary="List following (internal)",
)
async def internal_list_following(
    user_id: str,
    service: Graph,
    limit: int = Query(default=500, ge=1, le=1000),
) -> list[FollowResponse]:
    return await service.list_following(user_id, limit=limit, offset=0)
