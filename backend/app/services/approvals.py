"""Human approval gates for workflows (NEXORA Module 10).

A workflow created with ``requires_approval`` parks in ``waiting`` at
the completion gate (see WorkflowService.run_workflow) with its final
result stored and an approval record created here. The owner's decision
then drives the outcome:

- ``approved`` — the workflow completes with the stored result, exactly
  as if the gate had not been there.
- ``rejected`` — the workflow fails with ``approval_rejected``.
- ``changes_requested`` — the comment is delivered to the coordinator
  as a fresh user request and the API layer relaunches the run; when
  the team reaches the gate again a new approval round opens.

Every decision is written to ``activity_logs`` and notified (Phase 2a).
This service performs data effects only; launching runs stays in the
API layer, mirroring the workflows API.
"""

from uuid import UUID, uuid4

from app.models.base import utcnow
from app.repositories.workflows import WorkflowRepository
from app.schemas.approvals import ApprovalOut, DecideIn, DecideOut
from app.services.ai.base_provider import ProviderError

COLLECTION = "approvals"
SUMMARY_LIMIT = 20000

_DECISION_LABELS = {
    "approved": "duyệt",
    "rejected": "từ chối",
    "changes_requested": "yêu cầu sửa",
}


async def _notify(db, user_id: UUID, **kwargs) -> None:
    """Notify via Phase 2a when present; decisions must work regardless
    of merge order, so a missing notifications module is not an error."""
    try:
        from app.services.notifications import notify
    except ImportError:  # pragma: no cover - Phase 2a not merged yet
        return
    await notify(db, user_id, **kwargs)


