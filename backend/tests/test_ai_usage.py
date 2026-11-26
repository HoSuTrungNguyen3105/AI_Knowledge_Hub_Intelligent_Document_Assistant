"""Offline contracts for AI Usage & Cost Analytics.

Numbers must come from real stored records (ai_requests /
agent_executions) and the caller's own prices: synced model prices by
default, the caller's versioned overrides when set. Unpriced usage must
report cost as None, never an invented number.
"""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

from app.models.base import utcnow

BASE = "/api/v1/ai/ai-usage"
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


async def _request(
    db,
    user_id,
    *,
    days_ago=0,
    provider="openai",
    model=MODEL_A,
    status="success",
    in_tokens=0,
    out_tokens=0,
    latency=None,
):
    await db.ai_requests.insert_one(
        {
            "_id": uuid4(),
            "user_id": user_id,
            "provider": provider,
            "model": model,
            "status": status,
            "conversation_id": None,
            "message_id": None,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "latency_ms": latency,
            "created_at": utcnow() - timedelta(days=days_ago),
        }
    )


def test_ai_usage_requires_auth(client):
    assert client.get(f"{BASE}/overview").status_code == 401
    assert client.get(f"{BASE}/history").status_code == 401
    assert client.get(f"{BASE}/budgets").status_code == 401


async def test_overview_and_breakdowns(owner):
    client, owner_id, db = owner
    await _request(db, owner_id, in_tokens=1000, out_tokens=500, latency=200)
    await _request(db, owner_id, in_tokens=2000, out_tokens=1000, latency=400, status="error")
    await _request(db, owner_id, days_ago=40, in_tokens=9999, out_tokens=9999)

    body = client.get(f"{BASE}/overview", params={"preset": "30d"}).json()
    totals = body["totals"]
    assert totals["requests"] == 2
    assert totals["successful"] == 1
    assert totals["failed"] == 1
    assert totals["input_tokens"] == 3000
    assert totals["output_tokens"] == 1500
    assert totals["total_tokens"] == 4500
    expected = 3000 * PRICE_IN + 1500 * PRICE_OUT
    assert totals["cost_estimate"] == pytest.approx(expected)
    assert totals["avg_cost_per_request"] == pytest.approx(expected / 2)

    providers = client.get(f"{BASE}/providers", params={"preset": "30d"}).json()
    assert len(providers) == 1
    assert providers[0]["provider"] == "openai"
    assert providers[0]["requests"] == 2

    models = client.get(f"{BASE}/models", params={"preset": "30d"}).json()
    assert models[0]["model"] == MODEL_A
    assert models[0]["success_rate"] == 0.5
    assert models[0]["avg_latency_ms"] == 300

    series = client.get(f"{BASE}/timeseries", params={"preset": "7d"}).json()
    assert len(series) == 8
    assert sum(point["requests"] for point in series) == 2


async def test_history_pagination_filter_and_csv(owner):
    client, owner_id, db = owner
    for index in range(5):
        await _request(db, owner_id, in_tokens=100 * (index + 1), out_tokens=10)
    await _request(db, owner_id, provider="groq", model="openai/gpt-oss-120b")

    page = client.get(f"{BASE}/history", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 6
    assert len(page["items"]) == 2
    filtered = client.get(
        f"{BASE}/history", params={"provider": "groq"}
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["cost_estimate"] is None  # unpriced model

    response = client.get(f"{BASE}/export", params={"preset": "30d"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("time,provider,model")
    assert len(lines) == 7


async def test_pricing_override_versions_and_applies(owner):
    client, owner_id, db = owner
    await _request(db, owner_id, in_tokens=1_000_000, out_tokens=0)

    rows = client.get(f"{BASE}/pricing").json()
    synced = [row for row in rows if row["model"] == MODEL_A]
    assert synced and synced[0]["source"] == "synced"

    updated = client.put(
        f"{BASE}/pricing",
        json={
            "provider": "openai",
            "model": MODEL_A,
            "input_price_per_1m": 3.0,
            "output_price_per_1m": 9.0,
        },
    ).json()
    assert updated["source"] == "override"
    assert updated["version"] == 1

    again = client.put(
        f"{BASE}/pricing",
        json={
            "provider": "openai",
            "model": MODEL_A,
            "input_price_per_1m": 4.0,
            "output_price_per_1m": 9.0,
        },
    ).json()
    assert again["version"] == 2

    totals = client.get(f"{BASE}/overview", params={"preset": "30d"}).json()["totals"]
    assert totals["cost_estimate"] == pytest.approx(4.0)  # 1M input tokens at $4/1M


async def test_agents_breakdown_and_budgets(owner):
    client, owner_id, db = owner
    agent_id = uuid4()
    await db.agents.insert_one(
        {"_id": agent_id, "user_id": owner_id, "name": "Researcher"}
    )
    for status, cost in (("completed", 0.5), ("failed", 0.25)):
        await db.agent_executions.insert_one(
            {
                "_id": uuid4(),
                "agent_id": agent_id,
                "user_id": owner_id,
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "status": status,
                "input_tokens": 100,
                "output_tokens": 50,
                "latency_ms": 100,
                "estimated_cost": cost,
                "created_at": utcnow(),
            }
        )

    agents = client.get(f"{BASE}/agents", params={"preset": "30d"}).json()
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "Researcher"
    assert agents[0]["total_tokens"] == 300
    assert agents[0]["estimated_cost"] == pytest.approx(0.75)
    assert agents[0]["success_rate"] == 0.5

    await _request(db, owner_id, in_tokens=1000, out_tokens=500)
    budget = client.put(
        f"{BASE}/budgets",
        json={"scope_type": "total", "scope_id": "", "monthly_limit_usd": 0.005},
    ).json()
    assert budget["spent_usd"] == pytest.approx(1000 * PRICE_IN + 500 * PRICE_OUT)
    assert budget["percent_used"] == pytest.approx(40.0)
    assert budget["alert_level"] == 0

    tight = client.put(
        f"{BASE}/budgets",
        json={"scope_type": "total", "scope_id": "", "monthly_limit_usd": 0.0025},
    ).json()
    assert tight["alert_level"] == 80
    listed = client.get(f"{BASE}/budgets").json()
    assert len(listed) == 1
    notifications = await db.notifications.find(
        {"user_id": owner_id, "kind": "budget_alert"}
    ).to_list(length=10)
    assert len(notifications) == 1
