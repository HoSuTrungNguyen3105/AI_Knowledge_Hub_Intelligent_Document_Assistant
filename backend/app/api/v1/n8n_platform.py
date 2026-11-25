from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.n8n_platform import (
    N8nParamUpdatesIn,
    N8nStatusOut,
    N8nWorkflowCreateIn,
    N8nWorkflowDetailOut,
    N8nWorkflowListOut,
    N8nWorkflowOut,
)
from app.services.n8n_platform import N8nApiHTTP, N8nPlatformService

router = APIRouter(prefix="/ai/n8n-platform", tags=["n8n platform"])


def n8n_api_http() -> N8nApiHTTP:
    # Dependency override is exclusively for contract tests, never a runtime fallback.
    return N8nApiHTTP()


N8nApiHTTPDep = Annotated[N8nApiHTTP, Depends(n8n_api_http)]


@router.get("/status", response_model=N8nStatusOut)
async def get_n8n_status(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nStatusOut:
    """Connection status of the user's n8n instance. Never fails on an
    unreachable or unconfigured n8n: the status object carries the reason,
    so the page can guide the user instead of showing a raw error."""
    return await N8nPlatformService(db, settings, http).get_status()


@router.get("/workflows", response_model=N8nWorkflowListOut)
async def list_n8n_workflows(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowListOut:
    """The instance's workflows, refreshed from the n8n REST API. When the
    refresh fails the last mirrored list is returned with `sync_error` set."""
    return await N8nPlatformService(db, settings, http).list_workflows()


@router.post("/workflows", response_model=N8nWorkflowOut, status_code=201)
async def create_n8n_workflow(
    payload: N8nWorkflowCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowOut:
    """Create a workflow in the user's n8n from a pasted/built definition.
    It is created inactive; credentials and activation stay in n8n."""
    return await N8nPlatformService(db, settings, http).create_workflow(payload)


@router.get("/workflows/{workflow_id}", response_model=N8nWorkflowDetailOut)
async def get_n8n_workflow_detail(
    workflow_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowDetailOut:
    """One workflow with every node's editable (scalar) parameters."""
    return await N8nPlatformService(db, settings, http).get_workflow_detail(workflow_id)


@router.post("/workflows/{workflow_id}/parameters", response_model=N8nWorkflowDetailOut)
async def update_n8n_workflow_parameters(
    workflow_id: str,
    payload: N8nParamUpdatesIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowDetailOut:
    """Quick-edit node parameter values; the backend PATCHes the workflow
    in n8n. Only existing scalar values change — structure, connections and
    credentials are never touched from MindFlow."""
    return await N8nPlatformService(db, settings, http).update_parameters(
        workflow_id, payload.updates
    )


@router.post("/workflows/{workflow_id}/activate", response_model=N8nWorkflowOut)
async def activate_n8n_workflow(
    workflow_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowOut:
    return await N8nPlatformService(db, settings, http).set_active(workflow_id, True)


@router.post("/workflows/{workflow_id}/deactivate", response_model=N8nWorkflowOut)
async def deactivate_n8n_workflow(
    workflow_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowOut:
    return await N8nPlatformService(db, settings, http).set_active(workflow_id, False)
