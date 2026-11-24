"""Offline contracts for workforce resources (mindflow-workforce-feature
sections 3 + 9, wave 1).

One collection holds people and AI as resources. Covers human/AI create
with profile validation (matching block required, availability must fit
the type, skill/tool lists deduped), list filtering, patch rules, delete,
the optional link to an owned Agent, and owner isolation.
"""

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, seed

BASE = "/api/v1/ai/resources"
AGENTS = "/api/v1/ai/agents"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    from uuid import UUID

    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client


@pytest.fixture
def second(client_factory, register):
    client = client_factory()
    assert register(client, email="Second@Example.com", name="Second User").status_code == 201
    return client


def create_human(client, **overrides):
    payload = {
        "type": "human",
        "name": "Nguyễn Văn A",
        "role": "Frontend Developer",
        "skills": [{"name": "React", "level": 4}, {"name": "Next.js", "level": 4}],
        "human": {"experience_years": 4, "hours_per_week": 40, "current_project_count": 1},
    }
    payload.update(overrides)
    response = client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_ai(client, **overrides):
    payload = {
        "type": "ai",
        "name": "AI Developer",
        "role": "Coding Agent",
        "skills": [{"name": "Refactoring", "level": 4}],
        "ai": {
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "allowed_tools": ["calculator"],
            "denied_scopes": ["payment-data"],
            "token_limit_per_task": 200000,
        },
    }
    payload.update(overrides)
    response = client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_human_defaults(owner):
    response = owner.post(
        BASE, json={"type": "human", "name": "Lê Văn C", "role": "QA Engineer"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["availability_status"] == "available"
    assert body["human"]["current_project_count"] == 0
    assert body["ai"] is None
    assert body["skills"] == []


def test_create_human_full_profile_and_skill_dedupe(owner):
    body = create_human(
        owner,
        skills=[
            {"name": "React", "level": 4},
            {"name": "react", "level": 5},
            {"name": "TypeScript", "level": 3},
        ],
        cost_per_hour=25,
    )
    assert [s["name"] for s in body["skills"]] == ["React", "TypeScript"]
    assert body["human"]["experience_years"] == 4
    assert body["cost_per_hour"] == 25


def test_create_ai_profile_and_cleaned_lists(owner):
    body = create_ai(
        owner,
        ai={
            "provider": "ollama",
            "model": "kimi-k2.7-code",
            "allowed_tools": ["fs", "fs", " git ", ""],
            "denied_scopes": ["payment-data", "payment-data"],
        },
    )
    assert body["availability_status"] == "disconnected"
    assert body["ai"]["allowed_tools"] == ["fs", "git"]
    assert body["ai"]["denied_scopes"] == ["payment-data"]
    assert body["human"] is None


def test_create_ai_requires_ai_profile(owner):
    response = owner.post(BASE, json={"type": "ai", "name": "X", "role": "Agent"})
    assert response.status_code == 422


def test_mismatched_profiles_rejected(owner):
    human = create_human(owner)
    response = owner.post(
        BASE,
        json={
            "type": "human",
            "name": "Y",
            "role": "Dev",
            "ai": {"provider": "groq", "model": "m"},
        },
    )
    assert response.status_code == 422
    response = owner.post(
        BASE,
        json={
            "type": "ai",
            "name": "Z",
            "role": "Agent",
            "human": {"experience_years": 1},
            "ai": {"provider": "groq", "model": "m"},
        },
    )
    assert response.status_code == 422
    assert human["type"] == "human"


def test_availability_must_fit_type(owner):
    response = owner.post(
        BASE,
        json={
            "type": "human",
            "name": "A",
            "role": "Dev",
            "availability_status": "connected",
        },
    )
    assert response.status_code == 422
    response = owner.post(
        BASE,
        json={
            "type": "ai",
            "name": "B",
            "role": "Agent",
            "availability_status": "available",
            "ai": {"provider": "groq", "model": "m"},
        },
    )
    assert response.status_code == 422


def test_list_filter_by_type(owner):
    create_human(owner)
    create_ai(owner)
    all_items = owner.get(BASE).json()["resources"]
    assert len(all_items) == 2
    humans = owner.get(BASE, params={"type": "human"}).json()["resources"]
    assert [r["type"] for r in humans] == ["human"]
    ais = owner.get(BASE, params={"type": "ai"}).json()["resources"]
    assert [r["type"] for r in ais] == ["ai"]


def test_patch_resource(owner):
    created = create_human(owner)
    response = owner.patch(
        f"{BASE}/{created['id']}",
        json={"role": "Senior Frontend Developer", "availability_status": "busy"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "Senior Frontend Developer"
    assert response.json()["availability_status"] == "busy"
    # Availability from the AI vocabulary does not fit a human resource.
    response = owner.patch(
        f"{BASE}/{created['id']}", json={"availability_status": "connected"}
    )
    assert response.status_code == 422
    # A human resource cannot gain an ai profile through patching.
    response = owner.patch(
        f"{BASE}/{created['id']}", json={"ai": {"provider": "groq", "model": "m"}}
    )
    assert response.status_code == 422


def test_delete_resource(owner):
    created = create_ai(owner)
    assert owner.delete(f"{BASE}/{created['id']}").status_code == 204
    response = owner.get(f"{BASE}/{created['id']}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"


def test_owner_isolation(owner, second):
    created = create_human(owner)
    assert second.get(BASE).json()["resources"] == []
    assert second.get(f"{BASE}/{created['id']}").status_code == 404
    assert second.patch(f"{BASE}/{created['id']}", json={"role": "X"}).status_code == 404
    assert second.delete(f"{BASE}/{created['id']}").status_code == 404


def test_ai_agent_link(owner):
    agent = owner.post(
        AGENTS,
        json={
            "name": "Linked Agent",
            "provider": "openai",
            "model": MODEL_A,
            "system_prompt": "Help.",
            "tools": [],
        },
    )
    assert agent.status_code == 201, agent.text
    body = create_ai(
        owner,
        ai={"provider": "openai", "model": MODEL_A, "agent_id": agent.json()["id"]},
    )
    assert body["ai"]["agent_id"] == agent.json()["id"]
    # An agent id that is not the caller's own is rejected as not found.
    response = owner.post(
        BASE,
        json={
            "type": "ai",
            "name": "Bad Link",
            "role": "Agent",
            "ai": {"provider": "openai", "model": MODEL_A, "agent_id": str(uuid4())},
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "agent_not_found"
