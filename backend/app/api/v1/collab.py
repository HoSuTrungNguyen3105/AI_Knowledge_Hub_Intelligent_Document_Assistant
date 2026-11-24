from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.collab import (
    CollabMessageList,
    MessageIn,
    PostResult,
    RoomCreate,
    RoomList,
    RoomOut,
    RoomPatch,
)
from app.services.ai.chat import ChatHTTP
from app.services.collab import CollabService

router = APIRouter(tags=["Collaboration"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _service(db, settings, http=None) -> CollabService:
    return CollabService(db, settings, http)


@router.get("/ai/collab/rooms", response_model=RoomList)
async def list_rooms(user: CurrentUser, db: Database, settings: AppSettings) -> RoomList:
    return await _service(db, settings).list_rooms(user.id)


@router.post("/ai/collab/rooms", response_model=RoomOut, status_code=201)
async def create_room(
    payload: RoomCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> RoomOut:
    return await _service(db, settings).create_room(user.id, payload)


@router.get("/ai/collab/rooms/{room_id}", response_model=RoomOut)
async def get_room(
    room_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RoomOut:
    return await _service(db, settings).get_room(user.id, room_id)


@router.patch("/ai/collab/rooms/{room_id}", response_model=RoomOut)
async def patch_room(
    room_id: UUID, payload: RoomPatch, user: CurrentUser, db: Database, settings: AppSettings
) -> RoomOut:
    return await _service(db, settings).patch_room(user.id, room_id, payload)


@router.delete("/ai/collab/rooms/{room_id}", status_code=204)
async def delete_room(room_id: UUID, user: CurrentUser, db: Database, settings: AppSettings):
    await _service(db, settings).delete_room(user.id, room_id)
    return Response(status_code=204)


@router.get("/ai/collab/rooms/{room_id}/messages", response_model=CollabMessageList)
async def list_messages(
    room_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> CollabMessageList:
    return CollabMessageList(messages=await _service(db, settings).list_messages(user.id, room_id))


@router.post("/ai/collab/rooms/{room_id}/messages", response_model=PostResult, status_code=201)
async def post_message(
    room_id: UUID,
    payload: MessageIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> PostResult:
    """Store the user's message, then run every mentioned member Agent
    with the room transcript as context and store their replies."""
    return await _service(db, settings, http).post_message(user.id, room_id, payload)
