"""Offline contracts for workforce projects + Project Analysis AI
(mindflow-workforce-feature sections 2 + 9, wave 3).

Covers project CRUD and owner isolation, plus the analyze pass against a
mocked provider: the model's JSON is reassembled from streamed chunks,
validated, stored as an analysis, and moves the project to "analyzed";
an unreadable answer fails with analysis_invalid_response and stores
nothing.
"""

import json
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import MODEL_A, chunk, seed, sse

from app.api.v1.agents import agent_http
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/projects"

ANALYSIS_JSON = json.dumps(
    {
        "summary": "Website thương mại điện tử gồm storefront và trang quản trị.",
        "tasks": [
            {
                "title": "Xây dựng giao diện storefront",
                "description": "Trang chủ, danh mục, chi tiết sản phẩm",
                "skills_required": ["Next.js", "React"],
                "scopes": [],
                "estimated_hours": 16,
                "suggested_type": "either",
            },
            {
                "title": "Tích hợp thanh toán",
                "description": "Cổng thanh toán và xử lý đơn hàng",
                "skills_required": ["Node.js", "PostgreSQL"],
                "scopes": ["payment-data"],
                "estimated_hours": 12,
                "suggested_type": "human",
            },
        ],
        "risks": ["Rủi ro bảo mật thanh toán"],
    },
    ensure_ascii=False,
)


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
def second(client_factory, register):
    client = client_factory()
    assert register(client, email="Second@Example.com", name="Second User").status_code == 201
    return client


@pytest.fixture
def mock_llm(app):
    holder = {"text": ANALYSIS_JSON}

    def handler(_request):
        text = holder["text"]
        return httpx.Response(
            200, text=sse(chunk(text[:25]), chunk(text[25:]), "[DONE]")
        )

    app.dependency_overrides[agent_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(handler)
    )
    return holder


def create_project(client, **overrides):
    payload = {
        "name": "Website thương mại điện tử",
        "description": (
            "Xây dựng website bán hàng bằng Next.js, có quản lý sản phẩm, "
            "thanh toán, đơn hàng và dashboard quản trị."
        ),
        "tech_stack": ["Next.js", "PostgreSQL"],
        "deadline": "2026-12-31",
    }
    payload.update(overrides)
    response = client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_project_crud(owner):
    created = create_project(owner)
    assert created["status"] == "draft"
    assert created["deadline"] == "2026-12-31"
    assert created["tech_stack"] == ["Next.js", "PostgreSQL"]

    fetched = owner.get(f"{BASE}/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == created["name"]

    patched = owner.patch(
        f"{BASE}/{created['id']}", json={"name": "Website TMĐT v2", "status": "in_progress"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Website TMĐT v2"
    assert patched.json()["status"] == "in_progress"

    listed = owner.get(BASE).json()["projects"]
    assert [p["id"] for p in listed] == [created["id"]]


def test_project_validation(owner):
    response = owner.post(BASE, json={"name": "X", "description": "  "})
    assert response.status_code == 422
    created = create_project(owner)
    response = owner.patch(f"{BASE}/{created['id']}", json={"status": "flying"})
    assert response.status_code == 422


def test_project_owner_isolation(owner, second):
    created = create_project(owner)
    assert second.get(BASE).json()["projects"] == []
    assert second.get(f"{BASE}/{created['id']}").status_code == 404
    assert second.patch(f"{BASE}/{created['id']}", json={"name": "X"}).status_code == 404
    assert second.delete(f"{BASE}/{created['id']}").status_code == 404
    response = second.post(
        f"{BASE}/{created['id']}/analyze", json={"provider": "openai", "model": MODEL_A}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "project_not_found"


def test_analyze_happy_path(owner, mock_llm):
    created = create_project(owner)
    response = owner.post(
        f"{BASE}/{created['id']}/analyze", json={"provider": "openai", "model": MODEL_A}
    )
    assert response.status_code == 200, response.text
    analysis = response.json()
    assert analysis["project_id"] == created["id"]
    assert len(analysis["tasks"]) == 2
    assert analysis["tasks"][1]["scopes"] == ["payment-data"]
    assert analysis["tasks"][1]["suggested_type"] == "human"
    assert analysis["total_estimated_hours"] == 28

    project = owner.get(f"{BASE}/{created['id']}").json()
    assert project["status"] == "analyzed"

    analyses = owner.get(f"{BASE}/{created['id']}/analyses").json()["analyses"]
    assert len(analyses) == 1
    assert analyses[0]["id"] == analysis["id"]


def test_analyze_invalid_response_stores_nothing(owner, mock_llm):
    mock_llm["text"] = "Xin lỗi, tôi không thể phân tích dự án này."
    created = create_project(owner)
    response = owner.post(
        f"{BASE}/{created['id']}/analyze", json={"provider": "openai", "model": MODEL_A}
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "analysis_invalid_response"
    assert owner.get(f"{BASE}/{created['id']}").json()["status"] == "draft"
    assert owner.get(f"{BASE}/{created['id']}/analyses").json()["analyses"] == []


def test_analyze_missing_credentials(owner):
    created = create_project(owner)
    response = owner.post(
        f"{BASE}/{created['id']}/analyze", json={"provider": "groq", "model": "any"}
    )
    assert response.json()["detail"]["code"] == "credentials_missing"


def test_delete_project_cascades_analyses(owner, mock_llm):
    created = create_project(owner)
    response = owner.post(
        f"{BASE}/{created['id']}/analyze", json={"provider": "openai", "model": MODEL_A}
    )
    assert response.status_code == 200
    assert owner.delete(f"{BASE}/{created['id']}").status_code == 204
    assert owner.get(f"{BASE}/{created['id']}").status_code == 404
    assert owner.get(f"{BASE}/{created['id']}/analyses").status_code == 404
