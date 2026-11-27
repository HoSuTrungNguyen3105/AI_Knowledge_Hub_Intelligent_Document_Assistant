"""Workflow schedules (Scheduler spec, phase 1: configuration only).

A schedule stores *when* a firing target should fire, in the
``workflow_schedules`` collection, owner-scoped like every other module.
The target is either a saved n8n Factory request (workflow 07 — the
original behaviour and the default for schedules stored before targets
existed) or any synced n8n workflow started through the n8n Platform
run path. Phase 1 covers CRUD, validation, pause/resume and next-run
previews; the central tick that actually fires due schedules (spec
phase 2, option B: backend scheduler + n8n webhook) lives in
``schedule_runner`` and reuses ``compute_next_runs`` plus the stored
``next_run_at``.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import utcnow
from app.schemas.workflow_schedules import (
    ScheduleCreate,
    SchedulePatch,
    SchedulePreviewIn,
)
from app.services.ai.base_provider import ProviderError
from app.services.schedule_time import (
    ScheduleInvalid,
    compute_next_runs,
    describe_schedule,
    schedule_warnings,
)

COLLECTION = "workflow_schedules"
# Single-document scheduler state (last recorded tick), written by the
# ScheduleRunner on every tick and read by the health view.
STATE_COLLECTION = "scheduler_state"


def schedule_target_of(doc: dict) -> dict:
    """The firing target of a stored schedule. Documents written before
    targets existed only ever fired the Factory request."""
    target = doc.get("target")
    if isinstance(target, dict) and target.get("kind") in ("factory", "n8n_workflow"):
        return {
            "kind": target["kind"],
            "workflow_id": target.get("workflow_id"),
            "payload": target.get("payload") or {},
        }
    return {"kind": "factory", "workflow_id": None, "payload": {}}


def _validate_target(doc: dict) -> None:
    """A factory target needs its saved Factory request; an
    n8n_workflow target needs the workflow it should start."""
    target = schedule_target_of(doc)
    if target["kind"] == "factory":
        if not doc.get("factory_request"):
            raise ProviderError("schedule_invalid")
    elif not target.get("workflow_id"):
        raise ProviderError("schedule_invalid")


class WorkflowScheduleService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self.col = db[COLLECTION]

    # -- helpers ---------------------------------------------------------
    def _timing(self, doc: dict) -> dict:
        return {
            "schedule_type": doc["schedule_type"],
            "config": doc["config"],
            "cron_expression": doc.get("cron_expression"),
            "timezone": doc["timezone"],
            "start_at": doc.get("start_at"),
            "end_at": doc.get("end_at"),
        }

    def _first_next(self, doc: dict, after):
        """Validate the timing and return its first run after ``after``."""
        try:
            runs = compute_next_runs(**self._timing(doc), after=after, count=1)
        except ScheduleInvalid:
            raise ProviderError("schedule_invalid") from None
        if not runs:
            if doc["schedule_type"] == "once":
                raise ProviderError("schedule_in_past")
            raise ProviderError("schedule_invalid")
        return runs[0]

    def _out(self, doc: dict) -> dict:
        return {
            "id": doc["_id"],
            "name": doc["name"],
            "description": doc.get("description", ""),
            "factory_request": doc.get("factory_request"),
            "target": schedule_target_of(doc),
            "schedule_type": doc["schedule_type"],
            "cron_expression": doc.get("cron_expression"),
            "config": doc["config"],
            "timezone": doc["timezone"],
            "start_at": doc.get("start_at"),
            "end_at": doc.get("end_at"),
            "status": doc["status"],
            "concurrency_policy": doc.get("concurrency_policy", "skip"),
            "notify_on_success": doc.get("notify_on_success", False),
            "notify_on_failure": doc.get("notify_on_failure", True),
            "max_runs": doc.get("max_runs"),
            "run_count": doc.get("run_count", 0),
            "next_run_at": doc.get("next_run_at"),
            "last_run_at": doc.get("last_run_at"),
            "last_status": doc.get("last_status"),
            "description_text": describe_schedule(
                schedule_type=doc["schedule_type"],
                config=doc["config"],
                cron_expression=doc.get("cron_expression"),
                timezone=doc["timezone"],
            ),
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }

    async def _get_owned(self, user_id: UUID, schedule_id: UUID) -> dict:
        doc = await self.col.find_one({"_id": schedule_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("schedule_not_found")
        return doc

    # -- CRUD ------------------------------------------------------------
    async def create(self, user_id: UUID, payload: ScheduleCreate) -> dict:
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "name": payload.name,
            "description": payload.description,
            "factory_request": (
                payload.factory_request.model_dump(mode="json")
                if payload.factory_request is not None
                else None
            ),
            "target": payload.target.model_dump(mode="json"),
            "schedule_type": payload.schedule_type,
            "cron_expression": payload.cron_expression,
            "config": payload.config.model_dump(mode="json"),
            "timezone": payload.timezone,
            "start_at": payload.start_at,
            "end_at": payload.end_at,
            "status": payload.status,
            "concurrency_policy": payload.concurrency_policy,
            "notify_on_success": payload.notify_on_success,
            "notify_on_failure": payload.notify_on_failure,
            "max_runs": payload.max_runs,
            "run_count": 0,
            "last_run_at": None,
            "last_status": None,
            "created_at": now,
            "updated_at": now,
        }
        _validate_target(doc)
        doc["next_run_at"] = (
            self._first_next(doc, now) if doc["status"] == "active" else None
        )
        await self.col.insert_one(doc)
        return self._out(doc)

    async def list(
        self, user_id: UUID, status: str | None = None, search: str | None = None
    ) -> tuple[list[dict], int, dict]:
        query: dict = {"user_id": user_id}
        if status:
            query["status"] = status
        if search:
            query["name"] = {"$regex": search, "$options": "i"}
        cursor = self.col.find(query).sort("created_at", -1)
        docs = [doc async for doc in cursor]
        stats = {"total": 0, "active": 0, "paused": 0, "completed": 0}
        async for doc in self.col.find({"user_id": user_id}):
            stats["total"] += 1
            if doc["status"] in stats:
                stats[doc["status"]] += 1
        return [self._out(doc) for doc in docs], len(docs), stats

    async def get(self, user_id: UUID, schedule_id: UUID) -> dict:
        return self._out(await self._get_owned(user_id, schedule_id))

    async def update(
        self, user_id: UUID, schedule_id: UUID, payload: SchedulePatch
    ) -> dict:
        doc = await self._get_owned(user_id, schedule_id)
        changes = payload.model_dump(exclude_unset=True)
        if "factory_request" in changes and changes["factory_request"] is not None:
            changes["factory_request"] = payload.factory_request.model_dump(
                mode="json"
            )
        if "target" in changes and changes["target"] is not None:
            changes["target"] = payload.target.model_dump(mode="json")
        if "config" in changes and changes["config"] is not None:
            changes["config"] = payload.config.model_dump(mode="json")
        doc.update(changes)
        if "target" in changes or "factory_request" in changes:
            _validate_target(doc)
        timing_changed = any(
            key in changes
            for key in (
                "schedule_type",
                "cron_expression",
                "config",
                "timezone",
                "start_at",
                "end_at",
            )
        )
        if doc["status"] == "active" and timing_changed:
            doc["next_run_at"] = self._first_next(doc, utcnow())
        doc["updated_at"] = utcnow()
        await self.col.replace_one({"_id": schedule_id}, doc)
        return self._out(doc)

    async def pause(self, user_id: UUID, schedule_id: UUID) -> dict:
        doc = await self._get_owned(user_id, schedule_id)
        doc["status"] = "paused"
        doc["next_run_at"] = None
        doc["updated_at"] = utcnow()
        await self.col.replace_one({"_id": schedule_id}, doc)
        return self._out(doc)

    async def resume(self, user_id: UUID, schedule_id: UUID) -> dict:
        doc = await self._get_owned(user_id, schedule_id)
        now = utcnow()
        try:
            doc["next_run_at"] = self._first_next(doc, now)
            doc["status"] = "active"
        except ProviderError as err:
            if err.code != "schedule_in_past":
                raise
            # A one-time schedule whose moment passed while paused is done.
            doc["status"] = "completed"
            doc["next_run_at"] = None
        doc["updated_at"] = now
        await self.col.replace_one({"_id": schedule_id}, doc)
        return self._out(doc)

    async def delete(self, user_id: UUID, schedule_id: UUID) -> None:
        result = await self.col.delete_one(
            {"_id": schedule_id, "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise ProviderError("schedule_not_found")

    # -- previews ----------------------------------------------------------
    def preview(self, payload: SchedulePreviewIn) -> dict:
        timing = {
            "schedule_type": payload.schedule_type,
            "config": payload.config.model_dump(mode="json"),
            "cron_expression": payload.cron_expression,
            "timezone": payload.timezone,
            "start_at": payload.start_at,
            "end_at": payload.end_at,
        }
        try:
            runs = compute_next_runs(**timing, after=utcnow(), count=5)
            text = describe_schedule(
                schedule_type=payload.schedule_type,
                config=timing["config"],
                cron_expression=payload.cron_expression,
                timezone=payload.timezone,
            )
        except ScheduleInvalid:
            raise ProviderError("schedule_invalid") from None
        if not runs and payload.schedule_type == "once":
            raise ProviderError("schedule_in_past")
        return {
            "description_text": text,
            "next_runs": runs,
            "warnings": schedule_warnings(
                schedule_type=payload.schedule_type,
                config=timing["config"],
                end_at=payload.end_at,
            ),
        }

    async def next_runs(
        self, user_id: UUID, schedule_id: UUID, count: int = 5
    ) -> list:
        doc = await self._get_owned(user_id, schedule_id)
        try:
            return compute_next_runs(
                **self._timing(doc), after=utcnow(), count=count
            )
        except ScheduleInvalid:
            raise ProviderError("schedule_invalid") from None

    # -- firing-chain health ------------------------------------------------
    async def health(self, settings, platform) -> dict:
        """Assemble the health strip from real backend state only.

        The tick secret itself never leaves the server — only whether
        it is set. The last tick comes from the state document the
        runner writes on every tick; n8n reachability reuses the
        platform status check, which never raises.
        """
        state = await self.db[STATE_COLLECTION].find_one({"_id": "tick"})
        status = await platform.get_status()
        return {
            "external_tick_configured": bool(settings.scheduler_tick_secret),
            "last_tick_at": state.get("last_tick_at") if state else None,
            "last_tick_source": state.get("source") if state else None,
            "n8n_configured": status.configured,
            "n8n_reachable": status.reachable if status.configured else None,
            "n8n_error": status.error,
            "checked_at": utcnow(),
        }
