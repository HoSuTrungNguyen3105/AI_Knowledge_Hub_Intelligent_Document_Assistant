"""Offline contracts for the MindFlow -> n8n AI Factory bridge.

The n8n HTTP dependency is replaced with a fake: no network, no real n8n,
no real provider calls. These tests verify the bridge contract — the
caller's own agents are forwarded to the webhook with their provider,
model and system prompt — not a live n8n run.
"""

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

from app.api.v1.n8n_factory import n8n_http
from app.schemas.agents import AgentDetail
from app.services.ai.base_provider import ProviderError
from app.services.n8n_factory import build_team_payload

BASE = "/api/v1/ai/n8n-factory"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client, owner_id


def create_agent(client, name, system_prompt="You are helpful."):
    response = client.post(
        "/api/v1/ai/agents",
        json={
            "name": name,
            "provider": "openai",
            "model": MODEL_A,
            "system_prompt": system_prompt,
            "tools": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


class FakeN8n:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "project_id": "proj-1",
            "status": "completed",
            "task_results": [],
            "final": {"summary": "Done"},
        }
        self.error = error
        self.calls = []

    async def post_json(self, url, payload, timeout_seconds):
        self.calls.append(
            {"url": url, "payload": payload, "timeout": timeout_seconds}
        )
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def fake_n8n(app):
    fake = FakeN8n()
    app.dependency_overrides[n8n_http] = lambda: fake
    return fake


def test_run_requires_auth(client):
    response = client.post(f"{BASE}/run", json={"requirement": "Build a site"})
    assert response.status_code == 401


async def test_run_forwards_own_agents_to_n8n(owner, fake_n8n):
    client, _ = owner
    leader = create_agent(client, "AI Leader", "Lead the team.")
    dev = create_agent(client, "AI Developer", "Write the code.")
    response = client.post(
        f"{BASE}/run",
        json={
            "requirement": "Build a landing page",
            "domain": ["software"],
            "assignments": {"AI Leader": leader["id"], "AI Developer": dev["id"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert len(fake_n8n.calls) == 1
    call = fake_n8n.calls[0]
    assert call["url"].endswith("/webhook/ai-team/start")
    assert call["payload"]["requirement"] == "Build a landing page"
    assert call["payload"]["domain"] == ["software"]
    agents = call["payload"]["agents"]
    assert agents["AI Leader"] == {
        "name": "AI Leader",
        "provider": "openai",
        "model": MODEL_A,
        "system_prompt": "Lead the team.",
    }
    assert agents["AI Developer"]["system_prompt"] == "Write the code."


async def test_run_rejects_unknown_role(owner, fake_n8n):
    client, _ = owner
    agent = create_agent(client, "AI Leader")
    response = client.post(
        f"{BASE}/run",
        json={"requirement": "X", "assignments": {"AI Boss": agent["id"]}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_factory_roles"
    assert fake_n8n.calls == []


async def test_run_rejects_other_users_agent(
    owner, client_factory, register, db, settings, fake_n8n
):
    client, _ = owner
    leader = create_agent(client, "AI Leader")
    other = client_factory()
    assert register(other, email="Other@Example.com").status_code == 201
    other_id = UUID(other.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, other_id, price_in=0.000001, price_out=0.000002)
    response = other.post(
        f"{BASE}/run",
        json={"requirement": "X", "assignments": {"AI Leader": leader["id"]}},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_not_found"
    assert fake_n8n.calls == []


async def test_run_maps_n8n_outage(owner, app):
    client, _ = owner
    app.dependency_overrides[n8n_http] = lambda: FakeN8n(
        error=ProviderError("n8n_unreachable")
    )
    response = client.post(f"{BASE}/run", json={"requirement": "X"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "n8n_unreachable"


def test_build_team_payload_shape():
    agent = AgentDetail(
        id=UUID(int=1),
        name="AI Tester",
        provider="groq",
        model="openai/gpt-oss-20b",
        tools=[],
        system_prompt=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    payload = build_team_payload("Do it", ["software"], {"AI Tester": agent})
    assert payload["source"] == "mindflow"
    assert payload["agents"]["AI Tester"] == {
        "name": "AI Tester",
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "system_prompt": "",
    }
