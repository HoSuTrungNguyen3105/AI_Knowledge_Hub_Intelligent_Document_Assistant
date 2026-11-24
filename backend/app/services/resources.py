"""Workforce resources v1 (mindflow-workforce-feature.md sections 3 + 9).

One `resources` collection holds both kinds of project resource — people
and AI — told apart by `type`, sharing skills / availability / cost so the
recommendation scoring (a later wave) can rank a single list. An AI
resource may link to an existing MindFlow Agent (`ai.agent_id`) or stand
alone as an external profile (e.g. a coding-agent runtime); a provider
API key is never stored here.

Everything is owner-scoped by user_id like the rest of the app: another
owner's resource reads as not found, never as forbidden.
"""

from uuid import UUID, uuid4

import httpx

from app.core.config import Settings
from app.models.base import utcnow
from app.schemas.resources import (
    AI_AVAILABILITY,
    HUMAN_AVAILABILITY,
    ResourceCreate,
    ResourceList,
    ResourceOut,
    ResourcePatch,
)
from app.services.agent_sync import sync_resource
from app.services.ai.base_provider import ProviderError


class ResourceService:
    def __init__(
        self,
        db,
        settings: Settings,
        sync_transport: httpx.BaseTransport | None = None,
    ):
        self.db = db
        self.settings = settings
        self.sync_transport = sync_transport

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _out(doc: dict) -> ResourceOut:
        return ResourceOut(
            id=doc["_id"],
            type=doc["type"],
            name=doc["name"],
            role=doc["role"],
            skills=doc.get("skills", []),
            availability_status=doc["availability_status"],
            cost_per_hour=doc.get("cost_per_hour"),
            notes=doc.get("notes"),
            human=doc.get("human"),
            ai=doc.get("ai"),
            n8n_sync=doc.get("n8n_sync"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def _get_owned(self, user_id: UUID, resource_id: UUID) -> dict:
        doc = await self.db.resources.find_one(
            {"_id": resource_id, "user_id": user_id}
        )
        if doc is None:
            raise ProviderError("resource_not_found")
        return doc

    async def _check_agent_link(self, user_id: UUID, ai) -> None:
        if ai is not None and ai.agent_id is not None:
            found = await self.db.agents.find_one(
                {"_id": ai.agent_id, "user_id": user_id}
            )
            if found is None:
                raise ProviderError("agent_not_found")

    @staticmethod
    def _check_type_fit(doc_type: str, changes: dict) -> None:
        allowed = AI_AVAILABILITY if doc_type == "ai" else HUMAN_AVAILABILITY
        status = changes.get("availability_status")
        if status is not None and status not in allowed:
            raise ProviderError("invalid_provider_configuration")
        if doc_type == "ai" and changes.get("human") is not None:
            raise ProviderError("invalid_provider_configuration")
        if doc_type == "human" and changes.get("ai") is not None:
            raise ProviderError("invalid_provider_configuration")

    # --- CRUD ------------------------------------------------------------

    async def list(self, user_id: UUID, type: str | None = None) -> ResourceList:
        query: dict = {"user_id": user_id}
        if type is not None:
            query["type"] = type
        cursor = self.db.resources.find(query).sort("name", 1)
        return ResourceList(resources=[self._out(doc) async for doc in cursor])

    async def create(self, user_id: UUID, payload: ResourceCreate) -> ResourceOut:
        await self._check_agent_link(user_id, payload.ai)
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "type": payload.type,
            "name": payload.name,
            "role": payload.role,
            "skills": [skill.model_dump() for skill in payload.skills],
            "availability_status": payload.availability_status,
            "cost_per_hour": payload.cost_per_hour,
            "notes": payload.notes,
            "human": payload.human.model_dump() if payload.human else None,
            "ai": payload.ai.model_dump() if payload.ai else None,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.resources.insert_one(doc)
        if payload.type == "ai":
            # Notify the user's n8n (agent.created, spec section 11).
            # Best-effort: the outcome lands on doc["n8n_sync"] and never
            # fails the creation.
            doc["n8n_sync"] = await sync_resource(
                self.db, self.settings, doc, self.sync_transport
            )
        return self._out(doc)

    async def sync_now(self, user_id: UUID, resource_id: UUID) -> ResourceOut:
        """Re-send the agent.created webhook for an AI resource (e.g.
        after n8n was down or the webhook was configured later)."""
        doc = await self._get_owned(user_id, resource_id)
        if doc["type"] != "ai":
            raise ProviderError("resource_not_ai")
        doc["n8n_sync"] = await sync_resource(
            self.db, self.settings, doc, self.sync_transport
        )
        return self._out(doc)

    async def get(self, user_id: UUID, resource_id: UUID) -> ResourceOut:
        return self._out(await self._get_owned(user_id, resource_id))

    async def patch(
        self, user_id: UUID, resource_id: UUID, payload: ResourcePatch
    ) -> ResourceOut:
        doc = await self._get_owned(user_id, resource_id)
        changes = payload.model_dump(exclude_unset=True)
        self._check_type_fit(doc["type"], changes)
        if "ai" in changes and changes["ai"] is not None:
            await self._check_agent_link(user_id, payload.ai)
        if "skills" in changes and changes["skills"] is not None:
            changes["skills"] = [skill.model_dump() for skill in payload.skills]
        if "human" in changes and changes["human"] is not None:
            changes["human"] = payload.human.model_dump()
        if "ai" in changes and changes["ai"] is not None:
            changes["ai"] = payload.ai.model_dump()
        changes["updated_at"] = utcnow()
        await self.db.resources.update_one(
            {"_id": resource_id, "user_id": user_id}, {"$set": changes}
        )
        return self._out(await self._get_owned(user_id, resource_id))

    async def delete(self, user_id: UUID, resource_id: UUID) -> None:
        result = await self.db.resources.delete_one(
            {"_id": resource_id, "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise ProviderError("resource_not_found")
