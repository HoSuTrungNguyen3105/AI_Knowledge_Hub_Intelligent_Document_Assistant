"""Auto discussion rooms without a Moderator still get a conclusion.

Regression pin for the production report of 2026-11-27: a room created
by hand (no moderator picked) ran its turns and closed with
stop_reason "turn_limit" and final_message_id null — no synthesis was
ever posted, because only the Moderator produced one. The engine now
falls back to another member as synthesizer so an auto run always ends
with a summary message.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, MODEL_B, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

ROOMS = "/api/v1/ai/collab/rooms"
AGENTS = "/api/v1/ai/agents"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
def mock_agent(app):
    def configure(handler=None):
        default = httpx.Response(200, text=sse(chunk("Đã rõ."), "[DONE]"))
        handler = handler or (lambda _: default)
        app.dependency_overrides[agent_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )

    configure()
    return configure


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    return client


def make_agent(client, name):
    r = client.post(
        AGENTS,
        json={"name": name, "provider": "openai", "model": MODEL_A, "tools": []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_auto_room_without_moderator_still_gets_summary(owner, mock_agent):
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        # Distinct content per call so loop detection does not stop the
        # discussion before the turn limit on purpose.
        return httpx.Response(200, text=sse(chunk(f"Ý kiến số {calls['n']}"), "[DONE]"))

    mock_agent(handler)
    first = make_agent(owner, "Agent Một")
    second = make_agent(owner, "Agent Hai")
    r = owner.post(
        ROOMS,
        json={
            "title": "Phòng không Moderator",
            "agent_ids": [first["id"], second["id"]],
            "mode": "auto",
            "max_turns": 2,
        },
    )
    assert r.status_code == 201, r.text
    room = r.json()
    assert room["moderator_agent_id"] is None

    r = owner.post(
        f"{ROOMS}/{room['id']}/messages",
        json={"content": "Các bạn hãy thảo luận và chốt phương án."},
    )
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run is not None
    assert run["status"] == "completed"
    assert run["stop_reason"] == "moderator_summarized"
    assert run["final_message_id"] is not None
    # 2 discussion turns + 1 synthesis turn.
    assert calls["n"] == 3
