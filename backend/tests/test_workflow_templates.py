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


async def test_stats_service_filter_and_sort(owner, fake_github):
    source = owner.post(f"{BASE}/sources/default").json()
    owner.post(f"{BASE}/sources/{source['id']}/import")

    stats = owner.get(f"{BASE}/templates/stats")
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["total"] == 2
    assert body["by_category"] == {"Other": 1, "Telegram": 1}
    assert body["by_review_status"] == {"pending_review": 2}
    assert body["by_compatibility"] == {"compatible": 1, "needs_community_nodes": 1}
    assert body["services"] == ["gmailOAuth2"]

    by_service = owner.get(f"{BASE}/templates", params={"service": "gmailOAuth2"})
    assert by_service.json()["total"] == 1
    assert by_service.json()["items"][0]["name"] == "Daily Report"

    by_complexity = owner.get(f"{BASE}/templates", params={"complexity": "simple"})
    assert by_complexity.json()["total"] == 2

    needs_nodes = owner.get(
        f"{BASE}/templates", params={"compatibility": "needs_community_nodes"}
    )
    assert needs_nodes.json()["total"] == 1
    assert needs_nodes.json()["items"][0]["name"] == "Leaky"


class FakeN8n:
    """Minimal stand-in for the n8n REST API used by template sync."""

    def __init__(self):
        self.posts = []
        self.patches = []
        self.deletes = []

    async def post_json_body(self, url, api_key, payload, timeout_seconds):
        self.posts.append({"url": url, "payload": payload})
        return 201, {**payload, "id": "n8n-new-1", "active": False, "tags": []}

    async def patch_json(self, url, api_key, payload, timeout_seconds):
        self.patches.append({"url": url, "payload": payload})
        workflow_id = url.rsplit("/workflows/", 1)[1]
        return 200, {**payload, "id": workflow_id, "active": False, "tags": []}

    async def delete_json(self, url, api_key, timeout_seconds):
        self.deletes.append(url)
        return 204


@pytest.fixture
def fake_n8n(app, settings):
    from pydantic import SecretStr

    from app.api.v1.n8n_platform import n8n_api_http

    settings.n8n_api_key = SecretStr("test-key")
    fake = FakeN8n()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    return fake


async def _import_and_approve(owner):
    source = owner.post(f"{BASE}/sources/default").json()
    owner.post(f"{BASE}/sources/{source['id']}/import")
    listing = owner.get(f"{BASE}/templates").json()
    report = next(i for i in listing["items"] if i["name"] == "Daily Report")
    leaky = next(i for i in listing["items"] if i["name"] == "Leaky")
    owner.patch(
        f"{BASE}/templates/{report['id']}/review", json={"review_status": "approved"}
    )
    return report, leaky


async def test_sync_install_flow(owner, fake_github, fake_n8n):
    report, leaky = await _import_and_approve(owner)

    candidates = owner.get(f"{BASE}/sync-candidates")
    assert candidates.status_code == 200, candidates.text
    available_ids = {item["id"] for item in candidates.json()["available"]}
    assert report["id"] in available_ids
    assert leaky["id"] not in available_ids  # not approved yet

    refused = owner.post(f"{BASE}/install", json={"template_ids": [leaky["id"]]})
    assert refused.json()["results"][0]["status"] == "failed"
    assert refused.json()["results"][0]["error"] == "template_not_approved"

    installed = owner.post(f"{BASE}/install", json={"template_ids": [report["id"]]})
    result = installed.json()["results"][0]
    assert result["status"] == "installed"
    assert result["n8n_workflow_id"] == "n8n-new-1"
    assert len(fake_n8n.posts) == 1

    again = owner.post(f"{BASE}/install", json={"template_ids": [report["id"]]})
    assert again.json()["results"][0]["status"] == "already_installed"
    assert len(fake_n8n.posts) == 1  # no duplicate created in n8n

    mine = owner.get(f"{BASE}/mine").json()
    assert len(mine) == 1
    assert mine[0]["installed_version"] == 1
    assert mine[0]["update_available"] is False

    candidates2 = owner.get(f"{BASE}/sync-candidates").json()
    assert candidates2["available"] == []
    assert candidates2["updates"] == []
    return mine[0]