class ApprovalsService:
    def __init__(self, db):
        self.db = db
        self.collection = db[COLLECTION]
        self.repo = WorkflowRepository(db)

    @staticmethod
    def _out(doc) -> ApprovalOut:
        return ApprovalOut(
            id=doc["_id"],
            workflow_id=doc["workflow_id"],
            workflow_title=doc.get("workflow_title") or "",
            kind=doc.get("kind") or "workflow_completion",
            round=doc.get("round") or 1,
            status=doc["status"],
            summary=doc.get("summary") or "",
            comment=doc.get("comment"),
            created_at=doc["created_at"],
            decided_at=doc.get("decided_at"),
        )

    async def create_for_workflow(self, user_id: UUID, workflow, final_result: str) -> ApprovalOut:
        rounds = await self.collection.count_documents({"workflow_id": workflow.id})
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "workflow_id": workflow.id,
            "workflow_title": workflow.title,
            "kind": "workflow_completion",
            "round": rounds + 1,
            "status": "pending",
            "summary": (final_result or "")[:SUMMARY_LIMIT],
            "comment": None,
            "created_at": utcnow(),
            "decided_at": None,
        }
        await self.collection.insert_one(doc)
        await _notify(
            self.db,
            user_id,
            kind="approval_requested",
            title="Có yêu cầu chờ duyệt",
            body=workflow.title,
            link="/approvals",
        )
        return self._out(doc)

    async def list(self, user_id: UUID, status: str | None = None) -> list[ApprovalOut]:
        query: dict = {"user_id": user_id}
        if status:
            query["status"] = status
        docs = (
            await self.collection.find(query).sort("created_at", -1).limit(100).to_list(length=100)
        )
        return [self._out(doc) for doc in docs]

    async def _require(self, user_id: UUID, approval_id: UUID) -> dict:
        doc = await self.collection.find_one({"_id": approval_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("approval_not_found")
        return doc

    async def get(self, user_id: UUID, approval_id: UUID) -> ApprovalOut:
        return self._out(await self._require(user_id, approval_id))

    async def decide(self, user_id: UUID, approval_id: UUID, payload: DecideIn) -> DecideOut:
        doc = await self._require(user_id, approval_id)
        if doc["status"] != "pending":
            raise ProviderError("approval_already_decided")
        decision = payload.decision
        now = utcnow()
        await self.collection.update_one(
            {"_id": approval_id},
            {"$set": {"status": decision, "comment": payload.comment, "decided_at": now}},
        )
        doc = await self.collection.find_one({"_id": approval_id})

        await self.db.activity_logs.insert_one(
            {
                "_id": uuid4(),
                "user_id": user_id,
                "action": "approval_decided",
                "description": (
                    f"Đã {_DECISION_LABELS[decision]} yêu cầu duyệt "
                    f"workflow '{doc.get('workflow_title') or ''}' (vòng {doc.get('round') or 1})."
                ),
                "created_at": now,
            }
        )
        await _notify(
            self.db,
            user_id,
            kind="approval_decided",
            title=f"Đã {_DECISION_LABELS[decision]} yêu cầu duyệt",
            body=doc.get("workflow_title") or "",
            link="/approvals",
        )

        workflow_status = await self._apply_decision(user_id, doc, payload)
        return DecideOut(approval=self._out(doc), workflow_status=workflow_status)

    async def _apply_decision(self, user_id: UUID, approval: dict, payload: DecideIn) -> str | None:
        workflow = await self.repo.get_workflow(user_id, approval["workflow_id"])
        if workflow is None:
            return None
        if getattr(workflow, "approval_status", "none") != "pending":
            return workflow.status
        workflow_id = workflow.id
        decision = payload.decision

        if decision == "approved":
            updated = await self.repo.transition_workflow(
                user_id,
                workflow_id,
                ["waiting"],
                {
                    "status": "completed",
                    "approval_status": "approved",
                    "completed_at": utcnow(),
                    "lease_owner": None,
                },
            )
            if updated is None:
                return workflow.status
            team = await self.repo.get_team(user_id, workflow.team_id)
            if team is not None and workflow.final_result:
                await self.repo.create_message(
                    user_id,
                    workflow_id=workflow_id,
                    task_id=None,
                    from_agent_id=str(team.coordinator_agent_id),
                    to_agent_id="user",
                    message_type="WORKFLOW_UPDATE",
                    content=workflow.final_result,
                )
            await self.repo.add_event(
                user_id,
                workflow_id=workflow_id,
                event_type="workflow_completed",
                actor_id="user",
            )
            await _notify(
                self.db,
                user_id,
                kind="workflow_completed",
                title="Workflow hoàn thành",
                body=workflow.title,
                link="/agents/workflows",
            )
            return "completed"

        if decision == "rejected":
            updated = await self.repo.transition_workflow(
                user_id,
                workflow_id,
                ["waiting"],
                {
                    "status": "failed",
                    "approval_status": "rejected",
                    "error_code": "approval_rejected",
                    "completed_at": utcnow(),
                    "lease_owner": None,
                },
            )
            if updated is None:
                return workflow.status
            await self.repo.add_event(
                user_id,
                workflow_id=workflow_id,
                event_type="workflow_error",
                actor_id="user",
                payload={"code": "approval_rejected"},
            )
            await _notify(
                self.db,
                user_id,
                kind="workflow_failed",
                title="Workflow thất bại",
                body=f"{workflow.title} — approval_rejected",
                link="/agents/workflows",
            )
            return "failed"

        # changes_requested: hand the feedback to the coordinator and let
        # the API layer relaunch the run from `waiting`.
        updated = await self.repo.transition_workflow(
            user_id,
            workflow_id,
            ["waiting"],
            {"approval_status": "changes_requested", "lease_owner": None},
        )
        if updated is None:
            return workflow.status
        team = await self.repo.get_team(user_id, workflow.team_id)
        if team is not None:
            feedback = payload.comment or (
                "Người dùng yêu cầu chỉnh sửa kết quả trước khi duyệt. "
                "Hãy xem lại toàn bộ kết quả và cải thiện theo góp ý."
            )
            await self.repo.create_message(
                user_id,
                workflow_id=workflow_id,
                task_id=None,
                from_agent_id="user",
                to_agent_id=str(team.coordinator_agent_id),
                message_type="USER_REQUEST",
                content=feedback,
            )
        await self.repo.add_event(
            user_id,
            workflow_id=workflow_id,
            event_type="approval_changes_requested",
            actor_id="user",
            payload={"approval_id": str(approval["_id"])},
        )
        return "waiting"
