from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import AppSettings, CurrentUser, Database
from app.api.v1.agents import agent_http
from app.schemas.approvals import ApprovalList, ApprovalOut, DecideIn, DecideOut
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.approvals import ApprovalsService
from app.services.workflows import WorkflowService, launch_workflow

router = APIRouter(tags=["Approvals"])

AgentHTTPDep = Annotated[ChatHTTP, Depends(agent_http)]


@router.get("/ai/approvals", response_model=ApprovalList)
async def list_approvals(
    user: CurrentUser,
    db: Database,
    status: Annotated[str | None, Query()] = None,
) -> ApprovalList:
    """Approval inbox: newest first, optionally filtered by status."""
    return ApprovalList(approvals=await ApprovalsService(db).list(user.id, status=status))


@router.get("/ai/approvals/{approval_id}", response_model=ApprovalOut)
async def get_approval(approval_id: UUID, user: CurrentUser, db: Database) -> ApprovalOut:
    return await ApprovalsService(db).get(user.id, approval_id)


@router.post("/ai/approvals/{approval_id}/decide", response_model=DecideOut)
async def decide_approval(
    approval_id: UUID,
    payload: DecideIn,
    user: CurrentUser,
    db: Database,
    settings: AppSettings,
    http: AgentHTTPDep,
) -> DecideOut:
    """Record the owner's decision. Approving completes the workflow
    with its stored result; rejecting fails it; requesting changes
    feeds the comment back to the coordinator and relaunches the run."""
    result = await ApprovalsService(db).decide(user.id, approval_id, payload)
    if payload.decision == "changes_requested" and result.workflow_status == "waiting":
        service = WorkflowService(db, settings, http)
        try:
            claimed, owner = await service.prepare_start(user.id, result.approval.workflow_id)
            launch_workflow(service, user.id, result.approval.workflow_id, owner)
            result = DecideOut(approval=result.approval, workflow_status=claimed.status)
        except ProviderError:
            pass  # stays waiting; the user can resume it manually
    return result
