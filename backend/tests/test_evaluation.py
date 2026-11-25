"""Evaluation Center contract tests over the offline MongoDB mock.

Provider traffic is intercepted with httpx.MockTransport. The handler answers
from the last user message: known questions get known answers, judge prompts
get a JSON verdict, and a module-level switch flips one answer so regression
comparison has something real to detect.
"""

import json
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.evaluations import eval_http
from app.models.base import utcnow
from app.services.ai.chat import ChatHTTP
from tests.test_compare import MODEL_A, chunk, seed, sse

BASE = "/api/v1/ai/evaluations"
STATE = {"capital": "Paris"}


def _reply(text):
    return sse(
        chunk(text),
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5}},
        "[DONE]",
    )


def handler(request):
    payload = json.loads(request.content)
    content = payload["messages"][-1]["content"]
    if "giám khảo" in content:
        return httpx.Response(200, text=_reply('{"score": 0.9, "reason": "Đạt"}'))
    if "Capital of France" in content:
        return httpx.Response(200, text=_reply(STATE["capital"]))
    if "Say hello" in content:
        return httpx.Response(200, text=_reply("Hello world"))
    return httpx.Response(200, text=_reply("4"))


@pytest.fixture(autouse=True)
def eval_settings(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


@pytest.fixture(autouse=True)
def mock_eval(app):
    app.dependency_overrides[eval_http] = lambda: ChatHTTP(
        transport=httpx.MockTransport(handler)
    )


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def owner_id(owner):
    from uuid import UUID

    return UUID(owner.get("/api/v1/auth/me").json()["id"])


@pytest.fixture
async def seeded(db, settings, owner_id):
    await seed(db, settings, owner_id)
    return owner_id


def make_dataset(client, cases=None, name="Bộ kiểm thử cơ bản"):
    payload = {
        "name": name,
        "category": "qa",
        "cases": cases
        or [
            {
                "input": "Capital of France?",
                "expected_output": "Paris",
                "criteria": [{"type": "exact"}],
            },
            {
                "input": "Say hello",
                "criteria": [{"type": "contains", "value": "Hello"}],
            },
        ],
    }
    response = client.post(f"{BASE}/datasets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_dataset_crud_and_versioning(owner):
    dataset = make_dataset(owner)
    assert dataset["version"] == 1
    assert dataset["case_count"] == 2
    assert all(case["id"] for case in dataset["cases"])

    renamed = owner.patch(
        f"{BASE}/datasets/{dataset['id']}", json={"name": "Tên mới"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["version"] == 1

    replaced = owner.patch(
        f"{BASE}/datasets/{dataset['id']}",
        json={"cases": [{"input": "2 + 2 = ?", "expected_output": "4"}]},
    )
    assert replaced.status_code == 200
    assert replaced.json()["version"] == 2
    assert replaced.json()["case_count"] == 1

    exported = owner.get(f"{BASE}/datasets/{dataset['id']}/export")
    assert exported.status_code == 200
    parsed = json.loads(exported.json()["content"])
    assert parsed["name"] == "Tên mới"
    assert len(parsed["cases"]) == 1

    assert owner.delete(f"{BASE}/datasets/{dataset['id']}").status_code == 204
    missing = owner.get(f"{BASE}/datasets/{dataset['id']}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "eval_dataset_not_found"


def test_dataset_import_json_and_csv(owner):
    imported = owner.post(
        f"{BASE}/datasets/import",
        json={
            "format": "json",
            "name": "Nhập JSON",
            "content": json.dumps(
                [{"input": "2 + 2 = ?", "expected_output": "4"}, {"input": "Say hello"}]
            ),
        },
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["case_count"] == 2

    csv_body = "input,expected_output,tags\nCapital of France?,Paris,geo;eu\nSay hello,,"
    imported_csv = owner.post(
        f"{BASE}/datasets/import",
        json={"format": "csv", "name": "Nhập CSV", "content": csv_body},
    )
    assert imported_csv.status_code == 201, imported_csv.text
    cases = imported_csv.json()["cases"]
    assert cases[0]["tags"] == ["geo", "eu"]

    bad = owner.post(
        f"{BASE}/datasets/import",
        json={"format": "json", "content": "[{\"nope\": 1}]"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "eval_import_invalid"


async def test_model_run_scoring_judge_and_overview(owner, seeded):
    dataset = make_dataset(owner)
    response = owner.post(
        f"{BASE}/runs",
        json={
            "dataset_id": dataset["id"],
            "targets": [{"provider": "openai", "model": MODEL_A}],
            "judge": {"provider": "openai", "model": MODEL_A},
        },
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["progress_done"] == 2 and run["progress_total"] == 2
    summary = run["summaries"][0]
    assert summary["pass_rate"] == 1.0
    assert summary["accuracy"] == 1.0
    assert summary["errors"] == 0
    assert all(r["judge_score"] == 0.9 for r in run["results"])
    assert all(r["input_tokens"] == 11 for r in run["results"])

    fetched = owner.get(f"{BASE}/runs/{run['id']}")
    assert fetched.status_code == 200
    assert len(fetched.json()["results"]) == 2

    overview = owner.get(f"{BASE}/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["total_evaluations"] == 1
    assert body["total_models_tested"] == 1
    assert body["total_datasets"] == 1
    assert body["pass_rate"] == 1.0
    assert len(body["series"]) == 1


async def test_regression_compare_detects_flip(owner, seeded):
    dataset = make_dataset(owner)
    payload = {
        "dataset_id": dataset["id"],
        "targets": [{"provider": "openai", "model": MODEL_A}],
    }
    first = owner.post(f"{BASE}/runs", json=payload)
    assert first.status_code == 201
    baseline_id = first.json()["id"]
    marked = owner.post(f"{BASE}/runs/{baseline_id}/baseline")
    assert marked.status_code == 200
    assert marked.json()["is_baseline"] is True

    STATE["capital"] = "London"
    try:
        second = owner.post(f"{BASE}/runs", json=payload)
        assert second.status_code == 201
        current_id = second.json()["id"]
    finally:
        STATE["capital"] = "Paris"

    compared = owner.get(
        f"{BASE}/runs/compare",
        params={"baseline_id": baseline_id, "current_id": current_id},
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert body["regression_detected"] is True
    assert body["pass_rate_delta"] == -0.5
    regressed = [a for a in body["affected_cases"] if a["change"] == "regressed"]
    assert len(regressed) == 1
    assert regressed[0]["case_index"] == 0


async def test_prompt_versions_and_prompt_run(owner, seeded):
    invalid = owner.post(
        f"{BASE}/prompts",
        json={"name": "Thiếu placeholder", "template": "Trả lời câu hỏi"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "eval_prompt_template_invalid"

    created = owner.post(
        f"{BASE}/prompts",
        json={"name": "Trả lời ngắn", "template": "Trả lời ngắn gọn: {input}"},
    )
    assert created.status_code == 201, created.text
    prompt_id = created.json()["id"]
    assert len(created.json()["versions"]) == 1

    updated = owner.patch(
        f"{BASE}/prompts/{prompt_id}",
        json={"template": "Chỉ trả lời đáp án: {input}"},
    )
    assert updated.status_code == 200
    assert len(updated.json()["versions"]) == 2

    dataset = make_dataset(owner)
    run = owner.post(
        f"{BASE}/runs",
        json={
            "dataset_id": dataset["id"],
            "kind": "prompt",
            "prompt_id": prompt_id,
            "targets": [{"provider": "openai", "model": MODEL_A}],
        },
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["kind"] == "prompt"
    assert body["prompt_version"] == 2
    assert body["status"] == "completed"
    assert body["summaries"][0]["pass_rate"] == 1.0


async def test_run_validation_and_owner_scope(owner, client, register, seeded):
    empty = make_dataset(owner, cases=[], name="Bộ rỗng")
    no_cases = owner.post(
        f"{BASE}/runs",
        json={
            "dataset_id": empty["id"],
            "targets": [{"provider": "openai", "model": MODEL_A}],
        },
    )
    assert no_cases.status_code == 422
    assert no_cases.json()["detail"]["code"] == "eval_no_cases"

    dataset = make_dataset(owner)
    no_targets = owner.post(f"{BASE}/runs", json={"dataset_id": dataset["id"]})
    assert no_targets.status_code == 422
    assert no_targets.json()["detail"]["code"] == "eval_no_targets"

    run = owner.post(
        f"{BASE}/runs",
        json={
            "dataset_id": dataset["id"],
            "targets": [{"provider": "openai", "model": MODEL_A}],
        },
    )
    assert run.status_code == 201
    run_id = run.json()["id"]

    cancelled = owner.post(f"{BASE}/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "completed"

    assert register(client, email="eval-other@example.com").status_code == 201
    assert client.get(f"{BASE}/datasets/{dataset['id']}").status_code == 404
    assert client.get(f"{BASE}/runs/{run_id}").status_code == 404


async def test_cancel_marks_running_run(owner, db, owner_id):
    run_id = uuid4()
    dataset_id = uuid4()
    now = utcnow()
    await db.eval_runs.insert_one(
        {
            "_id": run_id,
            "user_id": owner_id,
            "name": "Run đang chạy",
            "kind": "model",
            "dataset_id": dataset_id,
            "dataset_name": "DS",
            "dataset_version": 1,
            "targets": [{"provider": "openai", "model": MODEL_A}],
            "prompt_id": None,
            "prompt_name": "",
            "prompt_version": None,
            "judge": None,
            "status": "running",
            "progress_done": 0,
            "progress_total": 2,
            "results": [],
            "summaries": [],
            "is_baseline": False,
            "regression_detected": False,
            "cancel_requested": False,
            "error_code": None,
            "created_at": now,
            "finished_at": None,
        }
    )
    response = owner.post(f"{BASE}/runs/{run_id}/cancel")
    assert response.status_code == 200
    doc = await db.eval_runs.find_one({"_id": run_id})
    assert doc["cancel_requested"] is True
