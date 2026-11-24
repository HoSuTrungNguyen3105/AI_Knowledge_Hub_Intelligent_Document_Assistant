from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.n8n_factory import (
    FactoryCallbackIn,
    FactoryRunListOut,
    FactoryRunOut,
    FactoryRunRequest,
)
from app.services.n8n_factory import N8nFactoryService, N8nHTTP

router = APIRouter(prefix="/ai/n8n-factory", tags=["n8n factory bridge"])


def n8n_http() -> N8nHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return N8nHTTP()


N8nHTTPDep = Annotated[N8nHTTP, Depends(n8n_http)]


@router.post("/runs", response_model=FactoryRunOut, status_code=202)
async def create_factory_run(
    payload: FactoryRunRequest,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
) -> FactoryRunOut:
    """Start a run: store it, fire the n8n webhook, return immediately.

    n8n executes in the background and calls the run's callback URL with
    the final package; poll GET /runs/{id} for the outcome.
    """
    return await N8nFactoryService(db, settings, http).create_run(user.id, payload)


@router.get("/runs", response_model=FactoryRunListOut)
async def list_factory_runs(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
) -> FactoryRunListOut:
    items, total = await N8nFactoryService(db, settings, http).list_runs(user.id)
    return FactoryRunListOut(items=items, total=total)


@router.get("/runs/{run_id}", response_model=FactoryRunOut)
async def get_factory_run(
    run_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
) -> FactoryRunOut:
    return await N8nFactoryService(db, settings, http).get_run(user.id, run_id)


@router.post("/runs/{run_id}/cancel", response_model=FactoryRunOut)
async def cancel_factory_run(
    run_id: UUID,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
) -> FactoryRunOut:
    """Stop tracking a run. The result n8n may still deliver afterwards is
    discarded; the n8n execution itself is not interrupted."""
    return await N8nFactoryService(db, settings, http).cancel_run(user.id, run_id)


@router.post("/runs/{run_id}/callback", response_model=FactoryRunOut)
async def factory_run_callback(
    run_id: UUID,
    payload: FactoryCallbackIn,
    db: Database,
    settings: AppSettings,
    http: N8nHTTPDep,
    authorization: Annotated[str | None, Header()] = None,
) -> FactoryRunOut:
    """Completion callback for n8n — no user session exists on that side,
    so the run's own callback token (Authorization: Bearer <token>) is the
    credential. The token is generated per run and never leaves the
    MindFlow <-> n8n hop."""
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    return await N8nFactoryService(db, settings, http).complete_run(
        run_id, token, payload.package
    )
