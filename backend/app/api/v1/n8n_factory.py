from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.n8n_factory import FactoryRunOut, FactoryRunRequest
from app.services.n8n_factory import N8nFactoryService, N8nHTTP

router = APIRouter(prefix="/ai/n8n-factory", tags=["n8n factory bridge"])


def n8n_http() -> N8nHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return N8nHTTP()


N8nHTTPDep = Annotated[N8nHTTP, Depends(n8n_http)]


@router.post("/run", response_model=FactoryRunOut)
async def run_factory_team(
    payload: FactoryRunRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
) -> FactoryRunOut:
    return await N8nFactoryService(db, settings, http).run_team(user.id, payload)
