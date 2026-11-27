"""Studio Projects: persistent source trees edited by Agents in place.

Covers the project/file CRUD contract, ZIP import hygiene (junk
directories and binaries skipped, traversal refused), the size limits,
owner scoping, and the coordination run: an Agent's JSON edit set is
applied to the stored files before the run returns, a malformed Agent
reply fails only its own step, and every applied change lands in the
audit log with the Agent's name.
"""

import io
import json
import zipfile
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, MODEL_B, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

PROJECTS = "/api/v1/ai/studio-projects"
AGENTS = "/api/v1/ai/agents"


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


def make_project(client, files=None, name="Project thử"):
    r = client.post(
        PROJECTS,
        json={"name": name, "files": files or []},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_project_and_file_crud(owner):
    project = make_project(
        owner,
        files=[
            {"path": "src/hello.txt", "content": "Xin chào"},
            {"path": "README.md", "content": "# Demo"},
        ],
    )
    assert project["file_count"] == 2
    assert project["total_bytes"] > 0

    r = owner.get(f"{PROJECTS}/{project['id']}/files")
    assert r.status_code == 200
    assert [f["path"] for f in r.json()["files"]] == ["README.md", "src/hello.txt"]

    r = owner.get(f"{PROJECTS}/{project['id']}/file", params={"path": "src/hello.txt"})
    assert r.status_code == 200
    assert r.json()["content"] == "Xin chào"

    r = owner.put(
        f"{PROJECTS}/{project['id']}/file",
        params={"path": "src/hello.txt"},
        json={"content": "Đã sửa"},
    )
    assert r.status_code == 200
    assert r.json()["content"] == "Đã sửa"

    r = owner.put(
        f"{PROJECTS}/{project['id']}/file",
        params={"path": "src/new.py"},
        json={"content": "print('hi')"},
    )
    assert r.status_code == 200

    r = owner.delete(
        f"{PROJECTS}/{project['id']}/file", params={"path": "README.md"}
    )
    assert r.status_code == 204
    r = owner.get(f"{PROJECTS}/{project['id']}")
    assert r.json()["file_count"] == 2

    r = owner.get(f"{PROJECTS}/{project['id']}/export.zip")
    assert r.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(archive.namelist()) == ["src/hello.txt", "src/new.py"]
    assert archive.read("src/hello.txt").decode() == "Đã sửa"

    r = owner.get(f"{PROJECTS}/{project['id']}/changes")
    actions = {(c["path"], c["action"], c["source"]) for c in r.json()["changes"]}
    assert ("src/hello.txt", "updated", "user") in actions
    assert ("README.md", "deleted", "user") in actions


def test_project_rejects_traversal_and_oversize(owner):
    r = owner.post(
        PROJECTS,
        json={
            "name": "Xấu",
            "files": [{"path": "../evil.txt", "content": "x"}],
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "studio_invalid_path"

    big = "a" * 900_000
    r = owner.post(
        PROJECTS,
        json={
            "name": "To",
            "files": [{"path": f"f{i}.txt", "content": big} for i in range(6)],
        },
    )
    assert r.status_code == 413, r.text
    assert r.json()["detail"]["code"] == "studio_project_too_large"


def test_import_zip_skips_junk_and_binaries(owner):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("src/app.py", "print('app')")
        archive.writestr("node_modules/lib/index.js", "module.exports = 1")
        archive.writestr(".git/config", "[core]")
        archive.writestr("logo.png", b"\x89PNG\r\n\x1a\n\x00\xff")
    r = owner.post(
        f"{PROJECTS}/import-zip",
        files={"file": ("demo.zip", buffer.getvalue(), "application/zip")},
        data={"name": "Project nhập"},
    )
    assert r.status_code == 201, r.text
    project = r.json()
    assert project["name"] == "Project nhập"
    r = owner.get(f"{PROJECTS}/{project['id']}/files")
    assert [f["path"] for f in r.json()["files"]] == ["src/app.py"]


def test_project_is_owner_scoped(owner, client_factory, register):
    project = make_project(owner)
    other = client_factory()
    assert register(other, email="Other@Example.com").status_code == 201
    r = other.get(f"{PROJECTS}/{project['id']}")
    assert r.status_code == 404


def test_run_applies_agent_edits_in_order(owner, mock_agent):
    project = make_project(
        owner, files=[{"path": "src/hello.txt", "content": "bản cũ"}]
    )
    agent = make_agent(owner, "Dev Một")
    edit_set = json.dumps(
        {
            "summary": "Đã viết lại hello.txt",
            "files": [
                {
                    "path": "src/hello.txt",
                    "action": "upsert",
                    "content": "bản mới từ Agent",
                },
                {
                    "path": "src/extra.txt",
                    "action": "upsert",
                    "content": "file thêm",
                },
            ],
        }
    )
    mock_agent(
        lambda _: httpx.Response(
            200, text=sse(chunk(f"```json\n{edit_set}\n```"), "[DONE]")
        )
    )
    r = owner.post(
        f"{PROJECTS}/{project['id']}/runs",
        json={"agent_ids": [agent["id"]], "instruction": "Sửa hello.txt giúp tôi"},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "completed"
    assert len(run["steps"]) == 1
    step = run["steps"][0]
    assert step["status"] == "completed"
    assert sorted(step["files_changed"]) == ["src/extra.txt", "src/hello.txt"]

    r = owner.get(
        f"{PROJECTS}/{project['id']}/file", params={"path": "src/hello.txt"}
    )
    assert r.json()["content"] == "bản mới từ Agent"

    r = owner.get(f"{PROJECTS}/{project['id']}/changes")
    agent_changes = [c for c in r.json()["changes"] if c["source"] == "agent"]
    assert {c["path"] for c in agent_changes} == {"src/extra.txt", "src/hello.txt"}
    assert all(c["agent_name"] == "Dev Một" for c in agent_changes)


def test_run_with_unparseable_reply_fails_only_the_step(owner, mock_agent):
    project = make_project(
        owner, files=[{"path": "a.txt", "content": "nguyên bản"}]
    )
    agent = make_agent(owner, "Dev Hai")
    mock_agent(
        lambda _: httpx.Response(200, text=sse(chunk("Tôi không trả JSON."), "[DONE]"))
    )
    r = owner.post(
        f"{PROJECTS}/{project['id']}/runs",
        json={"agent_ids": [agent["id"]], "instruction": "Sửa a.txt"},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "completed"
    step = run["steps"][0]
    assert step["status"] == "failed"
    assert step["error_code"] == "studio_invalid_agent_output"

    r = owner.get(f"{PROJECTS}/{project['id']}/file", params={"path": "a.txt"})
    assert r.json()["content"] == "nguyên bản"
