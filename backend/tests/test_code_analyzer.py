"""Code Analyzer contract tests (offline, mongomock).

Covers the read surface of PROJECT_SPEC.md: the public demo seed
(idempotent, dev/demo only), demo visibility for other users, project
detail with the prebuilt diagram, file detail, and owner scoping for
private projects.
"""

from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.code_analyzer import analyzer_http
from app.models.base import utcnow
from app.services.ai.chat import ChatHTTP
from tests.test_compare import MODEL_A, chunk, seed, sse

BASE = "/api/v1/ai/code-analyzer"


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


@pytest.fixture
def owner_id(owner):
    return UUID(owner.get("/api/v1/auth/me").json()["id"])


def _ai_reply(text):
    return sse(
        chunk(text),
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5}},
        "[DONE]",
    )


REPORT_MD = (
    "# Báo cáo phân tích codebase: repo\n\n"
    "## 3. Ánh xạ trang & tính năng → file\n\n"
    "- Khởi động ứng dụng: app/main.py gọi app/service.py, "
    "app/service.py đọc dữ liệu qua app/db.py.\n"
)


def ai_handler(request):
    return httpx.Response(
        200,
        text=_ai_reply(REPORT_MD),
        headers={"content-type": "text/event-stream"},
    )


@pytest.fixture
def mock_ai(app):
    app.dependency_overrides[analyzer_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(ai_handler)
    )


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


def make_zip(files: dict) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def upload(client, data: bytes, name="repo.zip"):
    return client.post(
        f"{BASE}/upload",
        files={"file": (name, data, "application/zip")},
    )


def test_upload_parses_imports_and_skips_junk(owner):
    data = make_zip(
        {
            "repo-main/app/main.py": "from app import service\n",
            "repo-main/app/service.py": "from app.db import connect\n",
            "repo-main/app/db.py": "def connect():\n    return None\n",
            "repo-main/node_modules/junk/index.js": "import x from 'y'\n",
            "repo-main/README.md": "# docs\n",
            "repo-main/logo.png": "not really a png",
            "repo-main/app/test_service.py": "def test_x():\n    pass\n",
        }
    )
    r = upload(owner, data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["analysis_dispatch"] == "static"
    project = body["project"]
    assert project["name"] == "repo"
    assert project["status"] == "COMPLETED"  # no provider -> static pass completes
    assert project["stats"]["analyzed_files"] == 3
    assert project["stats"]["primary_language"] == "python"

    detail = owner.get(f"{BASE}/projects/{project['id']}").json()
    by_path = {f["file_path"]: f for f in detail["files"]}
    assert set(by_path) == {"app/main.py", "app/service.py", "app/db.py"}
    main = by_path["app/main.py"]
    assert main["import_count"] == 1
    service_detail = owner.get(
        f"{BASE}/projects/{project['id']}/files/{by_path['app/service.py']['id']}"
    ).json()
    assert service_detail["imports"][0]["target_file"] == "app/db.py"
    assert service_detail["imports"][0]["target_id"]
    db_detail = owner.get(
        f"{BASE}/projects/{project['id']}/files/{by_path['app/db.py']['id']}"
    ).json()
    assert db_detail["imported_by"] == ["app/service.py"]


def test_upload_rejects_invalid_and_empty(owner):
    r = upload(owner, b"this is not a zip")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "code_upload_invalid"
    junk = make_zip({"node_modules/x/index.js": "code", "a.png": "img"})
    r = upload(owner, junk)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "code_upload_empty"


async def test_upload_runs_direct_ai(owner, mock_ai, db, settings, owner_id):
    await seed(db, settings, owner_id)
    data = make_zip(
        {
            "app/main.py": "from app import service\n",
            "app/service.py": "from app.db import connect\n",
            "app/db.py": "def connect():\n    return None\n",
        }
    )
    r = upload(owner, data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["analysis_dispatch"] == "ai"
    assert body["ai_analyzed"] == 3
    assert body["project"]["status"] == "COMPLETED"
    detail = owner.get(f"{BASE}/projects/{body['project']['id']}").json()
    assert detail["report_markdown"].startswith("# Báo cáo phân tích")
    assert "Ánh xạ trang" in detail["report_markdown"]
    # The report can be regenerated without re-uploading the ZIP.
    r = owner.post(f"{BASE}/projects/{body['project']['id']}/report")
    assert r.status_code == 200, r.text
    assert r.json()["analysis_dispatch"] == "ai"


async def test_upload_explicit_target(owner, mock_ai, db, settings, owner_id):
    await seed(db, settings, owner_id)
    data = make_zip({"app/db.py": "def connect():\n    return None\n"})
    r = owner.post(
        f"{BASE}/upload",
        files={"file": ("repo.zip", data, "application/zip")},
        data={"provider": "openai", "model": MODEL_A},
    )
    assert r.status_code == 201, r.text
    assert r.json()["analysis_dispatch"] == "ai"
    r = owner.post(
        f"{BASE}/upload",
        files={"file": ("repo.zip", data, "application/zip")},
        data={"provider": "openai", "model": "model-khong-co"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "model_not_synced"


def test_callback_applies_ai_results(owner):
    data = make_zip(
        {
            "src/main.py": "from src import db\n",
            "src/db.py": "def connect():\n    return None\n",
        }
    )
    project = upload(owner, data).json()["project"]
    detail = owner.get(f"{BASE}/projects/{project['id']}").json()
    main_file = {f["file_path"]: f for f in detail["files"]}["src/main.py"]

    r = owner.post(
        f"{BASE}/webhook/callback",
        json={
            "project_id": project["id"],
            "status": "completed",
            "files": [
                {
                    "file_id": main_file["id"],
                    "file_path": "src/main.py",
                    "ai_summary": "Điểm khởi động, mở kết nối DB.",
                    "role_tag": "Entry Point",
                    "imports": [
                        {
                            "target_file": "src/db.py",
                            "relation_label": "Mở kết nối khi khởi động",
                        }
                    ],
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"received": True, "updated": 1}
    fd = owner.get(
        f"{BASE}/projects/{project['id']}/files/{main_file['id']}"
    ).json()
    assert fd["ai_summary"] == "Điểm khởi động, mở kết nối DB."
    assert fd["imports"][0]["relation_label"] == "Mở kết nối khi khởi động"


def test_callback_requires_secret_when_configured(owner, settings):
    settings.n8n_code_analyzer_webhook_secret = "topsecret"
    data = make_zip({"src/a.py": "import os\n"})
    project = upload(owner, data).json()["project"]
    payload = {"project_id": project["id"], "status": "completed", "files": []}
    r = owner.post(f"{BASE}/webhook/callback", json=payload)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "code_callback_unauthorized"
    r = owner.post(
        f"{BASE}/webhook/callback",
        json=payload,
        headers={"x-mindflow-secret": "topsecret"},
    )
    assert r.status_code == 200
