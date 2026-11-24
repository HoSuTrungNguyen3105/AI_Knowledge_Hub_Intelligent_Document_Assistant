from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import CurrentUser, Database
from app.schemas.workspaces import (
    MemberAdd,
    MemberList,
    MemberOut,
    MemberPatch,
    WorkspaceCreate,
    WorkspaceList,
    WorkspaceOut,
    WorkspacePatch,
)
from app.services.workspaces import WorkspaceService

router = APIRouter(tags=["Workspaces"])


def _service(db) -> WorkspaceService:
    return WorkspaceService(db)


@router.get("/ai/workspaces", response_model=WorkspaceList)
async def list_workspaces(user: CurrentUser, db: Database) -> WorkspaceList:
    """Workspaces the caller belongs to. The caller's personal workspace
    is created on first use, so this list is never empty."""
    return await _service(db).list_mine(user.id)


@router.post("/ai/workspaces", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: Database
) -> WorkspaceOut:
    return await _service(db).create(user.id, payload)


@router.get("/ai/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: UUID, user: CurrentUser, db: Database
) -> WorkspaceOut:
    return await _service(db).get(user.id, workspace_id)


@router.patch("/ai/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def patch_workspace(
    workspace_id: UUID, payload: WorkspacePatch, user: CurrentUser, db: Database
) -> WorkspaceOut:
    return await _service(db).patch(user.id, workspace_id, payload)


@router.delete("/ai/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: UUID, user: CurrentUser, db: Database
) -> Response:
    """Owner only, and never for the personal workspace."""
    await _service(db).delete(user.id, workspace_id)
    return Response(status_code=204)


@router.get("/ai/workspaces/{workspace_id}/members", response_model=MemberList)
async def list_members(
    workspace_id: UUID, user: CurrentUser, db: Database
) -> MemberList:
    return await _service(db).list_members(user.id, workspace_id)


@router.post(
    "/ai/workspaces/{workspace_id}/members", response_model=MemberOut, status_code=201
)
async def add_member(
    workspace_id: UUID, payload: MemberAdd, user: CurrentUser, db: Database
) -> MemberOut:
    """Add an existing MindFlow account (looked up by email) with a role.
    Owner/admin only; the owner role itself can never be assigned."""
    return await _service(db).add_member(user.id, workspace_id, payload)


@router.patch(
    "/ai/workspaces/{workspace_id}/members/{member_user_id}", response_model=MemberOut
)
async def patch_member(
    workspace_id: UUID,
    member_user_id: UUID,
    payload: MemberPatch,
    user: CurrentUser,
    db: Database,
) -> MemberOut:
    return await _service(db).patch_member(user.id, workspace_id, member_user_id, payload)


@router.delete(
    "/ai/workspaces/{workspace_id}/members/{member_user_id}", status_code=204
)
async def remove_member(
    workspace_id: UUID, member_user_id: UUID, user: CurrentUser, db: Database
) -> Response:
    """Owner/admin removes a member; a member may also remove themselves
    (leave). The workspace owner can never be removed here."""
    await _service(db).remove_member(user.id, workspace_id, member_user_id)
    return Response(status_code=204)