async def test_sync_update_and_remove(owner, fake_github, fake_n8n):
    report, _leaky = await _import_and_approve(owner)
    owner.post(f"{BASE}/install", json={"template_ids": [report["id"]]})
    mine = owner.get(f"{BASE}/mine").json()[0]

    fake_github.files["Telegram/report.json"] = json.dumps(
        {**GOOD_WORKFLOW, "name": "Daily Report v2"}
    )
    source = owner.get(f"{BASE}/sources").json()[0]
    owner.post(f"{BASE}/sources/{source['id']}/import")

    candidates = owner.get(f"{BASE}/sync-candidates").json()
    assert len(candidates["updates"]) == 1
    assert candidates["updates"][0]["latest_version"] == 2

    updated = owner.post(f"{BASE}/mine/{mine['id']}/update")
    assert updated.status_code == 200, updated.text
    assert updated.json()["installed_version"] == 2
    assert updated.json()["update_available"] is False
    assert len(fake_n8n.patches) == 1
    assert fake_n8n.patches[0]["payload"]["name"] == "Daily Report v2"

    removed = owner.delete(f"{BASE}/mine/{mine['id']}")
    assert removed.status_code == 204
    assert any("n8n-new-1" in url for url in fake_n8n.deletes)
    assert owner.get(f"{BASE}/mine").json() == []
    # The shared template itself survives removal.
    assert owner.get(f"{BASE}/templates").json()["total"] == 2


async def test_versions_diff_and_restore(owner, fake_github):
    source = owner.post(f"{BASE}/sources/default").json()
    owner.post(f"{BASE}/sources/{source['id']}/import")
    listing = owner.get(f"{BASE}/templates").json()
    report = next(i for i in listing["items"] if i["name"] == "Daily Report")

    versions = owner.get(f"{BASE}/templates/{report['id']}/versions")
    assert versions.status_code == 200, versions.text
    assert [v["version"] for v in versions.json()] == [1]

    changed = json.loads(json.dumps(GOOD_WORKFLOW))
    changed["nodes"][1]["parameters"] = {"operation": "sendAndWait"}
    changed["nodes"].append(
        {
            "id": "4",
            "name": "Extra",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [400, 100],
            "parameters": {},
        }
    )
    fake_github.files["Telegram/report.json"] = json.dumps(changed)
    owner.post(f"{BASE}/sources/{source['id']}/import")

    versions2 = owner.get(f"{BASE}/templates/{report['id']}/versions").json()
    assert [v["version"] for v in versions2] == [2, 1]

    diff = owner.get(
        f"{BASE}/templates/{report['id']}/diff",
        params={"from_version": 1, "to_version": 2},
    )
    assert diff.status_code == 200, diff.text
    body = diff.json()
    assert body["nodes_added"] == ["Extra"]
    assert body["nodes_removed"] == []
    changed_names = {c["name"] for c in body["nodes_changed"]}
    assert "Send mail" in changed_names

    restored = owner.post(f"{BASE}/templates/{report['id']}/versions/1/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 3
    node_names = {n["name"] for n in restored.json()["workflow_json"]["nodes"]}
    assert node_names == {"Schedule", "Send mail"}

    missing = owner.get(f"{BASE}/templates/{report['id']}/versions/99")
    assert missing.status_code == 404


async def test_contribute_template(owner):
    payload = {
        "name": "My Shared Flow",
        "category": "Community",
        "workflow_json": GOOD_WORKFLOW,
    }
    created = owner.post(f"{BASE}/templates/contribute", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_kind"] == "community"
    assert body["review_status"] == "pending_review"
    assert body["version"] == 1

    listing = owner.get(f"{BASE}/templates", params={"q": "My Shared"})
    assert listing.json()["total"] == 1

    invalid = owner.post(
        f"{BASE}/templates/contribute",
        json={"name": "Broken", "workflow_json": {"nodes": "nope"}},
    )
    assert invalid.status_code == 422


def test_templates_require_auth(client):
    assert client.get(f"{BASE}/sources").status_code == 401
    assert client.get(f"{BASE}/templates").status_code == 401
