"""Code Analyzer contract tests (offline, mongomock).

Covers the read surface of PROJECT_SPEC.md: the public demo seed
(idempotent, dev/demo only), demo visibility for other users, project
detail with the prebuilt diagram, file detail, and owner scoping for
private projects.
"""

from uuid import uuid4

import pytest

from app.models.base import utcnow

BASE = "/api/v1/ai/code-analyzer"


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


def seed_demo(client):
    r = client.post(f"{BASE}/seed-demo")
    assert r.status_code == 200, r.text
    return r.json()


def test_seed_demo_creates_public_project(owner):
    body = seed_demo(owner)
    assert body["created"] is True
    project = body["project"]
    assert project["is_public_demo"] is True
    assert project["status"] == "COMPLETED"
    assert project["stats"]["analyzed_files"] == 12

    detail = owner.get(f"{BASE}/projects/{project['id']}")
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["diagram_data"]["mode"] == "files"
    assert len(data["diagram_data"]["nodes"]) == 12
    assert data["diagram_data"]["edges"]
    assert len(data["files"]) == 12
    by_path = {f["file_path"]: f for f in data["files"]}
    controller = by_path["src/controllers/taskController.js"]
    assert controller["import_count"] == 2
    assert controller["role_tag"] == "Controller"
    model = by_path["src/models/Task.js"]
    assert model["imported_by_count"] == 1

    file_detail = owner.get(
        f"{BASE}/projects/{project['id']}/files/{controller['id']}"
    )
    assert file_detail.status_code == 200, file_detail.text
    fd = file_detail.json()
    assert "taskService" in fd["ai_summary"] or fd["ai_summary"]
    targets = {i["target_file"] for i in fd["imports"]}
    assert "src/services/taskService.js" in targets
    assert all(i["target_id"] for i in fd["imports"])


def test_seed_demo_is_idempotent(owner):
    first = seed_demo(owner)
    second = seed_demo(owner)
    assert second["created"] is False
    assert second["project"]["id"] == first["project"]["id"]
    listed = owner.get(f"{BASE}/projects").json()["projects"]
    demos = [p for p in listed if p["is_public_demo"]]
    assert len(demos) == 1


def test_demo_visible_to_other_users(owner, client_factory, register):
    project = seed_demo(owner)["project"]
    other = client_factory()
    assert register(
        other, email="Second@Example.com", name="Second User"
    ).status_code == 201
    listed = other.get(f"{BASE}/projects").json()["projects"]
    assert [p["id"] for p in listed] == [project["id"]]
    assert other.get(f"{BASE}/projects/{project['id']}").status_code == 200


def test_seed_demo_blocked_in_production(owner, settings):
    settings.app_env = "production"
    r = owner.post(f"{BASE}/seed-demo")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "seed_disabled"


async def test_private_project_is_owner_scoped(owner, client_factory, register, db):
    me = owner.get("/api/v1/auth/me").json()
    project_id = uuid4()
    now = utcnow()
    await db.code_projects.insert_one(
        {
            "_id": project_id,
            "user_id": me["id"],
            "name": "Private Repo",
            "description": "",
            "is_public_demo": False,
            "status": "COMPLETED",
            "stats": {},
            "diagram_data": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    assert owner.get(f"{BASE}/projects/{project_id}").status_code == 200
    other = client_factory()
    assert register(
        other, email="Third@Example.com", name="Third User"
    ).status_code == 201
    listed = other.get(f"{BASE}/projects").json()["projects"]
    assert listed == []
    r = other.get(f"{BASE}/projects/{project_id}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "code_project_not_found"
    missing = owner.get(f"{BASE}/projects/{uuid4()}")
    assert missing.status_code == 404
    file_missing = owner.get(f"{BASE}/projects/{project_id}/files/{uuid4()}")
    assert file_missing.status_code == 404
    assert file_missing.json()["detail"]["code"] == "code_file_not_found"


def test_list_requires_auth(client_factory):
    anon = client_factory()
    assert anon.get(f"{BASE}/projects").status_code == 401
