"""Offline contracts for schedule activation (Scheduler spec, phase 2).

Covers the central tick (option B): due schedules fire through the
existing n8n Factory path with an atomic claim, executions are recorded
with idempotency keys, the concurrency policies hold, one-time
schedules complete, run-now fires manually, and finished factory runs
are reconciled into execution outcomes.
"""

import copy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.api.v1.n8n_factory import n8n_http
from app.api.v1.n8n_platform import n8n_api_http

BASE = "/api/v1/ai/workflow-schedules"
SECRET = "tick-secret"

PLATFORM_WORKFLOW = {
    "id": "wf-hook",
    "name": "Workflow chạy theo lịch",
    "active": True,
    "tags": [],
    "nodes": [
        {"type": "n8n-nodes-base.webhook", "parameters": {"path": "lich-chay/test"}}
    ],
    "connections": {},
    "settings": {},
    "createdAt": "2026-11-24T00:00:00.000Z",
    "updatedAt": "2026-11-24T00:00:00.000Z",
}


class FakePlatformApi:
    """Stands in for the n8n REST API for platform-target schedules."""

    def __init__(self, workflow=None):
        self.workflow = (
            copy.deepcopy(workflow) if workflow is not None else copy.deepcopy(PLATFORM_WORKFLOW)
        )
        self.webhook_calls = []

    async def get_json(self, url, api_key, timeout_seconds):
        workflow_id = url.rsplit("/workflows/", 1)[1]
        if self.workflow is not None and workflow_id == self.workflow["id"]:
            return 200, copy.deepcopy(self.workflow)
        return 404, {"message": "not found"}

    async def post_json_body(self, url, api_key, payload, timeout_seconds):
        self.webhook_calls.append({"url": url, "payload": payload})
        return 200, {"ok": True}


@pytest.fixture
def fake_platform(app, settings):
    settings.n8n_api_key = SecretStr("test-n8n-key")
    fake = FakePlatformApi()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    return fake


def platform_payload(**overrides):
    body = payload()
    body.pop("factory_request")
    body["target"] = {
        "kind": "n8n_workflow",
        "workflow_id": "wf-hook",
        "payload": {"topic": "tin sáng"},
    }
    body.update(overrides)
    return body


class FakeN8nHTTP:
    def __init__(self):
        self.calls = []

    async def post_json(self, url, payload, timeout_seconds):
        self.calls.append({"url": url, "payload": payload})
        return {"accepted": True}


@pytest.fixture
def fake_http(app):
    fake = FakeN8nHTTP()
    app.dependency_overrides[n8n_http] = lambda: fake
    return fake


@pytest.fixture
def owner(client, register, settings):
    settings.scheduler_tick_secret = SECRET
    # Keep the lifespan loop from re-ticking during the test session.
    settings.scheduler_tick_interval_seconds = 3600
    assert register(client).status_code == 201
    return client


def payload(**overrides):
    body = {
        "name": "Bản tin mỗi sáng",
        "factory_request": {"requirement": "Viết bản tin", "domain": []},
        "schedule_type": "daily",
        "config": {"hour": 8, "minute": 0},
        "timezone": "Asia/Ho_Chi_Minh",
    }
    body.update(overrides)
    return body


async def force_due(db, schedule_id):
    await db.workflow_schedules.update_one(
        {"_id": UUID(schedule_id)},
        {"$set": {"next_run_at": datetime.now(UTC) - timedelta(minutes=5)}},
    )


def tick(client, secret=SECRET):
    return client.post(f"{BASE}/tick", headers={"X-Scheduler-Secret": secret})


async def test_tick_fires_due_schedule(owner, db, fake_http):
    created = owner.post(BASE, json=payload()).json()
    await force_due(db, created["id"])

    result = tick(owner)
    assert result.status_code == 200, result.text
    assert result.json()["fired"] == 1
    assert len(fake_http.calls) == 1

    executions = owner.get(f"{BASE}/{created['id']}/executions").json()
    assert executions["total"] == 1
    execution = executions["items"][0]
    assert execution["status"] == "running"
    assert execution["trigger_type"] == "scheduled"
    assert execution["factory_run_id"] is not None

    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["run_count"] == 1
    assert schedule["last_status"] == "running"
    next_run = datetime.fromisoformat(schedule["next_run_at"])
    assert next_run > datetime.now(UTC)


async def test_second_tick_does_not_refire(owner, db, fake_http):
    created = owner.post(BASE, json=payload()).json()
    await force_due(db, created["id"])
    assert tick(owner).json()["fired"] == 1
    assert tick(owner).json()["fired"] == 0
    assert len(fake_http.calls) == 1


async def test_tick_ignores_future_schedule(owner, fake_http):
    owner.post(BASE, json=payload())
    assert tick(owner).json()["fired"] == 0
    assert fake_http.calls == []


def test_tick_rejects_wrong_secret(owner):
    result = tick(owner, secret="sai-secret")
    assert result.status_code == 401
    assert result.json()["detail"]["code"] == "scheduler_tick_unauthorized"


def test_tick_disabled_without_secret(owner, settings):
    settings.scheduler_tick_secret = ""
    result = tick(owner)
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "scheduler_tick_disabled"


async def test_once_schedule_completes_after_firing(owner, db, fake_http):
    run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    created = owner.post(
        BASE, json=payload(schedule_type="once", config={"run_at": run_at})
    ).json()
    await force_due(db, created["id"])
    assert tick(owner).json()["fired"] == 1
    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["status"] == "completed"
    assert schedule["next_run_at"] is None


