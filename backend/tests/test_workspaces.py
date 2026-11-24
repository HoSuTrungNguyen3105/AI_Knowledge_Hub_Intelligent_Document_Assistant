"""Offline contracts for Workspace Management v1 (NEXORA Module 02).

Covers: lazy personal workspace, team workspace CRUD, membership by email,
and the role matrix — members read, owner/admin manage, the owner's own
membership row is immutable, and non-members cannot even see a workspace.
"""

from uuid import uuid4

import pytest

BASE = "/api/v1/ai/workspaces"


@pytest.fixture
async def owner(client, register):
    assert register(client, email="Owner@Example.com").status_code == 201
    return client


@pytest.fixture
def second(client_factory, register):
    client = client_factory()
    assert register(client, email="Second@Example.com", name="Second User").status_code == 201
    return client


@pytest.fixture
def third(client_factory, register):
    client = client_factory()
    assert register(client, email="Third@Example.com", name="Third User").status_code == 201
    return client


def make_team(client, name="Nhóm dự án A"):
    response = client.post(BASE, json={"name": name, "description": "Team workspace"})
    assert response.status_code == 201, response.text
    return response.json()


def add_member(client, workspace_id, email="second@example.com", role="employee"):
    return client.post(
        f"{BASE}/{workspace_id}/members", json={"email": email, "role": role}
    )


def test_workspaces_require_auth(client):
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"name": "X"}).status_code == 401


async def test_personal_workspace_is_created_once(owner):
    first = owner.get(BASE).json()["workspaces"]
    assert len(first) == 1
    assert first[0]["kind"] == "personal"
    assert first[0]["my_role"] == "owner"
    assert first[0]["member_count"] == 1

    second = owner.get(BASE).json()["workspaces"]
    assert [w["id"] for w in second] == [w["id"] for w in first]


async def test_create_team_workspace(owner):
    team = make_team(owner)
    assert team["kind"] == "team"
    assert team["my_role"] == "owner"
    listing = owner.get(BASE).json()["workspaces"]
    assert [w["kind"] for w in listing] == ["personal", "team"]


async def test_add_member_by_email_and_member_reads(owner, second):
    team = make_team(owner)
    added = add_member(owner, team["id"])
    assert added.status_code == 201, added.text
    assert added.json()["email"] == "second@example.com"
    assert added.json()["role"] == "employee"

    # The new member sees the workspace with their own role.
    mine = second.get(BASE).json()["workspaces"]
    team_view = [w for w in mine if w["id"] == team["id"]]
    assert len(team_view) == 1
    assert team_view[0]["my_role"] == "employee"
    assert team_view[0]["member_count"] == 2

    members = second.get(f"{BASE}/{team['id']}/members").json()["members"]
    assert [m["role"] for m in members] == ["owner", "employee"]
    assert members[1]["email"] == "second@example.com"


async def test_add_member_errors(owner):
    team = make_team(owner)
    missing = add_member(owner, team["id"], email="ghost@example.com")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "workspace_user_not_found"

    assert add_member(owner, team["id"]).status_code == 201
    duplicate = add_member(owner, team["id"])
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "workspace_member_exists"

    as_owner = add_member(owner, team["id"], email="third@example.com", role="owner")
    assert as_owner.status_code == 422


async def test_role_matrix(owner, second, third):
    team = make_team(owner)
    add_member(owner, team["id"])  # second joins as employee

    # Non-member: the workspace does not exist for them.
    assert third.get(f"{BASE}/{team['id']}").status_code == 404

    # Employee can read but not manage.
    assert second.get(f"{BASE}/{team['id']}").status_code == 200
    forbidden_patch = second.patch(f"{BASE}/{team['id']}", json={"name": "Đổi tên"})
    assert forbidden_patch.status_code == 403
    assert forbidden_patch.json()["detail"]["code"] == "workspace_forbidden"
    assert add_member(second, team["id"], email="third@example.com").status_code == 403
    assert second.delete(f"{BASE}/{team['id']}").status_code == 403

    # Owner manages.
    patched = owner.patch(f"{BASE}/{team['id']}", json={"name": "Nhóm dự án A+"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Nhóm dự án A+"


async def test_member_role_change_and_owner_immutable(owner, second):
    team = make_team(owner)
    member = add_member(owner, team["id"]).json()

    changed = owner.patch(
        f"{BASE}/{team['id']}/members/{member['user_id']}", json={"role": "leader"}
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "leader"

    owner_id = owner.get("/api/v1/auth/me").json()["id"]
    immutable = owner.patch(
        f"{BASE}/{team['id']}/members/{owner_id}", json={"role": "viewer"}
    )
    assert immutable.status_code == 422
    assert immutable.json()["detail"]["code"] == "workspace_owner_immutable"
    assert owner.delete(f"{BASE}/{team['id']}/members/{owner_id}").status_code == 422

    # A random non-member id is a clean 404.
    missing = owner.patch(
        f"{BASE}/{team['id']}/members/{uuid4()}", json={"role": "viewer"}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "workspace_member_not_found"


async def test_remove_member_and_leave(owner, second):
    team = make_team(owner)
    member = add_member(owner, team["id"]).json()

    # The member can leave on their own.
    left = second.delete(f"{BASE}/{team['id']}/members/{member['user_id']}")
    assert left.status_code == 204
    mine = second.get(BASE).json()["workspaces"]
    assert all(w["id"] != team["id"] for w in mine)

    # Re-add, then the owner removes them.
    member = add_member(owner, team["id"]).json()
    removed = owner.delete(f"{BASE}/{team['id']}/members/{member['user_id']}")
    assert removed.status_code == 204
    assert second.get(f"{BASE}/{team['id']}").status_code == 404


async def test_delete_workspace_rules(owner):
    personal = owner.get(BASE).json()["workspaces"][0]
    refused = owner.delete(f"{BASE}/{personal['id']}")
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "workspace_personal_undeletable"

    team = make_team(owner)
    assert owner.delete(f"{BASE}/{team['id']}").status_code == 204
    assert owner.get(f"{BASE}/{team['id']}").status_code == 404
    listing = owner.get(BASE).json()["workspaces"]
    assert [w["kind"] for w in listing] == ["personal"]
