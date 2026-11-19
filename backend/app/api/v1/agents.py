import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.agents import (
    AgentCreate,
    AgentDetail,
    AgentList,
    AgentPatch,
    ExecutionDetail,
    ExecutionList,
    RunRequest,
    ToolCatalog,
)
from app.services.agents import AgentService
from app.services.ai.chat import ChatHTTP

router = APIRouter(prefix="/ai/agents", tags=["AI agents"])


def agent_http() -> ChatHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ChatHTTP()


AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


def _stream(events: AsyncIterator[dict]) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async with aclosing(events):
            async for event in events:
                yield _sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# Static path must precede /{agent_id} so "tools" is not parsed as a UUID.
@router.get("/tools", response_model=ToolCatalog)
async def get_tool_catalog(user: CurrentUser) -> ToolCatalog:
    return AgentService.tool_catalog()


@router.get("", response_model=AgentList)
async def list_agents(user: CurrentUser, db: Database, settings: AppSettings) -> AgentList:
    return await AgentService(db, settings).list_agents(user.id)


@router.post("", response_model=AgentDetail, status_code=201)
async def create_agent(
    payload: AgentCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> AgentDetail:
    return await AgentService(db, settings).create_agent(user.id, payload)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> AgentDetail:
    return await AgentService(db, settings).get_agent(user.id, agent_id)


@router.patch("/{agent_id}", response_model=AgentDetail)
async def patch_agent(
    agent_id: UUID, payload: AgentPatch, user: CurrentUser, db: Database, settings: AppSettings
) -> AgentDetail:
    return await AgentService(db, settings).patch_agent(user.id, agent_id, payload)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await AgentService(db, settings).delete_agent(user.id, agent_id)
    return Response(status_code=204)


@router.post("/{agent_id}/duplicate", response_model=AgentDetail, status_code=201)
async def duplicate_agent(
    agent_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> AgentDetail:
    return await AgentService(db, settings).duplicate_agent(user.id, agent_id)


@router.get("/{agent_id}/executions", response_model=ExecutionList)
async def list_executions(
    agent_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ExecutionList:
    return await AgentService(db, settings).list_executions(user.id, agent_id)


@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: UUID,
    payload: RunRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> StreamingResponse:
    service = AgentService(db, settings, http)
    prepared = await service.prepare_run(user.id, agent_id, payload)
    return _stream(service.stream_prepared(prepared))


@router.get("/{agent_id}/executions/{execution_id}", response_model=ExecutionDetail)
async def get_execution(
    agent_id: UUID, execution_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ExecutionDetail:
    return await AgentService(db, settings).get_execution(user.id, agent_id, execution_id)


@router.delete("/{agent_id}/executions/{execution_id}", status_code=204)
async def delete_execution(
    agent_id: UUID, execution_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await AgentService(db, settings).delete_execution(user.id, agent_id, execution_id)
    return Response(status_code=204)