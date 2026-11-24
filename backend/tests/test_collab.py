"""Offline contracts for collaboration rooms (NEXORA Module 03, v1).

Rooms live on the multi_chats collection with member Agents; messages
live in collab_messages. Covers room CRUD + member validation, plain
messages, @mention validation, a full mention round-trip against a
mocked provider (the reply is stored in the room with token usage and
the room transcript reaches the Agent), and owner isolation.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/collab/rooms"
AGENTS = "/api/v1/ai/agents"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client, owner_id


@pytest.fixture
def mock_agent(app):
    def configure(handler=None):
        handler = handler or (lambda _: httpx.Response(200, text=sse(chunk("Xin chào từ Agent"), "[DONE]")))
        app.dependency_overrides[agent_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )
    configure()
    return configure


def create_agent(client, name="Agent A"):
    response = client.post(
        AGENTS,
        json={"name": name, "provider": "openai", "model": MODEL_A, "system_prompt": "Help.", "tools": []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_room(client, agent_ids=(), title="Phòng dự án"):
    response = client.post(BASE, json={"title": title, "agent_ids": list(agent_ids)})
    assert response.status_code == 201, response.text
    return response.json()


def test_collab_requires_auth(client):
    assert client.get(BASE).status_code == 401


async def test_room_crud_and_members(owner):
    client, _ = owner
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])
    assert room["title"] == "Phòng dự án"
    assert room["agents"][0]["name"] == "Agent A"
    assert room["message_count"] == 0

    renamed = client.patch(f"{BASE}/{room['id']}", json={"title": "Phòng mới", "agent_ids": []})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Phòng mới"
    assert renamed.json()["agents"] == []

    assert client.delete(f"{BASE}/{room['id']}").status_code == 204
    assert client.get(f"{BASE}/{room['id']}").status_code == 404


async def test_room_rejects_unknown_agent(owner):
    client, _ = owner
    from uuid import uuid4

    response = client.post(BASE, json={"title": "X", "agent_ids": [str(uuid4())]})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_not_found"


async def test_plain_message_and_mention_validation(owner):
    client, _ = owner
    member = create_agent(client, "Trong phòng")
    outsider = create_agent(client, "Ngoài phòng")
    room = create_room(client, [member["id"]])

    posted = client.post(
        f"{BASE}/{room['id']}/messages", json={"content": "Ghi chú chung", "mention_agent_ids": []}
    )
    assert posted.status_code == 201, posted.text
    assert len(posted.json()["messages"]) == 1
    assert posted.json()["messages"][0]["sender_type"] == "user"

    bad = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Ê bạn ngoài", "mention_agent_ids": [outsider["id"]]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "collab_agent_not_member"

    messages = client.get(f"{BASE}/{room['id']}/messages").json()["messages"]
    assert len(messages) == 1  # the rejected post stored nothing


async def test_mention_runs_agent_and_stores_reply(owner, mock_agent, db):
    client, owner_id = owner
    seen_prompts = []

    def handler(request):
        import json

        body = json.loads(request.content)
        seen_prompts.append(body["messages"][-1]["content"])
        return httpx.Response(200, text=sse(chunk("Tôi đã rõ nhiệm vụ"), "[DONE]"))

    mock_agent(handler)
    agent = create_agent(client)
    room = create_room(client, [agent["id"]])

    client.post(f"{BASE}/{room['id']}/messages", json={"content": "Bối cảnh ban đầu", "mention_agent_ids": []})
    posted = client.post(
        f"{BASE}/{room['id']}/messages",
        json={"content": "Hãy bắt đầu việc A", "mention_agent_ids": [agent["id"]]},
    )
    assert posted.status_code == 201, posted.text
    messages = posted.json()["messages"]
    assert len(messages) == 2
    reply = messages[1]
    assert reply["sender_type"] == "agent"
    assert reply["agent_name"] == "Agent A"
    assert reply["content"] == "Tôi đã rõ nhiệm vụ"
    assert reply["status"] == "done"
    assert "Bối cảnh ban đầu" in seen_prompts[0]  # transcript reached the agent
    assert "Hãy bắt đầu việc A" in seen_prompts[0]

    detail = client.get(f"{BASE}/{room['id']}").json()
    assert detail["message_count"] == 3
    stored = await db.collab_messages.count_documents({"room_id": UUID(room["id"])})
    assert stored == 3
    assert owner_id  # owner fixture sanity


async def test_rooms_are_owner_scoped(owner, client_factory, register):
    client, _ = owner
    room = create_room(client)
    stranger = client_factory()
    assert register(stranger, email="stranger3@example.com").status_code == 201
    assert stranger.get(BASE).json()["rooms"] == []
    assert stranger.get(f"{BASE}/{room['id']}").status_code == 404
    response = stranger.post(f"{BASE}/{room['id']}/messages", json={"content": "alo"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "collab_room_not_found"