async def test_skip_policy_records_skipped_execution(owner, db, fake_http):
    created = owner.post(BASE, json=payload()).json()
    manual = owner.post(f"{BASE}/{created['id']}/run-now")
    assert manual.status_code == 202
    await force_due(db, created["id"])

    result = tick(owner).json()
    assert result["skipped"] == 1
    assert result["fired"] == 0
    executions = owner.get(f"{BASE}/{created['id']}/executions").json()
    statuses = [item["status"] for item in executions["items"]]
    assert statuses.count("skipped") == 1
    skipped = next(i for i in executions["items"] if i["status"] == "skipped")
    assert skipped["error"] == "previous_run_still_open"


async def test_run_now_keeps_the_timetable(owner, fake_http):
    created = owner.post(BASE, json=payload()).json()
    manual = owner.post(f"{BASE}/{created['id']}/run-now")
    assert manual.status_code == 202, manual.text
    execution = manual.json()
    assert execution["trigger_type"] == "manual"
    assert execution["status"] == "running"
    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["next_run_at"] == created["next_run_at"]
    assert schedule["run_count"] == 1


async def test_tick_syncs_finished_factory_run(owner, db, fake_http):
    created = owner.post(BASE, json=payload()).json()
    await force_due(db, created["id"])
    assert tick(owner).json()["fired"] == 1
    execution = owner.get(f"{BASE}/{created['id']}/executions").json()["items"][0]
    await db.n8n_factory_runs.update_one(
        {"_id": UUID(execution["factory_run_id"])},
        {
            "$set": {
                "status": "completed",
                "finished_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        },
    )
    result = tick(owner).json()
    assert result["synced"] == 1
    execution = owner.get(f"{BASE}/{created['id']}/executions").json()["items"][0]
    assert execution["status"] == "success"
    assert execution["duration_ms"] is not None
    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["last_status"] == "success"


async def test_skipped_firing_does_not_count_as_a_run(owner, db, fake_http):
    created = owner.post(BASE, json=payload(max_runs=2)).json()
    manual = owner.post(f"{BASE}/{created['id']}/run-now")
    assert manual.status_code == 202
    before = owner.get(f"{BASE}/{created['id']}").json()
    assert before["run_count"] == 1

    await force_due(db, created["id"])
    result = tick(owner).json()
    assert result["skipped"] == 1
    assert result["fired"] == 0

    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["run_count"] == 1
    assert schedule["last_status"] == "skipped"
    assert schedule["last_run_at"] == before["last_run_at"]
    assert schedule["status"] == "active"


# -- platform targets (task 2) ---------------------------------------------------


async def test_tick_fires_platform_target(owner, db, fake_platform):
    created = owner.post(BASE, json=platform_payload()).json()
    await force_due(db, created["id"])

    result = tick(owner)
    assert result.status_code == 200, result.text
    assert result.json()["fired"] == 1
    # The workflow's webhook received the schedule's payload, and no
    # Factory webhook was involved.
    assert len(fake_platform.webhook_calls) == 1
    assert fake_platform.webhook_calls[0]["payload"] == {"topic": "tin sáng"}
    assert fake_platform.webhook_calls[0]["url"].endswith("/webhook/lich-chay/test")

    executions = owner.get(f"{BASE}/{created['id']}/executions").json()
    execution = executions["items"][0]
    assert execution["status"] == "running"
    assert execution["platform_run_id"] is not None
    assert execution["factory_run_id"] is None

    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["run_count"] == 1
    assert schedule["last_status"] == "running"


async def test_tick_syncs_finished_platform_run(owner, db, fake_platform):
    created = owner.post(BASE, json=platform_payload()).json()
    await force_due(db, created["id"])
    assert tick(owner).json()["fired"] == 1
    execution = owner.get(f"{BASE}/{created['id']}/executions").json()["items"][0]
    # The platform run reports its terminal state (as the callback path
    # would record it); the next tick reconciles it into the execution.
    await db.n8n_runs.update_one(
        {"_id": execution["platform_run_id"]},
        {
            "$set": {
                "status": "success",
                "finished_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        },
    )
    result = tick(owner).json()
    assert result["synced"] == 1
    execution = owner.get(f"{BASE}/{created['id']}/executions").json()["items"][0]
    assert execution["status"] == "success"
    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["last_status"] == "success"


async def test_platform_target_inactive_workflow_fails_the_execution(
    owner, db, app, settings
):
    settings.n8n_api_key = SecretStr("test-n8n-key")
    inactive = {**PLATFORM_WORKFLOW, "active": False}
    fake = FakePlatformApi(workflow=inactive)
    app.dependency_overrides[n8n_api_http] = lambda: fake

    created = owner.post(BASE, json=platform_payload()).json()
    await force_due(db, created["id"])
    result = tick(owner).json()
    assert result["fired"] == 1
    assert fake.webhook_calls == []

    execution = owner.get(f"{BASE}/{created['id']}/executions").json()["items"][0]
    assert execution["status"] == "failed"
    assert execution["error"] == "n8n_workflow_inactive"
    schedule = owner.get(f"{BASE}/{created['id']}").json()
    assert schedule["last_status"] == "failed"
    # A firing that never started does not consume the run budget.
    assert schedule["run_count"] == 0


async def test_tick_records_state_for_the_health_strip(owner, db, fake_http):
    created = owner.post(BASE, json=payload()).json()
    await force_due(db, created["id"])
    assert tick(owner).json()["fired"] == 1

    health = owner.get(f"{BASE}/health").json()
    assert health["last_tick_at"] is not None
    assert health["last_tick_source"] == "external"
    assert health["external_tick_configured"] is True
