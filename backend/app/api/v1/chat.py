import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.chat import (
    ChatSendRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationPatch,
    ConversationSummary,
)
from app.services.ai.chat import ChatHTTP
from app.services.chat import ChatService, PreparedChat

router = APIRouter(prefix="/ai/chat", tags=["AI chat"])


def chat_http() -> ChatHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ChatHTTP()


ChatHTTPDep = Annotated[ChatHTTP, Depends(chat_http)]


def _sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


def _stream(service: ChatService, prepared: PreparedChat) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async for event in service.stream_prepared(prepared):
            yield _sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    user: CurrentUser, db: Database, settings: AppSettings
) -> ConversationList:
    return await ChatService(db, settings).list_conversations(user.id)


@router.post("/conversations", response_model=ConversationSummary, status_code=201)
async def create_conversation(
    payload: ConversationCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> ConversationSummary:
    return await ChatService(db, settings).create_conversation(user.id, payload)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ConversationDetail:
    return await ChatService(db, settings).get_conversation(user.id, conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def patch_conversation(
    conversation_id: UUID,
    payload: ConversationPatch,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ConversationSummary:
    return await ChatService(db, settings).patch_conversation(user.id, conversation_id, payload)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await ChatService(db, settings).delete_conversation(user.id, conversation_id)
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    payload: ChatSendRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: ChatHTTPDep,
) -> StreamingResponse:
    service = ChatService(db, settings, http)
    prepared = await service.prepare_send(user.id, conversation_id, payload.content)
    return _stream(service, prepared)


@router.post("/conversations/{conversation_id}/regenerate")
async def regenerate(
    conversation_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: ChatHTTPDep,
) -> StreamingResponse:
    service = ChatService(db, settings, http)
    prepared = await service.prepare_regenerate(user.id, conversation_id)
    return _stream(service, prepared)