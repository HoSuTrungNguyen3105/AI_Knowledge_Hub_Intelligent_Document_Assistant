"""Project import: upload a brief file and get the project created,
analyzed and a team recommendation drafted in a single request.

Covers POST /api/v1/ai/projects/import with a mocked LLM: the happy
path (.md and .txt), file validation errors, and the graceful
degradation where a failed analysis keeps the created project and
reports analysis_error instead of failing the upload.
"""

from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse
from test_projects import ANALYSIS_JSON

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/projects"
IMPORT = "/api/v1/ai/projects/import"
RESOURCES = "/api/v1/ai/resources"

BRIEF_MD = "# Website bán hàng\nXây dựng website Next.js có thanh toán và dashboard."


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client


@pytest.fixture
def mock_llm(app):
    holder = {"text": ANALYSIS_JSON}

    def handler(_request):
        return httpx.Response(
            200,
            text=sse(
                chunk(holder["text"][:30]), chunk(holder["text"][30:]), "[DONE]"
            ),
        )

    app.dependency_overrides[agent_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(handler)
    )
    return holder


def import_file(client, content=BRIEF_MD, filename="brief.md", **fields):
    data = {"provider": "openai", "model": MODEL_A, "name": "", "tech_stack": ""}
    data.update(fields)
    return client.post(
        IMPORT,
        files={"file": (filename, content.encode(), "application/octet-stream")},
        data=data,
    )


def test_import_md_runs_the_whole_flow(owner, mock_llm):
    response = import_file(owner, tech_stack="Next.js, PostgreSQL")
    assert response.status_code == 201, response.text
    body = response.json()
    # Name derived from the first line of the brief, heading marks off.
    assert body["project"]["name"] == "Website bán hàng"
    assert body["project"]["status"] == "analyzed"
    assert body["project"]["tech_stack"] == ["Next.js", "PostgreSQL"]
    assert body["analysis"] is not None
    assert len(body["analysis"]["tasks"]) == 2
    assert body["allocation"] is not None
    assert body["allocation"]["status"] == "proposed"
    assert body["analysis_error"] is None


def test_import_txt_with_explicit_name_and_roster(owner, mock_llm):
    created = owner.post(RESOURCES, json={
        "type": "human", "name": "Dev React", "role": "Frontend Developer",
        "skills": [{"name": "React", "level": 5}, {"name": "Next.js", "level": 4}],
        "cost_per_hour": 20,
        "human": {"experience_years": 4, "hours_per_week": 40, "current_project_count": 0},
    })
    assert created.status_code == 201
    response = import_file(
        owner,
        content="Làm lại trang bán hàng bằng Next.js.",
        filename="brief.txt",
        name="Dự án trang bán hàng",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["project"]["name"] == "Dự án trang bán hàng"
    assert body["allocation"]["items"][0]["resource_id"] == created.json()["id"]


def test_import_rejects_unsupported_and_empty_files(owner, mock_llm):
    response = import_file(owner, content="not an image", filename="photo.png")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "project_file_unsupported"

    response = import_file(owner, content="   \n  ", filename="empty.md")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "project_file_empty"

    assert owner.get(BASE).json()["projects"] == []


def test_import_keeps_project_when_analysis_fails(owner, mock_llm):
    mock_llm["text"] = "không phải JSON"
    response = import_file(owner)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["analysis"] is None
    assert body["allocation"] is None
    assert body["analysis_error"] == "analysis_invalid_response"
    assert body["project"]["status"] == "draft"
    projects = owner.get(BASE).json()["projects"]
    assert [item["id"] for item in projects] == [body["project"]["id"]]


def test_import_without_credentials_reports_error(client, register, mock_llm):
    assert register(client, email="nocreds@example.com").status_code == 201
    response = import_file(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["analysis"] is None
    assert body["analysis_error"] == "credentials_missing"
