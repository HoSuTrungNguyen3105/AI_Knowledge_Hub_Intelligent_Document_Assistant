"""Workflow Studio routes (Phase 4): catalog + graph conversion.

Mounted under /api/v1/ai/workflow-studio. Saving a Studio workflow goes
through the existing n8n Platform create endpoint — the Studio only
converts and validates; n8n stays the execution engine.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.workflow_studio import (
    StudioCatalogOut,
    StudioConvertOut,
    StudioGraphIn,
    StudioGraphOut,
    StudioParseIn,
)
from app.services.workflow_studio import convert_graph, get_catalog, parse_workflow

router = APIRouter(prefix="/ai/workflow-studio", tags=["Workflow Studio"])


@router.get("/catalog", response_model=StudioCatalogOut)
async def studio_catalog(user: CurrentUser) -> StudioCatalogOut:
    return get_catalog()


@router.post("/convert", response_model=StudioConvertOut)
async def studio_convert(user: CurrentUser, payload: StudioGraphIn) -> StudioConvertOut:
    return convert_graph(payload)


@router.post("/parse", response_model=StudioGraphOut)
async def studio_parse(user: CurrentUser, payload: StudioParseIn) -> StudioGraphOut:
    return parse_workflow(payload.workflow_json)
