from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.seed import (
    SeedApplyOut,
    SeedApplyRequest,
    SeedRemoveOut,
    SeedStatusOut,
    WorkforceSeedOut,
    WorkforceSeedRemoveOut,
)
from app.services.ai.chat import ChatHTTP
from app.services.seed import SeedService
from app.services.workforce_seed import WorkforceSeedService

router = APIRouter(tags=["NEXORA seed"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


def _service(db, settings, http) -> SeedService:
    return SeedService(db, settings, http)


@router.get("/ai/seed/demo", response_model=SeedStatusOut)
async def seed_status(
    user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
) -> SeedStatusOut:
    """Whether demo seeding is allowed here, and what demo data the
    caller currently has. Safe to call in any environment."""
    return await _service(db, settings, http).status(user.id)


@router.post("/ai/seed/demo", response_model=SeedApplyOut)
async def seed_apply(
    payload: SeedApplyRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> SeedApplyOut:
    """Create the caller's demo agents + teams (idempotent). Refused in
    production and when no provider with a synced model is configured."""
    return await _service(db, settings, http).apply(user.id, payload)


@router.delete("/ai/seed/demo", response_model=SeedRemoveOut)
async def seed_remove(
    user: CurrentUser, db: Database, settings: AppSettings, http: AgentHTTPDep
) -> SeedRemoveOut:
    """Remove only the caller's demo records. Real agents/teams — and demo
    agents a real team still uses — are never touched."""
    return await _service(db, settings, http).remove(user.id)


@router.post("/ai/seed/workforce", response_model=WorkforceSeedOut)
async def seed_workforce_apply(
    user: CurrentUser, db: Database, settings: AppSettings
) -> WorkforceSeedOut:
    """Create the 50 demo employees in the caller's workforce resources
    (idempotent by name). Refused in production, like the demo seed."""
    return await WorkforceSeedService(db, settings).apply(user.id)


@router.delete("/ai/seed/workforce", response_model=WorkforceSeedRemoveOut)
async def seed_workforce_remove(
    user: CurrentUser, db: Database, settings: AppSettings
) -> WorkforceSeedRemoveOut:
    """Remove only the workforce resources this seed created (is_demo)."""
    return await WorkforceSeedService(db, settings).remove(user.id)
