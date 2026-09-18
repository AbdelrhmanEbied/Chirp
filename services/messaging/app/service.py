
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from chirp_common.errors import ConflictError, ForbiddenError, NotFoundError
from chirp_common.events.bus import EventBus
from chirp_common.events.envelope import EventEnvelope, EventType
from chirp_common.http.client import ServiceClient
from chirp_common.ids import new_ulid
from app.models import Conversation, ConversationParticipant, Message
from app.repository import ConversationRepository, MessageRepository
from app.schemas import ConversationResponse, MessageResponse, SendMessageRequest
from app.settings import MessagingSettings

log = logging.getLogger(__name__)


class MessagingService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        conversations: ConversationRepository,
        messages: MessageRepository,
        bus: EventBus,
        settings: MessagingSettings,
        graph_client: ServiceClient,
    ) -> None:
        self._db = db
        self._conversations = conversations
        self._messages = messages
        self._bus = bus
        self._settings = settings
        self._graph = graph_client

    async def _check_blocked(self, user_id: str, target_id: str) -> None:
        try:
            data = await self._graph.get(
                f"/internal/v1/graph/blocks",
                params={"user_a": user_id, "user_b": target_id},
            )
            if data and data.get("blocked"):
                raise ForbiddenError("Cannot message this user.")
        except ForbiddenError:
            raise
        except Exception:
            log.warning("Failed to check block status, proceeding anyway")

    async def create_conversation(self, participant_ids: list[str]) -> ConversationResponse:
        now = datetime.now(UTC)

        conversation = Conversation(
            id=new_ulid(),
            title=None,
            created_at_index=now,
        )
        await self._conversations.add(conversation)

        for uid in participant_ids:
            participant = ConversationParticipant(
                conversation_id=conversation.id,
                user_id=uid,
                last_read_at=None,
                joined_at=now,
            )
            await self._conversations.add_participant(participant)

        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            participant_ids=participant_ids,
            created_at=conversation.created_at,
        )

    async def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        text: str,
    ) -> MessageResponse:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")

        if not await self._conversations.is_participant(conversation_id, sender_id):
            raise ForbiddenError("You are not a participant in this conversation.")

        participants = await self._conversations.get_participants(conversation_id)
        other_ids = [p.user_id for p in participants if p.user_id != sender_id]
        for other_id in other_ids:
            await self._check_blocked(sender_id, other_id)

        message = Message(
            id=new_ulid(),
            conversation_id=conversation_id,
            sender_id=sender_id,
            text=text,
        )
        await self._messages.add(message)

        for participant in participants:
            if participant.user_id != sender_id:
                await self._conversations.update_last_read_at(
                    conversation_id, participant.user_id, datetime.fromtimestamp(0, UTC)
                )

        await self._bus.publish(
            EventEnvelope.create(
                type=EventType.MESSAGE_SENT,
                producer=self._settings.service_name,
                subject_id=message.id,
                actor_id=sender_id,
                payload={
                    "conversation_id": conversation_id,
                    "sender_id": sender_id,
                    "text": text,
                },
            )
        )

        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            text=message.text,
            created_at=message.created_at,
        )

    async def list_conversations(
        self, user_id: str, limit: int = 20
    ) -> list[ConversationResponse]:
        conversations = await self._conversations.list_for_user(user_id, limit=limit)
        result: list[ConversationResponse] = []
        for conv in conversations:
            participants = await self._conversations.get_participants(conv.id)
            last_msg = await self._messages.get_last_message(conv.id)
            unread = await self._messages.count_unread(conv.id, user_id)
            result.append(
                ConversationResponse(
                    id=conv.id,
                    title=conv.title,
                    participant_ids=[p.user_id for p in participants],
                    last_message_text=last_msg.text if last_msg else None,
                    last_message_sender_id=last_msg.sender_id if last_msg else None,
                    last_message_at=last_msg.created_at if last_msg else None,
                    unread_count=unread,
                    created_at=conv.created_at,
                )
            )
        return result

    async def list_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[MessageResponse]:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")

        if not await self._conversations.is_participant(conversation_id, user_id):
            raise ForbiddenError("You are not a participant in this conversation.")

        messages = await self._messages.list_for_conversation(
            conversation_id, limit=limit, before=cursor
        )
        return [
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                sender_id=m.sender_id,
                text=m.text,
                created_at=m.created_at,
            )
            for m in reversed(messages)
        ]

    async def mark_read(self, conversation_id: str, user_id: str) -> None:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")

        if not await self._conversations.is_participant(conversation_id, user_id):
            raise ForbiddenError("You are not a participant in this conversation.")

        await self._conversations.update_last_read(conversation_id, user_id)

    async def get_unread_count(self, user_id: str) -> int:
        return await self._messages.count_unread_for_user(user_id)
