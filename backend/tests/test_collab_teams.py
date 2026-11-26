"""Collaboration rooms created from Agent Teams (wave 3).

Pins the team -> room bridge: creating a room with team_id freezes a
configuration snapshot (roles, execution order, effective provider/
model incl. overrides), the moderator is the team's coordinator,
disabled members are excluded, a team without an active leader is
rejected with a clear error, mentions run the member's OVERRIDE model
(visible on the stored reply), and editing the team afterwards does
not rewrite the existing room.
"""

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
TEAMS = "/api/v1/ai/agent-teams"


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


def make_team(client, members, coordinator_id, name="Team chạy việc"):
    r = client.post(
        TEAMS,
        json={"name": name, "coordinator_agent_id": coordinator_id, "members": members},
    )
    assert r.status_code == 201, r.text
    return r.json()


def standard_team(client):
    lead = make_agent(client, "Lead")
    dev = make_agent(client, "Dev")
    reviewer = make_agent(client, "Reviewer")
    team = make_team(
        client,
        [
            {"agent_id": lead["id"], "role": "leader"},
            {
                "agent_id": dev["id"],
                "role": "developer",
                "execution_order": 1,
                "instructions": "Chỉ viết code.",
                "provider_override": "openai",
                "model_override": MODEL_B,
            },
            {"agent_id": reviewer["id"], "role": "reviewer", "execution_order": 2},
        ],
        lead["id"],
    )
    return team, lead, dev, reviewer


def test_room_from_team_snapshots_config(owner, mock_agent):
    client = owner
    team, lead, dev, reviewer = standard_team(client)
    r = client.post(ROOMS, json={"title": "Phòng theo nhóm", "team_id": team["id"]})
    assert r.status_code == 201, r.text
    room = r.json()
    assert room["team_id"] == team["id"]
    assert room["moderator_agent_id"] == lead["id"]
    assert set(room["agent_ids"]) == {lead["id"], dev["id"], reviewer["id"]}
    snapshot = room["team_snapshot"]
    assert snapshot["team_name"] == "Team chạy việc"
    by_id = {m["agent_id"]: m for m in snapshot["members"]}
    assert by_id[dev["id"]]["role"] == "developer"
    assert by_id[dev["id"]]["execution_order"] == 1
    assert by_id[dev["id"]]["instructions"] == "Chỉ viết code."
    # Effective model in the snapshot is the team override.
    assert by_id[dev["id"]]["model"] == MODEL_B
    assert by_id[dev["id"]]["model_override"] == MODEL_B
    assert by_id[lead["id"]]["model"] == MODEL_A
    agents = {a["id"]: a for a in room["agents"]}
    assert agents[dev["id"]]["role"] == "developer"
    assert agents[dev["id"]]["model"] == MODEL_B


def test_team_edit_after_room_creation_does_not_rewrite_room(owner, mock_agent):
    client = owner
    team, lead, dev, reviewer = standard_team(client)
    room = client.post(ROOMS, json={"title": "Phòng", "team_id": team["id"]}).json()
    # Change the assignment: remove the override and swap roles.
    r = client.patch(
        f"{TEAMS}/{team['id']}",
        json={
            "members": [
                {"agent_id": lead["id"], "role": "leader"},
                {"agent_id": dev["id"], "role": "developer"},
                {"agent_id": reviewer["id"], "role": "tester"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    fresh = client.get(f"{ROOMS}/{room['id']}").json()
    by_id = {m["agent_id"]: m for m in fresh["team_snapshot"]["members"]}
    assert by_id[dev["id"]]["model"] == MODEL_B  # snapshot unchanged
    assert by_id[reviewer["id"]]["role"] == "reviewer"


def test_mention_runs_override_model(owner, mock_agent):
    client = owner
    team, lead, dev, reviewer = standard_team(client)
    room = client.post(ROOMS, json={"title": "Phòng", "team_id": team["id"]}).json()
    r = client.post(
        f"{ROOMS}/{room['id']}/messages",
        json={"content": "@Dev viết hàm login", "mention_agent_ids": [dev["id"]]},
    )
    assert r.status_code == 201, r.text
    replies = [m for m in r.json()["messages"] if m["sender_type"] == "agent"]
    assert len(replies) == 1
    # The stored reply records the model that actually ran: the override.
    assert replies[0]["model"] == MODEL_B
    assert replies[0]["provider"] == "openai"


def test_room_from_team_without_active_leader_rejected(owner, mock_agent):
    client = owner
    lead = make_agent(client, "Lead")
    dev = make_agent(client, "Dev")
    team = make_team(
        client,
        [
            {"agent_id": lead["id"], "role": "leader", "enabled": False},
            {"agent_id": dev["id"], "role": "developer"},
        ],
        lead["id"],
    )
    r = client.post(ROOMS, json={"title": "Phòng", "team_id": team["id"]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "collab_team_no_leader"


def test_room_from_missing_team_404(owner, mock_agent):
    client = owner
    r = client.post(ROOMS, json={"title": "Phòng", "team_id": str(uuid4())})
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "team_not_found"


def test_disabled_member_excluded_from_room(owner, mock_agent):
    client = owner
    lead = make_agent(client, "Lead")
    dev = make_agent(client, "Dev")
    ghost = make_agent(client, "Ghost")
    team = make_team(
        client,
        [
            {"agent_id": lead["id"], "role": "leader"},
            {"agent_id": dev["id"], "role": "developer"},
            {"agent_id": ghost["id"], "role": "tester", "enabled": False},
        ],
        lead["id"],
    )
    room = client.post(ROOMS, json={"title": "Phòng", "team_id": team["id"]}).json()
    assert ghost["id"] not in room["agent_ids"]
    assert set(room["agent_ids"]) == {lead["id"], dev["id"]}
