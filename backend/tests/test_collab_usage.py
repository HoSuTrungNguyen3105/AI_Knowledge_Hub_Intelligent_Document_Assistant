"""Per-room token/cost usage aggregation (Agent Team wave 5).

The usage endpoint aggregates the STORED Agent replies of a room:
only replies that carry provider-reported token usage are counted,
cost is estimated from the user's synced model prices, unpriced
models are reported as unpriced instead of being given an invented
cost, and roles come from the room's frozen team snapshot when the
room was created from a team.
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, MODEL_B, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

ROOMS = "/api/v1/ai/collab/rooms"
AGENTS = "/api/v1/ai/agents"
PRICE_IN = 0.000001
PRICE_OUT = 0.000002


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, model_id=MODEL_A, price_in=PRICE_IN, price_out=PRICE_OUT)
    await seed(db, settings, owner_id, model_id=MODEL_B, price_in=PRICE_IN, price_out=PRICE_OUT)
    return client, owner_id, db


@pytest.fixture
def mock_agent(app):
    def handler(request):
        payload = json.loads(request.content)
        if payload.get("model") == MODEL_B:
            return httpx.Response(
                200,
                text=sse(
                    chunk("B đây."),
                    {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
                    "[DONE]",
                ),
            )
        return httpx.Response(
            200,
            text=sse(
                chunk("A đây."),
                {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
                "[DONE]",
            ),
        )

    app.dependency_overrides[agent_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(handler)
    )


def make_agent(client, name, model=MODEL_A):
    r = client.post(
        AGENTS, json={"name": name, "provider": "openai", "model": model, "tools": []}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_usage_after_mention_round(owner, mock_agent):
    client, *_ = owner
    dev = make_agent(client, "Dev")
    room = client.post(ROOMS, json={"title": "Phòng", "agent_ids": [dev["id"]]}).json()
    r = client.post(
        f"{ROOMS}/{room['id']}/messages",
        json={"content": "Chào Dev", "mention_agent_ids": [dev["id"]]},
    )
    assert r.status_code == 201, r.text
    usage = client.get(f"{ROOMS}/{room['id']}/usage").json()
    assert usage["requests"] == 1
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert usage["estimated_cost"] == pytest.approx(7 * PRICE_IN + 3 * PRICE_OUT)
    assert usage["unpriced_requests"] == 0
    assert len(usage["by_role"]) == 1
    bucket = usage["by_role"][0]
    assert bucket["agent_name"] == "Dev"
    assert bucket["role"] is None  # manual room: no team role exists
    assert bucket["requests"] == 1
    assert len(usage["by_run"]) == 1
    assert usage["by_run"][0]["requests"] == 1


async def test_usage_roles_from_snapshot_and_unpriced(owner):
    client, owner_id, db = owner
    room_id = uuid4()
    run_id = uuid4()
    agent_id = uuid4()
    now = datetime.now(timezone.utc)
    await db.multi_chats.insert_one(
        {
            "_id": room_id,
            "user_id": owner_id,
            "title": "Phòng team",
            "agent_ids": [agent_id],
            "mode": "directed",
            "moderator_agent_id": agent_id,
            "team_id": uuid4(),
            "team_snapshot": {
                "team_id": uuid4(),
                "team_name": "Team",
                "coordinator_agent_id": agent_id,
                "members": [
                    {"agent_id": agent_id, "agent_name": "Dev", "role": "developer", "enabled": True}
                ],
            },
            "created_at": now,
            "updated_at": now,
        }
    )
    await db.collab_runs.insert_one(
        {"_id": run_id, "room_id": room_id, "user_id": owner_id, "mode": "directed", "status": "completed", "created_at": now, "updated_at": now}
    )
    base = {
        "room_id": room_id,
        "user_id": owner_id,
        "sender_type": "agent",
        "agent_id": agent_id,
        "agent_name": "Dev",
        "status": "done",
        "content": "ok",
        "created_at": now,
    }
    # One priced reply (MODEL_A) and one reply from an unknown model
    # (no synced price) plus one reply with no usage at all.
    await db.collab_messages.insert_many(
        [
            {**base, "_id": uuid4(), "provider": "openai", "model": MODEL_A, "input_tokens": 10, "output_tokens": 5, "run_id": run_id},
            {**base, "_id": uuid4(), "provider": "openai", "model": "model-unknown", "input_tokens": 4, "output_tokens": 1, "run_id": run_id},
            {**base, "_id": uuid4(), "provider": "openai", "model": MODEL_A, "input_tokens": None, "output_tokens": None, "run_id": run_id},
        ]
    )
    usage = client.get(f"{ROOMS}/{room_id}/usage").json()
    # The no-usage reply is not counted at all; tokens are never guessed.
    assert usage["requests"] == 2
    assert usage["input_tokens"] == 14
    assert usage["output_tokens"] == 6
    assert usage["unpriced_requests"] == 1
    assert usage["estimated_cost"] == pytest.approx(10 * PRICE_IN + 5 * PRICE_OUT)
    bucket = usage["by_role"][0]
    assert bucket["role"] == "developer"  # from the frozen snapshot
    assert bucket["requests"] == 2
    assert usage["by_run"][0]["run_id"] == str(run_id)


def test_usage_requires_ownership(owner, mock_agent):
    client, *_ = owner
    missing = uuid4()
    r = client.get(f"{ROOMS}/{missing}/usage")
    assert r.status_code == 404
