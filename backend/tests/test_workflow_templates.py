"""Offline contracts for the Workflow Template Library importer (phase 1).

The GitHub reader is replaced with a fake: no network, no real GitHub.
These tests verify the import contract — real JSON files are analysed,
security-scanned and upserted idempotently — not a live GitHub run.
"""

import json

import pytest

from app.api.v1.workflow_templates import github_http
from app.services.workflow_templates import analyze_workflow, parse_github_repo

BASE = "/api/v1/ai/workflow-templates"

GOOD_WORKFLOW = {
    "name": "Daily Report",
    "nodes": [
        {
            "name": "Schedule",
            "type": "n8n-nodes-base.scheduleTrigger",
            "parameters": {},
        },
        {
            "name": "Send mail",
            "type": "n8n-nodes-base.gmail",
            "parameters": {},
            "credentials": {"gmailOAuth2": {"id": "x", "name": "Gmail"}},
        },
    ],
    "connections": {},
}

SECRET_WORKFLOW = {
    "name": "Leaky",
    "nodes": [
        {
            "name": "HTTP",
            "type": "n8n-nodes-base.httpRequest",
            "parameters": {
                "url": "https://example.com/hook",
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "Bearer abcdefghijklmnopqrstuvwxyz0123456789"}
                    ]
                },
            },
        },
        {"name": "PDF", "type": "n8n-nodes-pdfmint.pdfMint", "parameters": {}},
    ],
    "connections": {},
}

FILES = {
    "Telegram/report.json": json.dumps(GOOD_WORKFLOW),
    "Other/leaky.json": json.dumps(SECRET_WORKFLOW),
    "Other/broken.json": "{not json",
    "Other/empty.json": json.dumps({"nodes": []}),
    "README.json": json.dumps({"nope": True}),
}


class FakeGitHub:
    def __init__(self, files=None):
        self.files = files if files is not None else dict(FILES)
        self.json_gets = []
        self.text_gets = []

    async def get_json(self, url, token, timeout_seconds):
        self.json_gets.append(url)
        tree = [
            {"type": "blob", "path": path} for path in self.files
        ] + [{"type": "tree", "path": "Telegram"}]
        return 200, {"tree": tree}

    async def get_text(self, url, timeout_seconds):
        self.text_gets.append(url)
        for path, text in self.files.items():
            if url.endswith(path):
                return 200, text
        return 404, ""


@pytest.fixture
async def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def fake_github(app):
    fake = FakeGitHub()
    app.dependency_overrides[github_http] = lambda: fake
    return fake


def test_parse_github_repo_variants():
    assert parse_github_repo("https://github.com/enescingoz/awesome-n8n-templates") == (
        "enescingoz/awesome-n8n-templates"
    )
    assert parse_github_repo("https://github.com/a/b.git") == "a/b"
    assert parse_github_repo("a/b") == "a/b"


def test_analyze_good_workflow():
    result = analyze_workflow(json.dumps(GOOD_WORKFLOW), "Telegram/report.json")
    assert "rejected" not in result
    assert result["name"] == "Daily Report"
    assert result["category"] == "Telegram"
    assert result["node_count"] == 2
    assert result["credential_types"] == ["gmailOAuth2"]
    assert result["compatibility"] == "compatible"
    assert result["security_flag"] is False


def test_analyze_flags_secret_and_community_node():
    result = analyze_workflow(json.dumps(SECRET_WORKFLOW), "Other/leaky.json")
    assert result["security_flag"] is True
    assert "suspected_hardcoded_secret" in result["risk_flags"]
    assert result["compatibility"] == "needs_community_nodes"
    assert result["community_nodes"] == ["n8n-nodes-pdfmint.pdfMint"]
    assert result["has_http_node"] is True
    assert result["http_urls"] == ["https://example.com/hook"]


def test_analyze_rejects_bad_files():
    assert analyze_workflow("{oops", "x.json")["rejected"] == "invalid_json"
    assert analyze_workflow(json.dumps({"nodes": []}), "x.json")["rejected"] == (
        "invalid_structure"
    )


async def test_default_source_and_duplicate_guard(owner, fake_github):
    created = owner.post(f"{BASE}/sources/default")
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["repo"] == "enescingoz/awesome-n8n-templates"
    assert body["license"] == "CC BY 4.0"
    again = owner.post(f"{BASE}/sources/default")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    duplicate = owner.post(
        f"{BASE}/sources",
        json={"repo_url": "https://github.com/enescingoz/awesome-n8n-templates"},
    )
    assert duplicate.status_code == 409


async def test_import_counts_and_idempotency(owner, fake_github):
    source = owner.post(f"{BASE}/sources/default").json()
    result = owner.post(f"{BASE}/sources/{source['id']}/import")
    assert result.status_code == 200, result.text
    log = result.json()
    assert log["status"] == "completed"
    assert log["found"] == 5
    assert log["downloaded"] == 5
    assert log["created"] == 2
    assert log["rejected"] == 3
    reasons = {f["path"]: f["reason"] for f in log["failures"]}
    assert reasons["Other/broken.json"] == "invalid_json"
    assert reasons["Other/empty.json"] == "invalid_structure"
    assert reasons["README.json"] == "invalid_structure"

    second = owner.post(f"{BASE}/sources/{source['id']}/import").json()
    assert second["created"] == 0
    assert second["unchanged"] == 2
    assert second["updated"] == 0

    fake_github.files["Telegram/report.json"] = json.dumps(
        {**GOOD_WORKFLOW, "name": "Daily Report v2"}
    )
    third = owner.post(f"{BASE}/sources/{source['id']}/import").json()
    assert third["updated"] == 1
    assert third["unchanged"] == 1


async def test_template_list_detail_and_review(owner, fake_github):
    source = owner.post(f"{BASE}/sources/default").json()
    owner.post(f"{BASE}/sources/{source['id']}/import")

    listing = owner.get(f"{BASE}/templates")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert names == {"Daily Report", "Leaky"}
    leaky = next(item for item in body["items"] if item["name"] == "Leaky")
    assert leaky["security_flag"] is True
    assert leaky["review_status"] == "pending_review"
    assert leaky["attribution"].startswith("Workflow templates collected from")

    filtered = owner.get(f"{BASE}/templates", params={"category": "Telegram"})
    assert filtered.json()["total"] == 1

    detail = owner.get(f"{BASE}/templates/{leaky['id']}")
    assert detail.status_code == 200
    assert detail.json()["workflow_json"]["name"] == "Leaky"
    assert "workflow_json" not in leaky  # list view stays light

    reviewed = owner.patch(
        f"{BASE}/templates/{leaky['id']}/review", json={"review_status": "rejected"}
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "rejected"


def test_templates_require_auth(client):
    assert client.get(f"{BASE}/sources").status_code == 401
    assert client.get(f"{BASE}/templates").status_code == 401
