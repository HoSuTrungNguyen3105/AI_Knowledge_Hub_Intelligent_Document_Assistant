from datetime import timedelta
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import (
    AgentMessage,
    AgentTask,
    AgentTeam,
    AgentWorkflow,
    AgentWorkflowEvent,
    AgentWorkflowFile,
)
from app.models.base import utcnow


class WorkflowRepository:
    """Owner-scoped persistence for Phase 6 teams/workflows/tasks/messages/events."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.teams = db.agent_teams
        self.workflows = db.agent_workflows
        self.tasks = db.agent_tasks
        self.messages = db.agent_messages
        self.events = db.agent_workflow_events
        self.files = db.agent_workflow_files

    # Teams
    async def create_team(self, user_id, *, name, description, coordinator_agent_id, members):
        now = utcnow()
        doc = {
            "_id": AgentTeam.generate_id(),
            "user_id": user_id,
            "name": name,
            "description": description,
            "coordinator_agent_id": coordinator_agent_id,
            "members": [m.model_dump() if hasattr(m, "model_dump") else m for m in members],
            "created_at": now,
            "updated_at": now,
        }
        await self.teams.insert_one(doc)
        return AgentTeam(**doc)

    async def list_teams(self, user_id):
        cursor = self.teams.find({"user_id": user_id}).sort("updated_at", -1)
        return [AgentTeam(**d) async for d in cursor]

    async def get_team(self, user_id, team_id):
        doc = await self.teams.find_one({"_id": team_id, "user_id": user_id})
        return AgentTeam(**doc) if doc else None

    async def update_team(self, user_id, team_id, values):
        if "members" in values:
            values = {
                **values,
                "members": [
                    m.model_dump() if hasattr(m, "model_dump") else m for m in values["members"]
                ],
            }
        doc = await self.teams.find_one_and_update(
            {"_id": team_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return AgentTeam(**doc) if doc else None

    async def delete_team(self, user_id, team_id) -> bool:
        # Deleting a team never deletes the underlying agents or their executions.
        result = await self.teams.delete_one({"_id": team_id, "user_id": user_id})
        return result.deleted_count > 0

    # Workflows
    async def create_workflow(
        self, user_id, *, team_id, title, goal, max_steps, budget,
        output_type="text", design_brief=None, requires_approval=False
    ):
        now = utcnow()
        doc = {
            "_id": AgentWorkflow.generate_id(),
            "user_id": user_id,
            "team_id": team_id,
            "title": title,
            "goal": goal,
            "output_type": output_type,
            "design_brief": design_brief,
            "requires_approval": requires_approval,
            "approval_status": "none",
            "artifact_status": "none",
            "artifact_file_count": 0,
            "artifact_total_bytes": 0,
            "artifact_error_code": None,
            "status": "queued",
            "current_step": 0,
            "max_steps": max_steps,
            "budget": budget,
            "usage": {"agent_turns": 0},
            "final_result": None,
            "error_code": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        await self.workflows.insert_one(doc)
        return AgentWorkflow(**doc)

    async def list_workflows(self, user_id):
        cursor = self.workflows.find({"user_id": user_id}).sort("created_at", -1)
        return [AgentWorkflow(**d) async for d in cursor]

    async def get_workflow(self, user_id, workflow_id):
        doc = await self.workflows.find_one({"_id": workflow_id, "user_id": user_id})
        return AgentWorkflow(**doc) if doc else None

    async def update_workflow(self, user_id, workflow_id, values):
        doc = await self.workflows.find_one_and_update(
            {"_id": workflow_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return AgentWorkflow(**doc) if doc else None

    async def transition_workflow(self, user_id, workflow_id, from_statuses, values):
        """Atomic conditional transition; returns None when the state moved on."""
        doc = await self.workflows.find_one_and_update(
            {"_id": workflow_id, "user_id": user_id, "status": {"$in": list(from_statuses)}},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return AgentWorkflow(**doc) if doc else None

    async def claim_workflow(self, user_id, workflow_id, lease_seconds):
        owner = str(uuid4())
        now = utcnow()
        doc = await self.workflows.find_one_and_update(
            {"_id": workflow_id, "user_id": user_id, "status": {"$in": ["queued", "waiting"]}},
            {
                "$set": {
                    "status": "running",
                    "lease_owner": owner,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "error_code": None,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
        return (AgentWorkflow(**doc), owner) if doc else (None, None)

    async def delete_workflow(self, user_id, workflow_id) -> bool:
        result = await self.workflows.delete_one({"_id": workflow_id, "user_id": user_id})
        if result.deleted_count == 0:
            return False
        await self.tasks.delete_many({"workflow_id": workflow_id, "user_id": user_id})
        await self.messages.delete_many({"workflow_id": workflow_id, "user_id": user_id})
        await self.events.delete_many({"workflow_id": workflow_id, "user_id": user_id})
        await self.files.delete_many({"workflow_id": workflow_id, "user_id": user_id})
        return True

    # Artifact files (website_zip workflows only)
    async def replace_files(self, user_id, workflow_id, files):
        await self.files.delete_many({"workflow_id": workflow_id, "user_id": user_id})
        docs = []
        for parsed in files:
            docs.append(
                {
                    "_id": AgentWorkflowFile.generate_id(),
                    "user_id": user_id,
                    "workflow_id": workflow_id,
                    "path": parsed.path,
                    "content": parsed.content,
                    "size_bytes": parsed.size_bytes,
                    "created_at": utcnow(),
                }
            )
        if docs:
            await self.files.insert_many(docs)
        return [AgentWorkflowFile(**d) for d in docs]

    async def list_files(self, user_id, workflow_id):
        cursor = self.files.find({"user_id": user_id, "workflow_id": workflow_id}).sort("path", 1)
        return [AgentWorkflowFile(**d) async for d in cursor]

    # Tasks
    async def create_task(
        self,
        user_id,
        *,
        workflow_id,
        title,
        description,
        assigned_agent_id,
        created_by_agent_id,
        depends_on=None,
        parent_task_id=None,
    ):
        now = utcnow()
        doc = {
            "_id": AgentTask.generate_id(),
            "user_id": user_id,
            "workflow_id": workflow_id,
            "parent_task_id": parent_task_id,
            "title": title,
            "description": description,
            "assigned_agent_id": assigned_agent_id,
            "created_by_agent_id": created_by_agent_id,
            "depends_on": depends_on or [],
            "status": "pending",
            "priority": "normal",
            "result": None,
            "revision_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.tasks.insert_one(doc)
        return AgentTask(**doc)

    async def list_tasks(self, user_id, workflow_id):
        cursor = self.tasks.find({"user_id": user_id, "workflow_id": workflow_id}).sort(
            "created_at", 1
        )
        return [AgentTask(**d) async for d in cursor]

    async def get_task(self, user_id, task_id):
        doc = await self.tasks.find_one({"_id": task_id, "user_id": user_id})
        return AgentTask(**doc) if doc else None

    async def transition_task(self, user_id, task_id, from_statuses, values):
        doc = await self.tasks.find_one_and_update(
            {"_id": task_id, "user_id": user_id, "status": {"$in": list(from_statuses)}},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return AgentTask(**doc) if doc else None

    async def update_task(self, user_id, task_id, values):
        doc = await self.tasks.find_one_and_update(
            {"_id": task_id, "user_id": user_id},
            {"$set": {**values, "updated_at": utcnow()}},
            return_document=True,
        )
        return AgentTask(**doc) if doc else None

    # Messages (claim prevents double processing)
    async def create_message(
        self,
        user_id,
        *,
        workflow_id,
        task_id,
        from_agent_id,
        to_agent_id,
        message_type,
        content,
        context_refs=None,
    ):
        doc = {
            "_id": AgentMessage.generate_id(),
            "user_id": user_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "from_agent_id": str(from_agent_id),
            "to_agent_id": str(to_agent_id),
            "message_type": message_type,
            "content": content,
            "context_refs": context_refs or [],
            "status": "PENDING",
            "created_at": utcnow(),
            "processed_at": None,
            "error_code": None,
        }
        await self.messages.insert_one(doc)
        return AgentMessage(**doc)

    async def list_messages(self, user_id, workflow_id):
        cursor = self.messages.find({"user_id": user_id, "workflow_id": workflow_id}).sort(
            "created_at", 1
        )
        return [AgentMessage(**d) async for d in cursor]

    async def claim_message(self, user_id, message_id):
        doc = await self.messages.find_one_and_update(
            {"_id": message_id, "user_id": user_id, "status": "PENDING"},
            {"$set": {"status": "PROCESSING"}},
            return_document=True,
        )
        return AgentMessage(**doc) if doc else None

    async def finish_message(self, user_id, message_id, status, error_code=None):
        await self.messages.update_one(
            {"_id": message_id, "user_id": user_id},
            {"$set": {"status": status, "processed_at": utcnow(), "error_code": error_code}},
        )

    # Events
    async def add_event(self, user_id, *, workflow_id, event_type, actor_id=None, payload=None):
        doc = {
            "_id": AgentWorkflowEvent.generate_id(),
            "user_id": user_id,
            "workflow_id": workflow_id,
            "event_type": event_type,
            "actor_id": str(actor_id) if actor_id is not None else None,
            "payload": payload or {},
            "created_at": utcnow(),
        }
        await self.events.insert_one(doc)
        return AgentWorkflowEvent(**doc)

    async def list_events(self, user_id, workflow_id):
        cursor = self.events.find({"user_id": user_id, "workflow_id": workflow_id}).sort(
            "created_at", 1
        )
        return [AgentWorkflowEvent(**d) async for d in cursor]
