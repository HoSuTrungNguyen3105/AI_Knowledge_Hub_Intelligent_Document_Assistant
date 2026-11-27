"""Role catalog behind the Chức danh (roles) page.

Pins the catalog contract: the built-in system roles are always listed
first and cannot be changed or deleted; a user's own roles are created
with a slug derived from the display name (the same normalisation team
members use), duplicates and system-name collisions are rejected, a
rename never changes the slug (teams keep pointing at the role), and
deleting a custom role simply removes it from the catalog.
"""

import pytest

ROLES = "/api/v1/ai/roles"


@pytest.fixture
async def owner(client, register):
    assert register(client).status_code == 201
    return client


def test_list_starts_with_system_roles(owner):
    r = owner.get(ROLES)
    assert r.status_code == 200, r.text
    roles = r.json()["roles"]
    slugs = [role["slug"] for role in roles]
    assert slugs[:3] == ["leader", "coordinator", "planner"]
    assert "developer" in slugs and "tester" in slugs and "member" in slugs
    assert all(role["is_system"] for role in roles)


def test_create_custom_role_normalises_slug(owner):
    r = owner.post(ROLES, json={"name": "Content Writer", "description": "Viết nội dung"})
    assert r.status_code == 201, r.text
    role = r.json()
    assert role["slug"] == "content_writer"
    assert role["name"] == "Content Writer"
    assert role["description"] == "Viết nội dung"
    assert role["is_system"] is False
    listed = owner.get(ROLES).json()["roles"]
    assert listed[-1]["slug"] == "content_writer"


def test_create_duplicate_or_system_name_rejected(owner):
    assert owner.post(ROLES, json={"name": "Data Analyst"}).status_code == 201
    r = owner.post(ROLES, json={"name": "Data Analyst"})
    assert r.status_code == 409, r.text
    r = owner.post(ROLES, json={"name": "Leader"})
    assert r.status_code == 409, r.text


def test_patch_custom_role_keeps_slug(owner):
    assert owner.post(ROLES, json={"name": "Data Analyst"}).status_code == 201
    r = owner.patch(
        f"{ROLES}/data_analyst",
        json={"name": "Chuyên viên dữ liệu", "description": "Phân tích số liệu"},
    )
    assert r.status_code == 200, r.text
    role = r.json()
    assert role["slug"] == "data_analyst"
    assert role["name"] == "Chuyên viên dữ liệu"
    assert role["description"] == "Phân tích số liệu"


def test_patch_system_or_missing_role_rejected(owner):
    r = owner.patch(f"{ROLES}/leader", json={"description": "x"})
    assert r.status_code == 409, r.text
    r = owner.patch(f"{ROLES}/khong_ton_tai", json={"description": "x"})
    assert r.status_code == 404, r.text


def test_delete_custom_role(owner):
    assert owner.post(ROLES, json={"name": "Data Analyst"}).status_code == 201
    r = owner.delete(f"{ROLES}/data_analyst")
    assert r.status_code == 204, r.text
    slugs = [role["slug"] for role in owner.get(ROLES).json()["roles"]]
    assert "data_analyst" not in slugs
    r = owner.delete(f"{ROLES}/tester")
    assert r.status_code == 409, r.text
    r = owner.delete(f"{ROLES}/khong_ton_tai")
    assert r.status_code == 404, r.text
