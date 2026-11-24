"""Offline contracts for Executive analytics (NEXORA Module 01).

Numbers must come from real stored records: the test inserts known
ai_requests / workflows / tasks / factory runs and checks the computed
windows, rates, model distribution, daily series, and price-based cost
estimates exactly.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

from app.models.base import utcnow

BASE = "/api/v1/ai/analytics/overview"
PRICE_IN = 0.000001
PRICE_OUT = 0.000002


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=PRICE_IN, price_out=PRICE_OUT)
    return client, owner_id, db


def test_analytics_requires_auth(client):
    assert client.get(BASE).status_code == 401


async def test_empty_account_overview(owner):
    client, _, _ = owner
    body = client.get(BASE).json()
    assert body["agents_total"] == 0
    assert body["workflows"] == {"total": 0, "by_status": {}, "success_rate": None}
    assert body["tasks"]["completion_rate"] is None
    assert body["usage_30d"]["requests"] == 0
    assert body["usage_30d"]["cost_estimate"] is None
    assert body["models_30d"] == []
    assert len(body["daily_14d"]) == 14
    assert all(day["requests"] == 0 for day in body["daily_14d"])
    assert body["recent_activity"] == []


async def _request(
    db, user_id, *, days_ago, status="success", in_tokens=0, out_tokens=0, latency=None
):
    await db.ai_requests.insert_one(
        {
            "_id": uuid4(),
            "user_id": user_id,
            "provider": "openai",
            "model": MODEL_A,
            "status": status,
            "conversation_id": None,
            "message_id": None,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "latency_ms": latency,
            "created_at": utcnow() - timedelta(days=days_ago),
        }
    )


async def test_overview_computes_from_real_records(owner):
    client, owner_id, db = owner

    await db.agents.insert_one({"_id": uuid4(), "user_id": owner_id, "name": "Real"})
    await db.agents.insert_one(
        {"_id": uuid4(), "user_id": owner_id, "name": "Demo", "is_demo": True}
    )
    await db.agent_teams.insert_one(
        {"_id": uuid4(), "user_id": owner_id, "name": "Demo team", "is_demo": True}
    )

    workflow_ids = {}
    for status in ("completed", "completed", "failed", "running"):
        workflow_id = uuid4()
        workflow_ids.setdefault(status, []).append(workflow_id)
        await db.agent_workflows.insert_one(
            {"_id": workflow_id, "user_id": owner_id, "status": status}
        )
    for status, count in (("completed", 3), ("failed", 1), ("in_progress", 1)):
        for _ in range(count):
            await db.agent_tasks.insert_one(
                {
                    "_id": uuid4(),
                    "workflow_id": workflow_ids["completed"][0],
                    "status": status,
                }
            )
    await db.n8n_factory_runs.insert_one(
        {"_id": uuid4(), "user_id": owner_id, "status": "completed"}
    )
    await db.n8n_factory_runs.insert_one(
        {"_id": uuid4(), "user_id": owner_id, "status": "running"}
    )

    await _request(db, owner_id, days_ago=1, in_tokens=1000, out_tokens=500, latency=200)
    await _request(db, owner_id, days_ago=2, status="error", in_tokens=100)
    await _request(db, owner_id, days_ago=10, in_tokens=2000, out_tokens=1000)
    await _request(db, owner_id, days_ago=40, in_tokens=9999, out_tokens=9999)

    body = client.get(BASE).json()
    assert body["agents_total"] == 2
    assert body["agents_demo"] == 1
    assert body["teams_total"] == 1
    assert body["teams_demo"] == 1

    assert body["workflows"]["total"] == 4
    assert body["workflows"]["by_status"] == {"completed": 2, "failed": 1, "running": 1}
    assert body["workflows"]["success_rate"] == pytest.approx(2 / 3)
    assert body["tasks"]["total"] == 5
    assert body["tasks"]["completion_rate"] == pytest.approx(3 / 4)
    assert body["factory_runs"] == {"total": 2, "by_status": {"completed": 1, "running": 1}}

    usage7 = body["usage_7d"]
    assert usage7["requests"] == 2
    assert usage7["successful"] == 1
    assert usage7["failed"] == 1
    assert usage7["input_tokens"] == 1100
    assert usage7["output_tokens"] == 500
    assert usage7["avg_latency_ms"] == 200
    # 1000*1e-6 + 500*2e-6 + 100*1e-6 = 0.0021
    assert usage7["cost_estimate"] == pytest.approx(0.0021)
    assert usage7["unpriced_requests"] == 0

    usage30 = body["usage_30d"]
    assert usage30["requests"] == 3
    assert usage30["input_tokens"] == 3100
    assert usage30["output_tokens"] == 1500
    assert usage30["cost_estimate"] == pytest.approx(0.0061)

    assert len(body["models_30d"]) == 1
    model = body["models_30d"][0]
    assert model["provider"] == "openai"
    assert model["model"] == MODEL_A
    assert model["requests"] == 3

    daily = {day["date"]: day for day in body["daily_14d"]}
    assert sum(day["requests"] for day in daily.values()) == 3
    yesterday = (utcnow() - timedelta(days=1)).date().isoformat()
    assert daily[yesterday]["requests"] == 1
    assert daily[yesterday]["input_tokens"] == 1000
