"""MindFlow -> self-hosted n8n bridge behind the AI Factory page.

Runs are asynchronous. Creating a run stores it (collection
``n8n_factory_runs``), fires the workflow-07 webhook with the caller's own
agents (provider, model and system prompt per role) plus a per-run callback
URL and token, and returns immediately. n8n accepts the run, executes it
in the background, and calls the callback when the final package is ready;
the page polls the run until it reaches a terminal status. No agent is
created, copied or re-defined on the n8n side — the run configuration is
read from the caller's own agent records on every run.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.agents import AgentDetail
from app.schemas.n8n_factory import (
    FACTORY_ROLES,
    RUN_TERMINAL_STATUSES,
    FactoryRunOut,
    FactoryRunRequest,
)
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError

WEBHOOK_PATH = "/webhook/ai-team/start"
RUNS_COLLECTION = "n8n_factory_runs"
CALLBACK_PATH = "/api/v1/ai/n8n-factory/runs/{run_id}/callback"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_team_payload(
    requirement: str,
    domain: list[str],
    agents_by_role: dict[str, AgentDetail],
    *,
    run_id: UUID | None = None,
    callback_url: str | None = None,
    callback_token: str | None = None,
) -> dict:
    """Build the workflow-07 webhook body (pure; unit-tested without I/O)."""
    payload: dict = {
        "requirement": requirement,
        "domain": domain,
        "source": "mindflow",
        "agents": {
            role: {
                "name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
                "system_prompt": agent.system_prompt or "",
            }
            for role, agent in agents_by_role.items()
        },
    }
    if run_id is not None:
        payload["run_id"] = str(run_id)
        payload["callback_url"] = callback_url
        payload["callback_token"] = callback_token
    return payload


class N8nHTTP:
    """Thin async client for the user's own n8n instance.

    The base URL comes from server settings only, never from the request,
    and no credentials are attached: the webhook is the entry point of the
    user's self-hosted n8n. Dependency-overridable in contract tests.
    """

    async def post_json(self, url: str, payload: dict, timeout_seconds: float) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            ) as client:
                response = await client.post(url, json=payload)
        except (httpx.TimeoutException, httpx.RequestError):
            raise ProviderError("n8n_unreachable") from None
        if response.status_code >= 400:
            raise ProviderError("n8n_run_failed")
        try:
            data = response.json()
        except ValueError:
            raise ProviderError("n8n_run_failed") from None
        if not isinstance(data, dict):
            raise ProviderError("n8n_run_failed")
        return data


class N8nFactoryService:
    def __init__(self, db: AsyncIOMotorDatabase, settings: Settings, http: N8nHTTP):
        self.db = db
        self.settings = settings
        self.http = http

    @property
    def runs(self):
        return self.db[RUNS_COLLECTION]

    @staticmethod
    def _out(doc: dict) -> FactoryRunOut:
        return FactoryRunOut(
            id=doc["_id"],
            requirement=doc["requirement"],
            domain=doc.get("domain") or [],
            assignments=doc.get("assignments") or [],
            status=doc["status"],
            error=doc.get("error"),
            result=doc.get("result"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            finished_at=doc.get("finished_at"),
            duration_ms=doc.get("duration_ms"),
        )

    async def create_run(self, user_id: UUID, payload: FactoryRunRequest) -> FactoryRunOut:
        unknown = [role for role in payload.assignments if role not in FACTORY_ROLES]
        if unknown:
            raise ProviderError("invalid_factory_roles")
        agents = AgentService(self.db, self.settings)
        by_role: dict[str, AgentDetail] = {}
        for role, agent_id in payload.assignments.items():
            # get_agent is owner-scoped: another user's agent id is a 404.
            by_role[role] = await agents.get_agent(user_id, agent_id)

        run_id = uuid4()
        now = _utcnow()
        token = secrets.token_urlsafe(32)
        doc = {
            "_id": run_id,
            "user_id": user_id,
            "requirement": payload.requirement,
            "domain": payload.domain,
            "assignments": [
                {
                    "role": role,
                    "agent_id": agent.id,
                    "name": agent.name,
                    "provider": agent.provider,
                    "model": agent.model,
                }
                for role, agent in by_role.items()
            ],
            "status": "queued",
            "error": None,
            "result": None,
            "callback_token": token,
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
            "duration_ms": None,
        }
        await self.runs.insert_one(doc)

        callback_url = (
            f"{self.settings.n8n_factory_callback_base_url}"
            f"{CALLBACK_PATH.format(run_id=run_id)}"
        )
        body = build_team_payload(
            payload.requirement,
            payload.domain,
            by_role,
            run_id=run_id,
            callback_url=callback_url,
            callback_token=token,
        )
        url = f"{self.settings.n8n_webhook_base_url}{WEBHOOK_PATH}"
        try:
            await self.http.post_json(url, body, self.settings.n8n_factory_timeout_seconds)
        except ProviderError as err:
            # The run never started; record the failure so the page history
            # shows it, then surface the same error to the caller.
            await self.runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": err.code,
                        "updated_at": _utcnow(),
                        "finished_at": _utcnow(),
                    }
                },
            )
            raise
        await self.runs.update_one(
            {"_id": run_id}, {"$set": {"status": "running", "updated_at": _utcnow()}}
        )
        doc["status"] = "running"
        return self._out(doc)

    async def _expire_stale(self, query: dict) -> None:
        """Fail active runs whose callback never arrived (lazy timeout)."""
        cutoff = _utcnow() - timedelta(
            seconds=self.settings.n8n_factory_run_timeout_seconds
        )
        now = _utcnow()
        await self.runs.update_many(
            {
                **query,
                "status": {"$in": ["queued", "running"]},
                "created_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "status": "failed",
                    "error": "run_timed_out",
                    "updated_at": now,
                    "finished_at": now,
                }
            },
        )

    async def list_runs(self, user_id: UUID, limit: int = 50) -> tuple[list[FactoryRunOut], int]:
        await self._expire_stale({"user_id": user_id})
        cursor = self.runs.find({"user_id": user_id}).sort("created_at", -1)
        docs = await cursor.to_list(length=limit)
        total = await self.runs.count_documents({"user_id": user_id})
        return [self._out(doc) for doc in docs], total

    async def get_run(self, user_id: UUID, run_id: UUID) -> FactoryRunOut:
        await self._expire_stale({"user_id": user_id, "_id": run_id})
        doc = await self.runs.find_one({"_id": run_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("factory_run_not_found")
        return self._out(doc)

    async def cancel_run(self, user_id: UUID, run_id: UUID) -> FactoryRunOut:
        """Stop tracking a run at the user's request.

        The run is marked cancelled (terminal), so a callback that still
        arrives afterwards is acknowledged but never applied. The n8n
        execution itself is NOT killed — the webhook offers no stop
        channel — so it may run to completion in the background; only its
        result is discarded. Cancelling a finished run changes nothing.
        """
        doc = await self.runs.find_one({"_id": run_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("factory_run_not_found")
        if doc["status"] in RUN_TERMINAL_STATUSES:
            return self._out(doc)
        finished = _utcnow()
        created = doc["created_at"]
        if created.tzinfo is None:  # Mongo reads come back naive (UTC)
            created = created.replace(tzinfo=timezone.utc)
        duration = int((finished - created).total_seconds() * 1000)
        changes = {
            "status": "cancelled",
            "error": "cancelled_by_user",
            "duration_ms": duration,
            "updated_at": finished,
            "finished_at": finished,
        }
        await self.runs.update_one({"_id": run_id}, {"$set": changes})
        doc.update(changes)
        return self._out(doc)

    async def complete_run(self, run_id: UUID, token: str, package: dict) -> FactoryRunOut:
        """Store the final package n8n calls back with. Idempotent: a
        duplicate callback for a finished run returns the stored run."""
        doc = await self.runs.find_one({"_id": run_id})
        if doc is None:
            raise ProviderError("factory_run_not_found")
        if not secrets.compare_digest(str(doc.get("callback_token") or ""), token or ""):
            raise ProviderError("invalid_callback_token")
        if doc["status"] in RUN_TERMINAL_STATUSES:
            return self._out(doc)
        status = package.get("status")
        if status not in RUN_TERMINAL_STATUSES:
            status = "completed"
        finished = _utcnow()
        duration = package.get("duration_ms")
        if not isinstance(duration, int) or duration < 0:
            created = doc["created_at"]
            if created.tzinfo is None:  # Mongo reads come back naive (UTC)
                created = created.replace(tzinfo=timezone.utc)
            duration = int((finished - created).total_seconds() * 1000)
        error = package.get("error") or package.get("plan_error")
        await self.runs.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": status,
                    "error": error,
                    "result": package,
                    "duration_ms": duration,
                    "updated_at": finished,
                    "finished_at": finished,
                }
            },
        )
        doc.update(
            {
                "status": status,
                "error": error,
                "result": package,
                "duration_ms": duration,
                "updated_at": finished,
                "finished_at": finished,
            }
        )
        return self._out(doc)
