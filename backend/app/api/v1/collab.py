from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.collab import (
    ArtifactList,
    CollabMessageList,
    CollabMessageOut,
    ExportIn,
    ExportResult,
    MessageIn,
    PostResult,
    RoomCreate,
    RoomList,
    RoomOut,
    RoomPatch,
    RunDetail,
    RunList,
    RunOut,
    SummarizeIn,
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


@router.get("/ai/collab/rooms/{room_id}/runs", response_model=RunList)
async def list_runs(
    room_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunList:
    return await _service(db, settings).list_runs(user.id, room_id)


@router.post(
    "/ai/collab/rooms/{room_id}/summarize",
    response_model=CollabMessageOut,
    status_code=201,
)
async def summarize(
    room_id: UUID,
    payload: SummarizeIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> CollabMessageOut:
    """Ask the room's Moderator (or a chosen member) to synthesize the
    discussion stored so far into a structured final summary."""
    return await _service(db, settings, http).summarize(user.id, room_id, payload)


@router.get("/ai/collab/runs/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunDetail:
    return await _service(db, settings).get_run(user.id, run_id)


@router.post("/ai/collab/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> RunOut:
    return await _service(db, settings).cancel_run(user.id, run_id)


@router.post("/ai/collab/runs/{run_id}/retry", response_model=RunDetail)
async def retry_run(
    run_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> RunDetail:
    """Re-run the failed Agent tasks of a run with fresh room context."""
    return await _service(db, settings, http).retry_run(user.id, run_id)


@router.post(
    "/ai/collab/rooms/{room_id}/export", response_model=ExportResult, status_code=201
)
async def export_room(
    room_id: UUID,
    payload: ExportIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
) -> ExportResult:
    """Build downloadable artifacts (report/transcript/results/ZIP)
    from the room's stored messages and runs."""
    return await _service(db, settings).export_room(user.id, room_id, payload)


@router.get("/ai/collab/rooms/{room_id}/artifacts", response_model=ArtifactList)
async def list_artifacts(
    room_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ArtifactList:
    return await _service(db, settings).list_artifacts(user.id, room_id)


@router.get("/ai/collab/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    data, name, mime_type = await _service(db, settings).download_artifact(
        user.id, artifact_id
    )
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.delete("/ai/collab/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
):
    await _service(db, settings).delete_artifact(user.id, artifact_id)
    return Response(status_code=204)
