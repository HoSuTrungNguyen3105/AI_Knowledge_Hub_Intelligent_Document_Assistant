"""Offline contracts for NEXORA demo seeding (spec Part 5).

Seeding must be idempotent, environment-gated, and must never overwrite,
relabel or delete the caller's real data. Providers are seeded with the
shared test_compare helper — no real provider calls happen.
"""

from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

BASE = "/api/v1/ai/seed/demo"
AGENTS = "/api/v1/ai/agents"
TEAMS = "/api/v1/ai/agent-teams"
AGENT_NAMES = [
    "AI Leader",
    "AI Planner",
    "AI Architect",
    "AI Developer",
    "AI Tester",
    "AI Reviewer",
    "AI Researcher",
]
TEAM_NAMES = ["Nhóm Kỹ thuật (Demo)", "Nhóm Nghiên cứu (Demo)", "Nhóm Vận hành (Demo)"]


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id)
    return client, owner_id


def test_seed_requires_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={}).status_code == 401
    assert client.delete(BASE).status_code == 401


async def test_seed_creates_agents_and_teams_idempotently(owner):
    client, _ = owner
    first = client.post(BASE, json={})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created_agents"] == AGENT_NAMES
    assert body["reused_agents"] == []
    assert body["created_teams"] == TEAM_NAMES
    assert body["skipped_teams"] == []

    status = client.get(BASE).json()
    assert status["enabled"] is True
    assert status["seeded"] is True
    assert status["demo_agents"] == 7
    assert status["demo_teams"] == 3

    # Second run creates nothing new.
    second = client.post(BASE, json={}).json()
    assert second["created_agents"] == []
    assert second["reused_agents"] == AGENT_NAMES
    assert second["created_teams"] == []
    assert second["skipped_teams"] == TEAM_NAMES
    assert len(client.get(AGENTS).json()["agents"]) == 7
    assert len(client.get(TEAMS).json()["teams"]) == 3


async def test_seed_with_explicit_provider_model(owner):
    client, _ = owner
    response = client.post(BASE, json={"provider": "openai", "model": MODEL_A})
    assert response.status_code == 200, response.text
    agents = client.get(AGENTS).json()["agents"]
    assert agents and all(
        a["provider"] == "openai" and a["model"] == MODEL_A for a in agents
    )


async def test_seed_without_configured_provider_is_422(client_factory, register):
    client = client_factory()
    assert register(client, email="NoProvider@Example.com").status_code == 201
    response = client.post(BASE, json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "seed_provider_required"


async def test_seed_disabled_in_production(owner, settings):
    client, _ = owner
    settings.app_env = "production"
    response = client.post(BASE, json={})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "seed_disabled"
    assert client.delete(BASE).status_code == 403
    status = client.get(BASE).json()
    assert status["enabled"] is False
    assert status["app_env"] == "production"


async def test_seed_never_relabels_existing_real_agents(owner):
    client, _ = owner
    real = client.post(
        AGENTS,
        json={
            "name": "AI Leader",
            "provider": "openai",
            "model": MODEL_A,
            "system_prompt": "Mine.",
            "tools": [],
        },
    )
    assert real.status_code == 201, real.text

    body = client.post(BASE, json={}).json()
    assert "AI Leader" in body["reused_agents"]
    assert len(body["created_agents"]) == 6

    # Removal must not delete the user's own AI Leader.
    removed = client.delete(BASE).json()
    assert removed["removed_teams"] == 3
    names = [a["name"] for a in client.get(AGENTS).json()["agents"]]
    assert names == ["AI Leader"]


async def test_remove_keeps_demo_agents_used_by_real_teams(owner):
    client, _ = owner
    client.post(BASE, json={})
    agents = {a["name"]: a["id"] for a in client.get(AGENTS).json()["agents"]}
    real_team = client.post(
        TEAMS,
        json={
            "name": "Nhóm thật của tôi",
            "coordinator_agent_id": agents["AI Leader"],
            "members": [
                {"agent_id": agents["AI Leader"], "role": "coordinator"},
                {"agent_id": agents["AI Developer"], "role": "developer"},
            ],
        },
    )
    assert real_team.status_code == 201, real_team.text

    removed = client.delete(BASE).json()
    assert removed["removed_teams"] == 3
    assert sorted(removed["kept_agents"]) == ["AI Developer", "AI Leader"]
    assert removed["removed_agents"] == 5

    remaining = [a["name"] for a in client.get(AGENTS).json()["agents"]]
    assert sorted(remaining) == ["AI Developer", "AI Leader"]
    team_names = [t["name"] for t in client.get(TEAMS).json()["teams"]]
    assert team_names == ["Nhóm thật của tôi"]
