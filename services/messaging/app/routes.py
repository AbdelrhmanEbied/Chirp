
from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.dependencies import CurrentUser, Messaging
from app.schemas import (
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    SendMessageRequest,
)

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])
internal_router = APIRouter(prefix="/internal/v1", tags=["internal"], include_in_schema=False)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: CreateConversationRequest,
    user: CurrentUser,
    service: Messaging,
) -> ConversationResponse:
    all_participants = list({user.id, *payload.participant_ids})
    return await service.create_conversation(all_participants)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    user: CurrentUser,
    service: Messaging,
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ConversationResponse]:
    return await service.list_conversations(user.id, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    user: CurrentUser,
    service: Messaging,
) -> ConversationResponse:
    conversations = await service.list_conversations(user.id, limit=100)
    for conv in conversations:
        if conv.id == conversation_id:
            return conv
    from chirp_common.errors import NotFoundError
    raise NotFoundError("Conversation not found.")


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: str,
    payload: SendMessageRequest,
    user: CurrentUser,
    service: Messaging,
) -> MessageResponse:
    return await service.send_message(conversation_id, user.id, payload.text)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    user: CurrentUser,
    service: Messaging,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> list[MessageResponse]:
    return await service.list_messages(conversation_id, user.id, limit=limit, cursor=cursor)


@router.post(
    "/conversations/{conversation_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_read(
    conversation_id: str,
    user: CurrentUser,
    service: Messaging,
) -> Response:
    await service.mark_read(conversation_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
