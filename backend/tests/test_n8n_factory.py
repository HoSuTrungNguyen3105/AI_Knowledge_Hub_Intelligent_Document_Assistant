"""Offline contracts for the asynchronous MindFlow -> n8n AI Factory bridge.

The n8n HTTP dependency is replaced with a fake: no network, no real n8n,
no real provider calls. These tests verify the async contract — creating a
run fires the webhook with the caller's own agents plus a per-run callback
URL/token and returns immediately; the run completes only when n8n calls
back with the final package — not a live n8n run.
"""

from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

from app.api.v1.n8n_factory import n8n_http
from app.schemas.agents import AgentDetail
from app.services.ai.base_provider import ProviderError
from app.services.n8n_factory import build_team_payload

BASE = "/api/v1/ai/n8n-factory"
PACKAGE = {
    "project_id": "proj-1",
    "status": "completed_with_issues",
    "duration_ms": 1234,
    "task_results": [],
    "review": {"status": "changes_requested", "score": 70},
    "final": {"summary": "Done"},
}


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
    """Stands in for n8n: accepts the run immediately, like workflow 07's
    early Respond node. Completion arrives separately via the callback."""

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def post_json(self, url, payload, timeout_seconds):
        self.calls.append(
            {"url": url, "payload": payload, "timeout": timeout_seconds}
        )
        if self.error:
            raise self.error
        return {"accepted": True, "run_id": payload.get("run_id")}


@pytest.fixture
def fake_n8n(app):
    fake = FakeN8n()
    app.dependency_overrides[n8n_http] = lambda: fake
    return fake


def create_run(client, **overrides):
    body = {"requirement": "Build a landing page", "domain": ["software"]}
    body.update(overrides)
    response = client.post(f"{BASE}/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_runs_require_auth(client):
    assert client.post(f"{BASE}/runs", json={"requirement": "X"}).status_code == 401
    assert client.get(f"{BASE}/runs").status_code == 401
    assert client.get(f"{BASE}/runs/{uuid4()}").status_code == 401


async def test_create_run_fires_webhook_with_agents_and_callback(owner, fake_n8n):
    client, _ = owner
    leader = create_agent(client, "AI Leader", "Lead the team.")
    dev = create_agent(client, "AI Developer", "Write the code.")
    run = create_run(
        client,
        assignments={"AI Leader": leader["id"], "AI Developer": dev["id"]},
    )
    assert run["status"] == "running"
    assert run["result"] is None
    snapshot = {a["role"]: a for a in run["assignments"]}
    assert snapshot["AI Leader"]["name"] == "AI Leader"
    assert snapshot["AI Developer"]["agent_id"] == dev["id"]

    assert len(fake_n8n.calls) == 1
    call = fake_n8n.calls[0]
    assert call["url"].endswith("/webhook/ai-team/start")
    payload = call["payload"]
    assert payload["requirement"] == "Build a landing page"
    assert payload["run_id"] == run["id"]
    assert payload["callback_url"].endswith(f"/runs/{run['id']}/callback")
    assert payload["callback_token"]
    assert payload["agents"]["AI Leader"] == {
        "name": "AI Leader",
        "provider": "openai",
        "model": MODEL_A,
        "system_prompt": "Lead the team.",
    }
    assert payload["agents"]["AI Developer"]["system_prompt"] == "Write the code."


async def test_create_rejects_unknown_role(owner, fake_n8n):
    client, _ = owner
    agent = create_agent(client, "AI Leader")
    response = client.post(
        f"{BASE}/runs",
        json={"requirement": "X", "assignments": {"AI Boss": agent["id"]}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_factory_roles"
    assert fake_n8n.calls == []


async def test_create_rejects_other_users_agent(
    owner, client_factory, register, db, settings, fake_n8n
):
    client, _ = owner
    leader = create_agent(client, "AI Leader")
    other = client_factory()
    assert register(other, email="Other@Example.com").status_code == 201
    other_id = UUID(other.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, other_id, price_in=0.000001, price_out=0.000002)
    response = other.post(
        f"{BASE}/runs",
        json={"requirement": "X", "assignments": {"AI Leader": leader["id"]}},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_not_found"
    assert fake_n8n.calls == []


async def test_create_maps_n8n_outage_and_records_failed_run(owner, app):
    client, _ = owner
    app.dependency_overrides[n8n_http] = lambda: FakeN8n(
        error=ProviderError("n8n_unreachable")
    )
    response = client.post(f"{BASE}/runs", json={"requirement": "X"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "n8n_unreachable"
    listing = client.get(f"{BASE}/runs")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "failed"
    assert items[0]["error"] == "n8n_unreachable"
    assert items[0]["finished_at"] is not None


async def test_callback_completes_run(owner, fake_n8n, client_factory):
    client, _ = owner
    run = create_run(client)
    token = fake_n8n.calls[0]["payload"]["callback_token"]
    callback_url = f"{BASE}/runs/{run['id']}/callback"
    anon = client_factory()  # no session: the token is the credential

    missing = anon.post(callback_url, json={"package": PACKAGE})
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "invalid_callback_token"

    wrong = anon.post(
        callback_url,
        json={"package": PACKAGE},
        headers={"Authorization": "Bearer not-the-token"},
    )
    assert wrong.status_code == 401

    done = anon.post(
        callback_url,
        json={"package": PACKAGE},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed_with_issues"
    assert body["result"]["final"] == {"summary": "Done"}
    assert body["duration_ms"] == 1234
    assert body["finished_at"] is not None

    detail = client.get(f"{BASE}/runs/{run['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed_with_issues"

    # A duplicate callback is accepted but changes nothing.
    again = anon.post(
        callback_url,
        json={"package": {**PACKAGE, "status": "failed"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "completed_with_issues"


async def test_callback_unknown_run_is_404(client):
    response = client.post(
        f"{BASE}/runs/{uuid4()}/callback",
        json={"package": PACKAGE},
        headers={"Authorization": "Bearer whatever"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "factory_run_not_found"


async def test_runs_are_owner_scoped(
    owner, client_factory, register, db, settings, fake_n8n
):
    client, _ = owner
    run = create_run(client)
    other = client_factory()
    assert register(other, email="Other@Example.com").status_code == 201
    other_id = UUID(other.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, other_id, price_in=0.000001, price_out=0.000002)

    detail = other.get(f"{BASE}/runs/{run['id']}")
    assert detail.status_code == 404
    assert detail.json()["detail"]["code"] == "factory_run_not_found"
    assert other.get(f"{BASE}/runs").json() == {"items": [], "total": 0}

    listing = client.get(f"{BASE}/runs").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == run["id"]


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
    assert "run_id" not in payload
    assert payload["agents"]["AI Tester"] == {
        "name": "AI Tester",
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "system_prompt": "",
    }
    run_id = uuid4()
    with_callback = build_team_payload(
        "Do it",
        ["software"],
        {"AI Tester": agent},
        run_id=run_id,
        callback_url="http://host.docker.internal:8000/callback",
        callback_token="tok",
    )
    assert with_callback["run_id"] == str(run_id)
    assert with_callback["callback_url"].endswith("/callback")
    assert with_callback["callback_token"] == "tok"
