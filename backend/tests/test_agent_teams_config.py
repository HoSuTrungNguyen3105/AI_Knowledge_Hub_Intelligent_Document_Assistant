"""Agent Team assignment configuration (UPDATE_EXISTING_FEATURES_AGENT_TEAM, wave 1).

Pins the extended team-member contract: assignment fields round-trip
through the API, suggested + custom roles are accepted, per-team
provider/model overrides are stored and reported as the member's
effective values, legacy member payloads keep working with defaults,
and AgentService.prepare_run honours an override by running an
effective copy — the stored Agent is never modified.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, MODEL_B, chunk, seed, sse

from app.schemas.agents import RunRequest
from app.services.agents import AgentService
from app.services.ai.chat import ChatHTTP

TEAMS = "/api/v1/ai/agent-teams"
AGENTS = "/api/v1/ai/agents"


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, model_id=MODEL_A)
    await seed(db, settings, owner_id, model_id=MODEL_B)
    return client, owner_id, db, settings


def make_agent(client, name, model=MODEL_A):
    r = client.post(
        AGENTS, json={"name": name, "provider": "openai", "model": model, "tools": []}
    )
    assert r.status_code == 201, r.text
    return r.json()


def create_team(client, members, coordinator_id):
    r = client.post(
        TEAMS,
        json={"name": "Team", "coordinator_agent_id": coordinator_id, "members": members},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_member_assignment_fields_round_trip(owner):
    client, *_ = owner
    lead = make_agent(client, "Lead")
    dev = make_agent(client, "Dev")
    team = create_team(
        client,
        [
            {"agent_id": lead["id"], "role": "leader"},
            {
                "agent_id": dev["id"],
                "role": "developer",
                "execution_order": 2,
                "priority": 5,
                "instructions": "Chỉ viết code, không tự deploy.",
                "responsibility": "Viết và chỉnh sửa code",
                "description": "Dev chính",
                "provider_override": "openai",
                "model_override": MODEL_B,
                "system_prompt_override": "Bạn là dev của team này.",
            },
        ],
        lead["id"],
    )
    member = next(m for m in team["members"] if m["agent_id"] == dev["id"])
    assert member["execution_order"] == 2
    assert member["priority"] == 5
    assert member["instructions"] == "Chỉ viết code, không tự deploy."
    assert member["responsibility"] == "Viết và chỉnh sửa code"
    assert member["provider_override"] == "openai"
    assert member["model_override"] == MODEL_B
    # Effective values reported on the member are the override values.
    assert member["provider"] == "openai"
    assert member["model"] == MODEL_B
    # And they survive a fresh read (Test 1: save, reload, verify).
    fresh = client.get(f"{TEAMS}/{team['id']}").json()
    member = next(m for m in fresh["members"] if m["agent_id"] == dev["id"])
    assert member["model"] == MODEL_B
    assert member["execution_order"] == 2


def test_legacy_member_payload_gets_defaults(owner):
    client, *_ = owner
    lead = make_agent(client, "Lead")
    team = create_team(client, [{"agent_id": lead["id"], "role": "coordinator"}], lead["id"])
    member = team["members"][0]
    assert member["execution_order"] is None
    assert member["priority"] == 0
    assert member["provider_override"] is None
    assert member["model_override"] is None
    assert member["model"] == MODEL_A


def test_suggested_and_custom_roles_accepted(owner):
    client, *_ = owner
    lead = make_agent(client, "Lead")
    designer = make_agent(client, "UI Person")
    writer = make_agent(client, "Writer")
    team = create_team(
        client,
        [
            {"agent_id": lead["id"], "role": "leader"},
            {"agent_id": designer["id"], "role": "Designer"},
            {"agent_id": writer["id"], "role": "Content Writer"},
        ],
        lead["id"],
    )
    roles = {m["agent_id"]: m["role"] for m in team["members"]}
    assert roles[lead["id"]] == "leader"
    assert roles[designer["id"]] == "designer"
    # Custom roles are stored as slugs.
    assert roles[writer["id"]] == "content_writer"


def test_invalid_role_rejected(owner):
    client, *_ = owner
    lead = make_agent(client, "Lead")
    r = client.post(
        TEAMS,
        json={
            "name": "Team",
            "coordinator_agent_id": lead["id"],
            "members": [{"agent_id": lead["id"], "role": "boss!!!"}],
        },
    )
    assert r.status_code == 422, r.text


def test_model_override_requires_provider_override(owner):
    client, *_ = owner
    lead = make_agent(client, "Lead")
    dev = make_agent(client, "Dev")
    r = client.post(
        TEAMS,
        json={
            "name": "Team",
            "coordinator_agent_id": lead["id"],
            "members": [
                {"agent_id": lead["id"], "role": "leader"},
                {"agent_id": dev["id"], "role": "developer", "model_override": MODEL_B},
            ],
        },
    )
    assert r.status_code == 422, r.text


def _chat_http():
    def handler(request):
        return httpx.Response(200, text=sse(chunk("Done."), "[DONE]"))

    return ChatHTTP(transport=httpx.MockTransport(handler))


async def test_prepare_run_honours_model_override(owner):
    client, owner_id, db, settings = owner
    agent = make_agent(client, "Dev")
    service = AgentService(db, settings, _chat_http())
    prepared = await service.prepare_run(
        owner_id,
        UUID(agent["id"]),
        RunRequest(prompt="Viết hàm login"),
        provider_override="openai",
        model_override=MODEL_B,
        system_prompt_override="Prompt riêng của team",
    )
    # The run carries the effective (override) configuration...
    assert prepared.agent.model == MODEL_B
    assert prepared.model.model_id == MODEL_B
    assert prepared.agent.system_prompt == "Prompt riêng của team"
    # ...while the stored Agent keeps its own configuration.
    stored = client.get(f"{AGENTS}/{agent['id']}").json()
    assert stored["model"] == MODEL_A
    assert stored["system_prompt"] is None


async def test_prepare_run_without_override_uses_agent_config(owner):
    client, owner_id, db, settings = owner
    agent = make_agent(client, "Dev")
    service = AgentService(db, settings, _chat_http())
    prepared = await service.prepare_run(
        owner_id, UUID(agent["id"]), RunRequest(prompt="Xin chào")
    )
    assert prepared.agent.model == MODEL_A
    assert prepared.model.model_id == MODEL_A
