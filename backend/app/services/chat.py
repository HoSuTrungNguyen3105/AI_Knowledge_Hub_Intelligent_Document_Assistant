import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models import Conversation, Message
from app.repositories.chat import ChatRepository
from app.repositories.providers import ProviderRepository
from app.schemas.chat import (
    DEFAULT_TITLE,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationPatch,
    ConversationSummary,
    MessageOut,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ERRORS, BaseProvider, ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.registry import get_provider


@dataclass
class PreparedChat:
    user_id: UUID
    conversation: Conversation
    adapter: BaseProvider
    api_key: SecretStr
    request: ChatRequest
    user_message: Message | None = None


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class ChatService:
    """Conversation CRUD plus streamed generation, owner-scoped end to end.

    Validation happens in prepare_* (before the SSE response starts) so config
    errors return proper HTTP status codes. Provider runtime errors surface as
    SSE error events because the stream has already begun.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        chat_http: ChatHTTP | None = None,
    ):
        self.repo = ChatRepository(db)
        self.providers = ProviderRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.chat_http = chat_http

    async def create_conversation(
        self, user_id: UUID, payload: ConversationCreate
    ) -> ConversationSummary:
        get_provider(payload.provider, require_implemented=True)
        credential = await self._require_credential(user_id, payload.provider)
        await self._require_model(credential, payload.model)
        conversation = await self.repo.create_conversation(
            user_id,
            title=payload.title or DEFAULT_TITLE,
            provider=payload.provider,
            model=payload.model,
            system_prompt=payload.system_prompt,
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
        )
        return self._summary(conversation)

    async def list_conversations(self, user_id: UUID) -> ConversationList:
        conversations = await self.repo.list_conversations(user_id)
        return ConversationList(conversations=[self._summary(c) for c in conversations])

    async def get_conversation(self, user_id: UUID, conversation_id: UUID) -> ConversationDetail:
        conversation = await self._require_conversation(user_id, conversation_id)
        messages = await self.repo.list_messages(user_id, conversation_id)
        return ConversationDetail(
            **self._summary(conversation).model_dump(),
            messages=[self._message(m) for m in messages],
        )

    async def patch_conversation(
        self, user_id: UUID, conversation_id: UUID, patch: ConversationPatch
    ) -> ConversationSummary:
        await self._require_conversation(user_id, conversation_id)
        values = {
            field: getattr(patch, field)
            for field in ("title", "system_prompt", "temperature", "max_output_tokens")
            if field in patch.model_fields_set
        }
        updated = await self.repo.update_conversation(user_id, conversation_id, values)
        if updated is None:
            raise ProviderError("conversation_not_found")
        return self._summary(updated)

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> None:
        if not await self.repo.delete_conversation(user_id, conversation_id):
            raise ProviderError("conversation_not_found")

    async def prepare_send(
        self, user_id: UUID, conversation_id: UUID, content: str
    ) -> PreparedChat:
        conversation = await self._require_conversation(user_id, conversation_id)
        credential = await self._require_credential(user_id, conversation.provider)
        model = await self._require_model(credential, conversation.model)
        self._check_chat_capability(model)
        user_message = await self.repo.add_message(
            user_id, conversation_id, role="user", content=content
        )
        if conversation.title == DEFAULT_TITLE:
            await self.repo.update_conversation(
                user_id, conversation_id, {"title": content[:60].strip() or DEFAULT_TITLE}
            )
        history = await self.repo.list_messages(user_id, conversation_id)
        return self._prepare(user_id, conversation, credential, self._turns(history), user_message)

    async def prepare_regenerate(self, user_id: UUID, conversation_id: UUID) -> PreparedChat:
        conversation = await self._require_conversation(user_id, conversation_id)
        credential = await self._require_credential(user_id, conversation.provider)
        model = await self._require_model(credential, conversation.model)
        self._check_chat_capability(model)
        messages = await self.repo.list_messages(user_id, conversation_id)
        last_user = max(
            (i for i, m in enumerate(messages) if m.role == "user"), default=None
        )
        if last_user is None:
            raise ProviderError("empty_message")
        # Drop the assistant replies being regenerated; keep history through last user turn.
        for message in messages[last_user + 1 :]:
            await self.repo.delete_message(user_id, message.id)
        kept = messages[: last_user + 1]
        if not any(m.role == "user" for m in kept):
            raise ProviderError("empty_message")
        return self._prepare(user_id, conversation, credential, self._turns(kept), None)

    def _prepare(
        self,
        user_id: UUID,
        conversation: Conversation,
        credential,
        turns: tuple[ChatTurn, ...],
        user_message: Message | None,
    ) -> PreparedChat:
        key = self.vault.decrypt(credential.encrypted_api_key, user_id, conversation.provider)
        adapter = create_provider(conversation.provider, chat_http=self.chat_http)
        request = ChatRequest(
            model=conversation.model,
            turns=turns,
            system_prompt=conversation.system_prompt,
            temperature=conversation.temperature,
            max_output_tokens=conversation.max_output_tokens,
        )
        return PreparedChat(user_id, conversation, adapter, key, request, user_message)

    async def stream_prepared(self, prepared: PreparedChat) -> AsyncIterator[dict]:
        user_id = prepared.user_id
        conversation = prepared.conversation
        if prepared.user_message is not None:
            yield {
                "event": "user_message",
                "data": {"message": self._message(prepared.user_message).model_dump(mode="json")},
            }
        started = time.monotonic()
        parts: list[str] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        status = "success"
        error_code: str | None = None
        try:
            async for event in prepared.adapter.stream_chat(prepared.api_key, prepared.request):
                if event.kind == "delta":
                    parts.append(event.text)
                    yield {"event": "delta", "data": {"text": event.text}}
                elif event.kind == "usage":
                    if event.input_tokens is not None:
                        input_tokens = event.input_tokens
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens
        except ProviderError as error:
            status, error_code = "error", error.code
        except asyncio.CancelledError:
            await self._persist_partial(
                user_id, conversation, parts, input_tokens, output_tokens, started
            )
            raise
        message = await self._persist_assistant(
            user_id,
            conversation,
            content="".join(parts),
            status=status,
            error_code=error_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=_elapsed_ms(started),
        )
        if status == "error":
            yield {
                "event": "error",
                "data": {"code": error_code, "message": ERRORS[error_code][1]},
            }
        else:
            yield {
                "event": "done",
                "data": {"message": self._message(message).model_dump(mode="json")},
            }

    async def _persist_partial(
        self, user_id, conversation, parts, input_tokens, output_tokens, started
    ) -> None:
        # Best-effort save of a stopped reply; shielded so it survives cancellation.
        task = asyncio.create_task(
            self._persist_assistant(
                user_id,
                conversation,
                content="".join(parts),
                status="stopped",
                error_code=None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=_elapsed_ms(started),
            )
        )
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass

    async def _persist_assistant(
        self,
        user_id: UUID,
        conversation: Conversation,
        *,
        content: str,
        status: str,
        error_code: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int,
    ) -> Message:
        message = await self.repo.add_message(
            user_id,
            conversation.id,
            role="assistant",
            content=content,
            status=status,
            model=conversation.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error_code=error_code,
        )
        await self.repo.record_request(
            user_id,
            provider=conversation.provider,
            model=conversation.model,
            status=status,
            conversation_id=conversation.id,
            message_id=message.id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        await self.repo.touch_conversation(user_id, conversation.id)
        return message

    async def _require_conversation(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = await self.repo.get_conversation(user_id, conversation_id)
        if conversation is None:
            raise ProviderError("conversation_not_found")
        return conversation

    async def _require_credential(self, user_id: UUID, provider: str):
        credential = await self.providers.get(user_id, provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        if not credential.enabled:
            raise ProviderError("provider_disabled")
        return credential

    async def _require_model(self, credential, model_id: str):
        model = await self.providers.get_model(credential.id, model_id)
        if model is None:
            raise ProviderError("model_not_synced")
        return model

    @staticmethod
    def _check_chat_capability(model) -> None:
        # Tri-state: only an explicit False blocks chat. Unknown (OpenAI/Groq) is
        # allowed and the provider's own response decides success.
        if model.capabilities.get("chat") is False:
            raise ProviderError("model_not_chat_capable")

    @staticmethod
    def _turns(messages: list[Message]) -> tuple[ChatTurn, ...]:
        turns = []
        for message in messages:
            if message.role == "user":
                turns.append(ChatTurn("user", message.content))
            elif (
                message.role == "assistant"
                and message.status in ("success", "stopped")
                and message.content
            ):
                turns.append(ChatTurn("assistant", message.content))
        return tuple(turns)

    @staticmethod
    def _summary(conversation: Conversation) -> ConversationSummary:
        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            provider=conversation.provider,
            model=conversation.model,
            system_prompt=conversation.system_prompt,
            temperature=conversation.temperature,
            max_output_tokens=conversation.max_output_tokens,
            multi_chat_id=conversation.multi_chat_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def _message(message: Message) -> MessageOut:
        return MessageOut(
            id=message.id,
            role=message.role,
            content=message.content,
            status=message.status,
            model=message.model,
            input_tokens=message.input_tokens,
            output_tokens=message.output_tokens,
            latency_ms=message.latency_ms,
            error_code=message.error_code,
            created_at=message.created_at,
        )