from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.schemas.n8n_platform import (
    N8nExecutionDetailOut,
    N8nExecutionListOut,
    N8nRunCreateIn,
    N8nRunListOut,
    N8nRunOut,
    N8nStatsOut,
    N8nStatusOut,
    N8nWorkflowCreateIn,
    N8nWorkflowDetailOut,
    N8nWorkflowExportOut,
    N8nWorkflowListOut,
    N8nWorkflowOut,
    N8nWorkflowValidateIn,
    N8nWorkflowValidateOut,
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
    """One workflow with its nodes (read-only detail view). Node
    parameters are edited in n8n itself, never from MindFlow."""
    return await N8nPlatformService(db, settings, http).get_workflow_detail(workflow_id)


@router.post("/workflows/validate", response_model=N8nWorkflowValidateOut)
async def validate_n8n_workflow(
    payload: N8nWorkflowValidateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowValidateOut:
    """Validate a parsed workflow JSON and preview it. Creates nothing —
    the import flow calls this before the user confirms."""
    return await N8nPlatformService(db, settings, http).validate_workflow(
        payload.workflow
    )


@router.put("/workflows/{workflow_id}", response_model=N8nWorkflowOut)
async def update_n8n_workflow(
    workflow_id: str,
    payload: N8nWorkflowCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowOut:
    """Replace an existing workflow's definition with an imported JSON.
    The stored n8n id decides which workflow is updated."""
    return await N8nPlatformService(db, settings, http).update_workflow(
        workflow_id, payload
    )


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_n8n_workflow(
    workflow_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> Response:
    """Delete a workflow in n8n and drop its mirror entry."""
    await N8nPlatformService(db, settings, http).delete_workflow(workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workflows/{workflow_id}/export", response_model=N8nWorkflowExportOut)
async def export_n8n_workflow(
    workflow_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nWorkflowExportOut:
    """The workflow definition read live from n8n, for download/backup."""
    return await N8nPlatformService(db, settings, http).export_workflow(workflow_id)


@router.get("/stats", response_model=N8nStatsOut)
async def get_n8n_stats(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nStatsOut:
    """Workflow Management dashboard statistics: synced workflow counts
    plus today's execution counts read live from n8n (None when n8n
    cannot be read — never estimated)."""
    return await N8nPlatformService(db, settings, http).get_stats()


@router.get("/executions", response_model=N8nExecutionListOut)
async def list_n8n_executions(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
    workflow_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> N8nExecutionListOut:
    """Execution history synced live from n8n, with workflow/status
    filters. A read failure is reported on the object, not raised."""
    return await N8nPlatformService(db, settings, http).list_executions(
        workflow_id=workflow_id, status_filter=status_filter, limit=limit
    )


@router.get("/executions/{execution_id}", response_model=N8nExecutionDetailOut)
async def get_n8n_execution(
    execution_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nExecutionDetailOut:
    """One execution with its error (if any) and per-node results."""
    return await N8nPlatformService(db, settings, http).get_execution(execution_id)


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


@router.post("/runs", response_model=N8nRunOut, status_code=201)
async def start_n8n_run(
    payload: N8nRunCreateIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nRunOut:
    """Start an active webhook workflow and track the run (phase 2)."""
    return await N8nPlatformService(db, settings, http).start_run(user.id, payload)


@router.get("/runs", response_model=N8nRunListOut)
async def list_n8n_runs(
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
    workflow_id: str | None = None,
    limit: int = 50,
) -> N8nRunListOut:
    return await N8nPlatformService(db, settings, http).list_runs(
        user.id, workflow_id=workflow_id, limit=limit
    )


@router.get("/runs/{run_id}", response_model=N8nRunOut)
async def get_n8n_run(
    run_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nRunOut:
    return await N8nPlatformService(db, settings, http).get_run(user.id, run_id)


@router.post("/runs/{run_id}/stop", response_model=N8nRunOut)
async def stop_n8n_run(
    run_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nRunOut:
    return await N8nPlatformService(db, settings, http).stop_run(user.id, run_id)


@router.post("/runs/{run_id}/retry", response_model=N8nRunOut, status_code=201)
async def retry_n8n_run(
    run_id: str,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: N8nApiHTTPDep,
) -> N8nRunOut:
    return await N8nPlatformService(db, settings, http).retry_run(user.id, run_id)
