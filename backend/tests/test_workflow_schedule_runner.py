"""Offline contracts for schedule activation (Scheduler spec, phase 2).

Covers the central tick (option B): due schedules fire through the
existing n8n Factory path with an atomic claim, executions are recorded
with idempotency keys, the concurrency policies hold, one-time
schedules complete, run-now fires manually, and finished factory runs
are reconciled into execution outcomes.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.api.v1.n8n_factory import n8n_http

BASE = "/api/v1/ai/workflow-schedules"
SECRET = "tick-secret"


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
