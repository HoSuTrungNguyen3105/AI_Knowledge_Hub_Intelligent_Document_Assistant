"""Workspace management v1 (NEXORA Module 02 + Part 3 roles).

Design constraints for this first step (see NEXORA_IMPLEMENTATION_PLAN):
- Every account owns a personal workspace, created lazily and exactly
  once (guarded by a partial unique index on (owner_id, kind=personal)).
- Existing data stays owner-scoped by user_id; this service manages the
  workspace + membership layer only. Modules opt into workspace scoping
  one at a time later — nothing here changes how other data is queried.
- Authorization is enforced here, in the backend: reading a workspace
  requires membership (non-members get 404, not a hint it exists);
  managing requires the owner/admin role.
- The workspace owner's membership row is immutable: the role cannot be
  reassigned and the row cannot be removed through these endpoints.
"""

from uuid import UUID, uuid4

from pymongo.errors import DuplicateKeyError

from app.models.base import utcnow
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
from app.services.ai.base_provider import ProviderError

MANAGER_ROLES = {"owner", "admin"}


class WorkspaceService:
    def __init__(self, db):
        self.db = db

    # --- helpers ---------------------------------------------------------

    async def ensure_personal(self, user_id: UUID) -> dict:
        existing = await self.db.workspaces.find_one(
            {"owner_id": user_id, "kind": "personal"}
        )
        if existing is not None:
            return existing
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "owner_id": user_id,
            "name": "Không gian cá nhân",
            "description": None,
            "kind": "personal",
            "is_demo": False,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await self.db.workspaces.insert_one(doc)
        except DuplicateKeyError:
            # A concurrent first call created it; return that one.
            return await self.db.workspaces.find_one(
                {"owner_id": user_id, "kind": "personal"}
            )
        await self.db.workspace_members.insert_one(
            {
                "_id": uuid4(),
                "workspace_id": doc["_id"],
                "user_id": user_id,
                "role": "owner",
                "invited_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return doc

    async def _membership(self, user_id: UUID, workspace_id: UUID) -> dict | None:
        return await self.db.workspace_members.find_one(
            {"workspace_id": workspace_id, "user_id": user_id}
        )

    async def _require_member(self, user_id: UUID, workspace_id: UUID) -> tuple[dict, dict]:
        workspace = await self.db.workspaces.find_one({"_id": workspace_id})
        membership = await self._membership(user_id, workspace_id)
        if workspace is None or membership is None:
            raise ProviderError("workspace_not_found")
        return workspace, membership

    async def _require_manager(self, user_id: UUID, workspace_id: UUID) -> tuple[dict, dict]:
        workspace, membership = await self._require_member(user_id, workspace_id)
        if membership["role"] not in MANAGER_ROLES:
            raise ProviderError("workspace_forbidden")
        return workspace, membership

    async def _out(self, workspace: dict, my_role: str) -> WorkspaceOut:
        count = await self.db.workspace_members.count_documents(
            {"workspace_id": workspace["_id"]}
        )
        return WorkspaceOut(
            id=workspace["_id"],
            name=workspace["name"],
            description=workspace.get("description"),
            kind=workspace["kind"],
            owner_id=workspace["owner_id"],
            my_role=my_role,
            member_count=count,
            is_demo=bool(workspace.get("is_demo", False)),
            created_at=workspace["created_at"],
            updated_at=workspace["updated_at"],
        )

    # --- workspaces --------------------------------------------------------

    async def list_mine(self, user_id: UUID) -> WorkspaceList:
        await self.ensure_personal(user_id)
        memberships = await self.db.workspace_members.find(
            {"user_id": user_id}
        ).to_list(length=200)
        roles = {m["workspace_id"]: m["role"] for m in memberships}
        workspaces = await self.db.workspaces.find(
            {"_id": {"$in": list(roles)}}
        ).to_list(length=200)
        # Personal workspace first, then oldest first.
        workspaces.sort(key=lambda w: (w["kind"] != "personal", w["created_at"]))
        return WorkspaceList(
            workspaces=[await self._out(w, roles[w["_id"]]) for w in workspaces]
        )

    async def create(self, user_id: UUID, payload: WorkspaceCreate) -> WorkspaceOut:
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "owner_id": user_id,
            "name": payload.name,
            "description": payload.description,
            "kind": "team",
            "is_demo": False,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.workspaces.insert_one(doc)
        await self.db.workspace_members.insert_one(
            {
                "_id": uuid4(),
                "workspace_id": doc["_id"],
                "user_id": user_id,
                "role": "owner",
                "invited_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return await self._out(doc, "owner")

    async def get(self, user_id: UUID, workspace_id: UUID) -> WorkspaceOut:
        workspace, membership = await self._require_member(user_id, workspace_id)
        return await self._out(workspace, membership["role"])

    async def patch(
        self, user_id: UUID, workspace_id: UUID, payload: WorkspacePatch
    ) -> WorkspaceOut:
        workspace, membership = await self._require_manager(user_id, workspace_id)
        values = {
            field: getattr(payload, field)
            for field in ("name", "description")
            if getattr(payload, field) is not None
        }
        if values:
            values["updated_at"] = utcnow()
            await self.db.workspaces.update_one({"_id": workspace_id}, {"$set": values})
            workspace = await self.db.workspaces.find_one({"_id": workspace_id})
        return await self._out(workspace, membership["role"])

    async def delete(self, user_id: UUID, workspace_id: UUID) -> None:
        workspace, membership = await self._require_member(user_id, workspace_id)
        if workspace["kind"] == "personal":
            raise ProviderError("workspace_personal_undeletable")
        if membership["role"] != "owner":
            raise ProviderError("workspace_forbidden")
        await self.db.workspace_members.delete_many({"workspace_id": workspace_id})
        await self.db.workspaces.delete_one({"_id": workspace_id})

    # --- members -----------------------------------------------------------

    async def _member_out(self, membership: dict) -> MemberOut:
        user = await self.db.users.find_one({"_id": membership["user_id"]})
        return MemberOut(
            user_id=membership["user_id"],
            email=(user or {}).get("email", ""),
            name=(user or {}).get("name", ""),
            role=membership["role"],
            created_at=membership["created_at"],
        )

    async def list_members(self, user_id: UUID, workspace_id: UUID) -> MemberList:
        await self._require_member(user_id, workspace_id)
        rows = await self.db.workspace_members.find(
            {"workspace_id": workspace_id}
        ).to_list(length=500)
        rows.sort(key=lambda m: (m["role"] != "owner", m["created_at"]))
        return MemberList(members=[await self._member_out(m) for m in rows])

    async def add_member(
        self, user_id: UUID, workspace_id: UUID, payload: MemberAdd
    ) -> MemberOut:
        await self._require_manager(user_id, workspace_id)
        target = await self.db.users.find_one({"email": str(payload.email)})
        if target is None:
            raise ProviderError("workspace_user_not_found")
        if await self._membership(target["_id"], workspace_id) is not None:
            raise ProviderError("workspace_member_exists")
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "workspace_id": workspace_id,
            "user_id": target["_id"],
            "role": payload.role,
            "invited_by": user_id,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.workspace_members.insert_one(doc)
        return await self._member_out(doc)

    async def _require_target_member(
        self, workspace_id: UUID, target_user_id: UUID
    ) -> dict:
        membership = await self._membership(target_user_id, workspace_id)
        if membership is None:
            raise ProviderError("workspace_member_not_found")
        if membership["role"] == "owner":
            raise ProviderError("workspace_owner_immutable")
        return membership

    async def patch_member(
        self,
        user_id: UUID,
        workspace_id: UUID,
        target_user_id: UUID,
        payload: MemberPatch,
    ) -> MemberOut:
        await self._require_manager(user_id, workspace_id)
        membership = await self._require_target_member(workspace_id, target_user_id)
        await self.db.workspace_members.update_one(
            {"_id": membership["_id"]},
            {"$set": {"role": payload.role, "updated_at": utcnow()}},
        )
        membership["role"] = payload.role
        return await self._member_out(membership)

    async def remove_member(
        self, user_id: UUID, workspace_id: UUID, target_user_id: UUID
    ) -> None:
        _, membership = await self._require_member(user_id, workspace_id)
        # Managers can remove others; anyone may remove themselves (leave).
        if membership["role"] not in MANAGER_ROLES and user_id != target_user_id:
            raise ProviderError("workspace_forbidden")
        target = await self._require_target_member(workspace_id, target_user_id)
        await self.db.workspace_members.delete_one({"_id": target["_id"]})
