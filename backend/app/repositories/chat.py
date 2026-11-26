from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import AIRequest, Conversation, Message
from app.models.base import utcnow
from app.services.rate_limits import persist_rate_limit_snapshot


class ChatRepository:
    """Every query is owner-scoped; conversation ownership is re-checked on write."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.conversations = db.conversations
        self.messages = db.messages
        self.ai_requests = db.ai_requests

    async def create_conversation(
        self,
        user_id: UUID,
        *,
        title: str,
        provider: str,
        model: str,
        system_prompt: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        multi_chat_id: UUID | None = None,
    ) -> Conversation:
        now = utcnow()
        doc = {
            "_id": Conversation.generate_id(),
            "user_id": user_id,
            "knowledge_base_id": None,
            "multi_chat_id": multi_chat_id,
            "title": title,
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "created_at": now,
            "updated_at": now,
        }
        await self.conversations.insert_one(doc)
        return Conversation(**doc)

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation | None:
        doc = await self.conversations.find_one({"_id": conversation_id, "user_id": user_id})
        return Conversation(**doc) if doc else None

    async def list_conversations(self, user_id: UUID, limit: int = 100) -> list[Conversation]:
        cursor = (
            self.conversations.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
        )
        return [Conversation(**doc) async for doc in cursor]

    async def update_conversation(
        self, user_id: UUID, conversation_id: UUID, values: dict
    ) -> Conversation | None:
        doc = await self.conversations.find_one_and_update(
            {"_id": conversation_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return Conversation(**doc) if doc else None

    async def touch_conversation(self, user_id: UUID, conversation_id: UUID) -> None:
        await self.conversations.update_one(
            {"_id": conversation_id, "user_id": user_id},
            {"$set": {"updated_at": utcnow()}},
        )

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> bool:
        result = await self.conversations.delete_one({"_id": conversation_id, "user_id": user_id})
        if not result.deleted_count:
            return False
        await self.messages.delete_many({"conversation_id": conversation_id, "user_id": user_id})
        return True

    async def add_message(
        self,
        user_id: UUID,
        conversation_id: UUID,
        *,
        role: str,
        content: str,
        status: str = "success",
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
    ) -> Message:
        doc = {
            "_id": Message.generate_id(),
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "status": status,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "error_code": error_code,
            "created_at": utcnow(),
        }
        await self.messages.insert_one(doc)
        return Message(**doc)

    async def list_messages(self, user_id: UUID, conversation_id: UUID) -> list[Message]:
        cursor = self.messages.find(
            {"conversation_id": conversation_id, "user_id": user_id}
        ).sort("created_at", 1)
        return [Message(**doc) async for doc in cursor]

    async def delete_message(self, user_id: UUID, message_id: UUID) -> bool:
        result = await self.messages.delete_one({"_id": message_id, "user_id": user_id})
        return bool(result.deleted_count)

    async def record_request(
        self,
        user_id: UUID,
        *,
        provider: str,
        model: str,
        status: str,
        conversation_id: UUID | None = None,
        message_id: UUID | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        await self.ai_requests.insert_one(
            {
                "_id": AIRequest.generate_id(),
                "user_id": user_id,
                "provider": provider,
                "model": model,
                "status": status,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
                "created_at": utcnow(),
            }
        )
        await persist_rate_limit_snapshot(self.db, user_id, provider, model)