import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.compare import (
    ComparisonCreate,
    ComparisonDetail,
    ComparisonList,
    SynthesizeRequest,
)
from app.services.ai.chat import ChatHTTP
from app.services.compare import CompareService

router = APIRouter(prefix="/ai/compare", tags=["AI compare"])


def compare_http() -> ChatHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return ChatHTTP()


CompareHTTPDep = Annotated[ChatHTTP, Depends(compare_http)]


def _sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"


def _stream(events: AsyncIterator[dict]) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async for event in events:
            yield _sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/comparisons", response_model=ComparisonList)
async def list_comparisons(
    user: CurrentUser, db: Database, settings: AppSettings
) -> ComparisonList:
    return await CompareService(db, settings).list_comparisons(user.id)


@router.post("/comparisons", response_model=ComparisonDetail, status_code=201)
async def create_comparison(
    payload: ComparisonCreate, user: CurrentUser, db: Database, settings: AppSettings
) -> ComparisonDetail:
    return await CompareService(db, settings).create_comparison(user.id, payload)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonDetail)
async def get_comparison(
    comparison_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> ComparisonDetail:
    return await CompareService(db, settings).get_comparison(user.id, comparison_id)


@router.delete("/comparisons/{comparison_id}", status_code=204)
async def delete_comparison(
    comparison_id: UUID, user: CurrentUser, db: Database, settings: AppSettings
) -> Response:
    await CompareService(db, settings).delete_comparison(user.id, comparison_id)
    return Response(status_code=204)


@router.post("/comparisons/{comparison_id}/execute")
async def execute_comparison(
    comparison_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: CompareHTTPDep,
) -> StreamingResponse:
    service = CompareService(db, settings, http)
    prepared = await service.prepare_execute(user.id, comparison_id)
    return _stream(service.stream_prepared(prepared))


@router.post("/comparisons/{comparison_id}/synthesize")
async def synthesize_comparison(
    comparison_id: UUID,
    payload: SynthesizeRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: CompareHTTPDep,
) -> StreamingResponse:
    service = CompareService(db, settings, http)
    prepared = await service.prepare_synthesize(user.id, comparison_id, payload)
    return _stream(service.stream_synthesis(prepared))