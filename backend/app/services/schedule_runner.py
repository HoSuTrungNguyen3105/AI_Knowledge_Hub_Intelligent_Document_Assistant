"""Workflow schedule activation (Scheduler spec, phase 2).

Implements spec option B — Backend Central Scheduler + n8n Webhook. A
tick finds due schedules, claims each one atomically by advancing its
``next_run_at`` under a compare-and-set on the old value (so two ticks
can never fire the same slot twice), records an execution with a unique
idempotency key, and starts the run through the existing
:class:`N8nFactoryService` — the same path as a manual Factory run, so
results land in the Factory history and arrive via the same callback.

The tick runs as a background loop inside the backend lifespan (every
``scheduler_tick_interval_seconds``) and through ``POST
/ai/workflow-schedules/tick`` for external cron callers that also keep
the free-tier backend awake. Finished factory runs are reconciled into
executions lazily on each tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.base import utcnow
from app.schemas.n8n_factory import FactoryRunRequest
from app.services.ai.base_provider import ProviderError
from app.services.n8n_factory import RUNS_COLLECTION, N8nFactoryService, N8nHTTP
from app.services.notifications import notify
from app.services.schedule_time import ScheduleInvalid, compute_next_runs

logger = logging.getLogger(__name__)

SCHEDULES = "workflow_schedules"
EXECUTIONS = "workflow_schedule_executions"
RUN_SUCCESS = {"completed", "completed_with_issues"}
RUN_TERMINAL = RUN_SUCCESS | {"needs_configuration", "failed", "cancelled"}
SCHEDULE_LINK = "/agents/workflows?tab=schedules"


class ScheduleRunner:
    def __init__(
        self, db: AsyncIOMotorDatabase, settings, http: N8nHTTP
    ) -> None:
        self.db = db
        self.settings = settings
        self.http = http
        self.schedules = db[SCHEDULES]
        self.executions = db[EXECUTIONS]

    # -- firing ------------------------------------------------------------
    async def _open_execution(self, schedule_id: UUID) -> dict | None:
        return await self.executions.find_one(
            {"schedule_id": schedule_id, "status": "running"}
        )

    async def _insert_execution(self, doc: dict) -> dict:
        try:
            await self.executions.insert_one(doc)
            return doc
        except DuplicateKeyError:
            existing = await self.executions.find_one(
                {"idempotency_key": doc["idempotency_key"]}
            )
            return existing or doc

    def _new_execution(
        self, doc: dict, *, trigger_type: str, scheduled_for, now: datetime
    ) -> dict:
        slot = scheduled_for or now
        return {
            "_id": uuid4(),
            "schedule_id": doc["_id"],
            "user_id": doc["user_id"],
            "factory_run_id": None,
            "n8n_execution_id": None,
            "idempotency_key": f"{doc['_id']}:{slot.isoformat()}:{trigger_type}",
            "trigger_type": trigger_type,
            "scheduled_for": scheduled_for,
            "started_at": now,
            "finished_at": None,
            "status": "running",
            "duration_ms": None,
            "retry_count": 0,
            "error": None,
            "created_at": now,
        }

    async def _mark_fired(
        self, doc: dict, *, outcome: str, now: datetime, advance_next: bool
    ) -> None:
        updates: dict = {
            "last_run_at": now,
            "last_status": outcome,
            "updated_at": now,
            "run_count": doc.get("run_count", 0) + 1,
        }
        finished = doc["schedule_type"] == "once" or (
            doc.get("max_runs") is not None
            and updates["run_count"] >= doc["max_runs"]
        )
        if finished:
            updates["status"] = "completed"
            updates["next_run_at"] = None
        elif advance_next:
            try:
                runs = compute_next_runs(
                    schedule_type=doc["schedule_type"],
                    config=doc["config"],
                    cron_expression=doc.get("cron_expression"),
                    timezone=doc["timezone"],
                    start_at=doc.get("start_at"),
                    end_at=doc.get("end_at"),
                    after=now,
                    count=1,
                )
                updates["next_run_at"] = runs[0] if runs else None
                if not runs:
                    updates["status"] = "completed"
            except ScheduleInvalid:
                updates["status"] = "error"
                updates["next_run_at"] = None
        await self.schedules.update_one({"_id": doc["_id"]}, {"$set": updates})
        doc.update(updates)

    async def fire(
        self,
        doc: dict,
        *,
        trigger_type: str,
        scheduled_for: datetime | None,
        advance_next: bool,
    ) -> dict | None:
        """Fire one schedule once. Returns the execution, or None when the
        queue policy defers a scheduled firing to a later tick."""
        now = utcnow()
        policy = doc.get("concurrency_policy", "skip")
        if await self._open_execution(doc["_id"]) is not None:
            if trigger_type == "scheduled" and policy == "queue":
                return None
            if policy != "allow_parallel":
                skipped = self._new_execution(
                    doc, trigger_type=trigger_type,
                    scheduled_for=scheduled_for, now=now,
                )
                skipped.update(
                    status="skipped",
                    error="previous_run_still_open",
                    finished_at=now,
                    duration_ms=0,
                )
                skipped = await self._insert_execution(skipped)
                await self._mark_fired(
                    doc, outcome="skipped", now=now, advance_next=advance_next
                )
                return self._out(skipped)
        execution = await self._insert_execution(
            self._new_execution(
                doc, trigger_type=trigger_type,
                scheduled_for=scheduled_for, now=now,
            )
        )
        if execution["status"] != "running":
            return self._out(execution)  # idempotent replay of the same slot
        factory = N8nFactoryService(self.db, self.settings, self.http)
        try:
            run = await factory.create_run(
                doc["user_id"], FactoryRunRequest(**doc["factory_request"])
            )
        except ProviderError as err:
            finished = utcnow()
            changes = {
                "status": "failed",
                "error": err.code,
                "finished_at": finished,
                "duration_ms": int((finished - now).total_seconds() * 1000),
            }
            await self.executions.update_one(
                {"_id": execution["_id"]}, {"$set": changes}
            )
            execution.update(changes)
            await self._mark_fired(
                doc, outcome="failed", now=now, advance_next=advance_next
            )
            if doc.get("notify_on_failure"):
                await notify(
                    self.db,
                    doc["user_id"],
                    kind="schedule_failed",
                    title=f"Lịch '{doc['name']}' không kích hoạt được",
                    body=(
                        "n8n chưa nhận lượt chạy này. Kiểm tra Docker/n8n "
                        "ở máy của bạn rồi chạy lại từ tab Lịch chạy."
                    ),
                    link=SCHEDULE_LINK,
                )
            return self._out(execution)
        await self.executions.update_one(
            {"_id": execution["_id"]}, {"$set": {"factory_run_id": run.id}}
        )
        execution["factory_run_id"] = run.id
        await self._mark_fired(
            doc, outcome="running", now=now, advance_next=advance_next
        )
        return self._out(execution)

    # -- tick ----------------------------------------------------------------
    def _next_after(
        self, doc: dict, scheduled_for: datetime, now: datetime
    ) -> datetime | None:
        timing = {
            "schedule_type": doc["schedule_type"],
            "config": doc["config"],
            "cron_expression": doc.get("cron_expression"),
            "timezone": doc["timezone"],
            "start_at": doc.get("start_at"),
            "end_at": doc.get("end_at"),
        }
        try:
            runs = compute_next_runs(**timing, after=scheduled_for, count=1)
            if runs and runs[0] <= now:
                # Missed more than one slot while the backend slept: do not
                # replay the backlog, resume from the next future slot.
                runs = compute_next_runs(**timing, after=now, count=1)
        except ScheduleInvalid:
            return None
        return runs[0] if runs else None

    async def tick(self, now: datetime | None = None) -> dict:
        now = now or utcnow()
        synced = await self.sync_open_executions()
        fired = skipped = deferred = 0
        due = [
            doc
            async for doc in self.schedules.find(
                {"status": "active", "next_run_at": {"$ne": None, "$lte": now}}
            )
            .sort("next_run_at", 1)
            .limit(50)
        ]
        for doc in due:
            if doc.get("concurrency_policy") == "queue" and (
                await self._open_execution(doc["_id"]) is not None
            ):
                deferred += 1
                continue
            scheduled_for = doc["next_run_at"]
            claimed = await self.schedules.find_one_and_update(
                {
                    "_id": doc["_id"],
                    "status": "active",
                    "next_run_at": scheduled_for,
                },
                {
                    "$set": {
                        "next_run_at": self._next_after(doc, scheduled_for, now),
                        "updated_at": now,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
            if claimed is None:
                continue  # another tick claimed this slot first
            result = await self.fire(
                claimed,
                trigger_type="scheduled",
                scheduled_for=scheduled_for,
                advance_next=False,
            )
            if result is None:
                deferred += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                fired += 1
        return {
            "fired": fired,
            "skipped": skipped,
            "deferred": deferred,
            "synced": synced,
        }

    # -- reconciliation ------------------------------------------------------
    async def sync_open_executions(self) -> int:
        synced = 0
        cursor = self.executions.find(
            {"status": "running", "factory_run_id": {"$ne": None}}
        ).limit(50)
        async for execution in cursor:
            run = await self.db[RUNS_COLLECTION].find_one(
                {"_id": execution["factory_run_id"]}
            )
            if run is None or run["status"] not in RUN_TERMINAL:
                continue
            success = run["status"] in RUN_SUCCESS
            finished = run.get("finished_at") or run.get("updated_at") or utcnow()
            duration = None
            if execution.get("started_at") and finished:
                duration = int(
                    (finished - execution["started_at"]).total_seconds() * 1000
                )
            await self.executions.update_one(
                {"_id": execution["_id"]},
                {
                    "$set": {
                        "status": "success" if success else "failed",
                        "error": None if success else (run.get("error") or run["status"]),
                        "finished_at": finished,
                        "duration_ms": duration,
                    }
                },
            )
            schedule = await self.schedules.find_one(
                {"_id": execution["schedule_id"]}
            )
            if schedule is not None:
                await self.schedules.update_one(
                    {"_id": schedule["_id"]},
                    {
                        "$set": {
                            "last_status": "success" if success else "failed",
                            "updated_at": utcnow(),
                        }
                    },
                )
                wanted = (
                    schedule.get("notify_on_success")
                    if success
                    else schedule.get("notify_on_failure")
                )
                if wanted:
                    await notify(
                        self.db,
                        schedule["user_id"],
                        kind="schedule_success" if success else "schedule_failed",
                        title=(
                            f"Lịch '{schedule['name']}' đã chạy xong"
                            if success
                            else f"Lịch '{schedule['name']}' chạy thất bại"
                        ),
                        body="Xem kết quả ở tab AI Factory hoặc lịch sử của lịch.",
                        link=SCHEDULE_LINK,
                    )
            synced += 1
        return synced

    # -- manual + history ------------------------------------------------------
    async def run_now(self, user_id: UUID, schedule_id: UUID) -> dict:
        doc = await self.schedules.find_one(
            {"_id": schedule_id, "user_id": user_id}
        )
        if doc is None:
            raise ProviderError("schedule_not_found")
        result = await self.fire(
            doc, trigger_type="manual", scheduled_for=None, advance_next=False
        )
        return result

    async def list_executions(
        self, user_id: UUID, schedule_id: UUID, limit: int = 50
    ) -> tuple[list[dict], int]:
        doc = await self.schedules.find_one(
            {"_id": schedule_id, "user_id": user_id}
        )
        if doc is None:
            raise ProviderError("schedule_not_found")
        docs = [
            item
            async for item in self.executions.find({"schedule_id": schedule_id})
            .sort("created_at", -1)
            .limit(limit)
        ]
        return [self._out(item) for item in docs], len(docs)

    def _out(self, doc: dict) -> dict:
        return {
            "id": doc["_id"],
            "schedule_id": doc["schedule_id"],
            "factory_run_id": doc.get("factory_run_id"),
            "trigger_type": doc["trigger_type"],
            "scheduled_for": doc.get("scheduled_for"),
            "started_at": doc.get("started_at"),
            "finished_at": doc.get("finished_at"),
            "status": doc["status"],
            "duration_ms": doc.get("duration_ms"),
            "error": doc.get("error"),
            "created_at": doc["created_at"],
        }


async def run_scheduler_loop(db: AsyncIOMotorDatabase, settings) -> None:
    """Background tick loop started from the FastAPI lifespan.

    Ticks immediately at startup (catching schedules that came due while
    the backend was asleep) and then every configured interval. A failed
    tick is logged and never kills the loop.
    """
    http = N8nHTTP()
    while True:
        try:
            result = await ScheduleRunner(db, settings, http).tick()
            if result["fired"] or result["synced"] or result["skipped"]:
                logger.info("Scheduler tick: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(settings.scheduler_tick_interval_seconds)
