"""Credential bindings: mapping template credential types to the user's
own n8n credentials, bulk re-apply to installed workflows, install-time
rewriting, and Vietnamese template names (rename + translate guard).
Offline tests with a fake n8n HTTP layer; no real credentials anywhere.
"""

from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from app.services.credential_bindings import (
    apply_bindings_to_nodes,
    credential_coverage,
)
from app.services.workflow_templates import _parse_translation_lines

BASE = "/api/v1/ai/credential-bindings"
TEMPLATES = "/api/v1/ai/workflow-templates"

N8N_CREDENTIALS = [
    {"id": "cred-gmail-1", "name": "Gmail của tôi", "type": "gmailOAuth2"},
    {"id": "cred-openai-1", "name": "OpenAI key", "type": "openAiApi"},
    {"id": "cred-gmail-2", "name": "Gmail phụ", "type": "gmailOAuth2"},
]


@pytest.fixture
async def owner(client, register):
    assert register(client).status_code == 201
    return client


class FakeN8n:
    """Stand-in for the n8n REST API: credentials list, workflow
    create/fetch/put. Created workflows are stored so the bulk
    re-apply endpoint can fetch them back."""

    def __init__(self):
        self.posts = []
        self.puts = []
        self.workflows = {}
        self.counter = 0

    async def get_json(self, url, api_key, timeout_seconds):
        if url.endswith("/api/v1/credentials"):
            return 200, {"data": N8N_CREDENTIALS}
        workflow_id = url.rsplit("/workflows/", 1)[1]
        raw = self.workflows.get(workflow_id)
        if raw is None:
            return 404, {}
        return 200, raw

    async def post_json_body(self, url, api_key, payload, timeout_seconds):
        self.posts.append({"url": url, "payload": payload})
        self.counter += 1
        workflow_id = f"n8n-wf-{self.counter}"
        raw = {**payload, "id": workflow_id, "active": False, "tags": []}
        self.workflows[workflow_id] = raw
        return 201, raw

    async def put_json(self, url, api_key, payload, timeout_seconds):
        self.puts.append({"url": url, "payload": payload})
        workflow_id = url.rsplit("/workflows/", 1)[1]
        raw = {**payload, "id": workflow_id, "active": False, "tags": []}
        self.workflows[workflow_id] = raw
        return 200, raw

    async def delete_json(self, url, api_key, timeout_seconds):
        return 204


@pytest.fixture
def fake_n8n(app, settings):
    from app.api.v1.n8n_platform import n8n_api_http

    settings.n8n_api_key = SecretStr("test-n8n-key")
    fake = FakeN8n()
    app.dependency_overrides[n8n_api_http] = lambda: fake
    return fake


def _node(name, cred_type=None, cred_id="author-machine-id"):
    node = {"name": name, "type": "n8n-nodes-base.test", "parameters": {}}
    if cred_type:
        node["credentials"] = {cred_type: {"id": cred_id, "name": "Author cred"}}
    return node


async def _seed_template(db, template_id="tpl-1", **overrides):
    doc = {
        "_id": template_id,
        "name": "Morning Gmail digest",
        "name_vi": None,
        "category": "Gmail_and_Email_Automation",
        "source_kind": "github",
        "node_count": 2,
        "node_types": ["n8n-nodes-base.test"],
        "credential_types": ["gmailOAuth2", "openAiApi"],
        "complexity": "simple",
        "compatibility": "compatible",
        "community_nodes": [],
        "security_flag": False,
        "risk_flags": [],
        "review_status": "approved",
        "version": 1,
        "license": "CC BY 4.0",
        "attribution": "test",
        "description": "",
        "has_code_node": False,
        "has_http_node": False,
        "http_urls": [],
        "workflow_json": {
            "name": "Morning Gmail digest",
            "nodes": [_node("Read mail", "gmailOAuth2"), _node("Summarize", "openAiApi")],
            "connections": {},
            "settings": {},
        },
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    await db.shared_workflows.insert_one(doc)
    return doc


# -- pure helpers ------------------------------------------------------------


def test_apply_bindings_rewrites_only_bound_types_and_never_mutates_input():
    nodes = [_node("A", "gmailOAuth2"), _node("B", "openAiApi"), _node("C")]
    bindings = {"gmailOAuth2": {"id": "cred-gmail-1", "name": "Gmail của tôi"}}
    out, applied = apply_bindings_to_nodes(nodes, bindings)
    assert applied == ["gmailOAuth2"]
    assert out[0]["credentials"]["gmailOAuth2"] == {
        "id": "cred-gmail-1",
        "name": "Gmail của tôi",
    }
    assert out[1]["credentials"]["openAiApi"]["id"] == "author-machine-id"
    # The template's own nodes keep the author's reference.
    assert nodes[0]["credentials"]["gmailOAuth2"]["id"] == "author-machine-id"


def test_credential_coverage_splits_rewritten_and_missing():
    nodes = [_node("A", "gmailOAuth2"), _node("B", "openAiApi"), _node("C")]
    bindings = {"gmailOAuth2": {"id": "cred-gmail-1", "name": "Gmail của tôi"}}
    rewritten, missing = credential_coverage(nodes, bindings)
    assert rewritten == ["gmailOAuth2"]
    assert missing == ["openAiApi"]
    # Nothing bound: everything the definition references is missing.
    assert credential_coverage(nodes, {}) == ([], ["gmailOAuth2", "openAiApi"])
    # Nothing referenced: nothing to report.
    assert credential_coverage([_node("C")], bindings) == ([], [])


def test_parse_translation_lines_requires_every_index():
    text = "1. Tóm tắt email buổi sáng\n2. Gửi tin Telegram\n"
    assert _parse_translation_lines(text, 2) == [
        "Tóm tắt email buổi sáng",
        "Gửi tin Telegram",
    ]
    assert _parse_translation_lines("1. Chỉ một dòng\n", 2) is None
    assert _parse_translation_lines("không đánh số", 1) is None


# -- bindings API --------------------------------------------------------------


async def test_bindings_view_lists_required_types_and_n8n_credentials(
    owner, fake_n8n, db
):
    await _seed_template(db)
    response = owner.get(BASE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bindings"] == []
    assert body["n8n_error"] is None
    assert {c["id"] for c in body["n8n_credentials"]} == {
        "cred-gmail-1",
        "cred-openai-1",
        "cred-gmail-2",
    }
    required = {item["cred_type"]: item for item in body["required_types"]}
    assert required["gmailOAuth2"]["template_count"] == 1
    assert required["gmailOAuth2"]["bound"] is False
    assert required["openAiApi"]["bound"] is False


async def test_set_binding_validates_credential_and_type(owner, fake_n8n, db):
    await _seed_template(db)
    wrong_type = owner.put(
        BASE, json={"cred_type": "gmailOAuth2", "n8n_credential_id": "cred-openai-1"}
    )
    assert wrong_type.status_code == 422, wrong_type.text
    assert wrong_type.json()["detail"]["code"] == "credential_binding_invalid"

    unknown = owner.put(
        BASE, json={"cred_type": "gmailOAuth2", "n8n_credential_id": "nope"}
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "credential_binding_invalid"

    saved = owner.put(
        BASE, json={"cred_type": "gmailOAuth2", "n8n_credential_id": "cred-gmail-2"}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["n8n_credential_name"] == "Gmail phụ"

    view = owner.get(BASE).json()
    assert view["bindings"][0]["cred_type"] == "gmailOAuth2"
    required = {item["cred_type"]: item for item in view["required_types"]}
    assert required["gmailOAuth2"]["bound"] is True

    removed = owner.delete(f"{BASE}/gmailOAuth2")
    assert removed.status_code == 204
    missing = owner.delete(f"{BASE}/gmailOAuth2")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "credential_binding_not_found"


# -- install + bulk re-apply ---------------------------------------------------


async def test_install_rewrites_bound_credentials_and_uses_vietnamese_name(
    owner, fake_n8n, db
):
    await _seed_template(db, name_vi="Tóm tắt email buổi sáng")
    owner.put(
        BASE, json={"cred_type": "gmailOAuth2", "n8n_credential_id": "cred-gmail-1"}
    )
    response = owner.post(f"{TEMPLATES}/install", json={"template_ids": ["tpl-1"]})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "installed"
    assert result["template_name"] == "Tóm tắt email buổi sáng"

    payload = fake_n8n.posts[0]["payload"]
    assert payload["name"] == "Tóm tắt email buổi sáng"
    nodes = {node["name"]: node for node in payload["nodes"]}
    assert nodes["Read mail"]["credentials"]["gmailOAuth2"] == {
        "id": "cred-gmail-1",
        "name": "Gmail của tôi",
    }
    # Unbound types keep the template's original reference.
    assert nodes["Summarize"]["credentials"]["openAiApi"]["id"] == "author-machine-id"


async def test_install_reports_missing_credential_types(owner, fake_n8n, db):
    await _seed_template(db)
    owner.put(
        BASE, json={"cred_type": "gmailOAuth2", "n8n_credential_id": "cred-gmail-1"}
    )
    response = owner.post(f"{TEMPLATES}/install", json={"template_ids": ["tpl-1"]})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    # The install still succeeds — the gap is reported, not blocking.
    assert result["status"] == "installed"
    assert result["rewritten_credential_types"] == ["gmailOAuth2"]
    assert result["missing_credential_types"] == ["openAiApi"]

    # The installed list carries the same warning until the type is bound.
    mine = owner.get(f"{TEMPLATES}/mine").json()
    assert mine[0]["missing_credential_types"] == ["openAiApi"]

    owner.put(
        BASE, json={"cred_type": "openAiApi", "n8n_credential_id": "cred-openai-1"}
    )
    mine = owner.get(f"{TEMPLATES}/mine").json()
    assert mine[0]["missing_credential_types"] == []

    # Re-installing reports already_installed with the coverage attached.
    again = owner.post(f"{TEMPLATES}/install", json={"template_ids": ["tpl-1"]})
    result = again.json()["results"][0]
    assert result["status"] == "already_installed"
    assert result["missing_credential_types"] == []
    assert result["rewritten_credential_types"] == ["gmailOAuth2", "openAiApi"]


async def test_install_without_any_binding_reports_everything_missing(
    owner, fake_n8n, db
):
    await _seed_template(db)
    response = owner.post(f"{TEMPLATES}/install", json={"template_ids": ["tpl-1"]})
    result = response.json()["results"][0]
    assert result["status"] == "installed"
    assert result["rewritten_credential_types"] == []
    assert result["missing_credential_types"] == ["gmailOAuth2", "openAiApi"]


async def test_apply_installed_rewrites_existing_workflows(owner, fake_n8n, db):
    await _seed_template(db)
    installed = owner.post(f"{TEMPLATES}/install", json={"template_ids": ["tpl-1"]})
    assert installed.json()["results"][0]["status"] == "installed"

    # Nothing bound yet: re-apply is a no-op.
    noop = owner.post(f"{BASE}/apply-installed")
    assert noop.status_code == 200, noop.text
    assert noop.json()["unchanged"] == 1
    assert fake_n8n.puts == []

    owner.put(
        BASE, json={"cred_type": "openAiApi", "n8n_credential_id": "cred-openai-1"}
    )
    applied = owner.post(f"{BASE}/apply-installed")
    body = applied.json()
    assert body["updated"] == 1, body
    assert body["results"][0]["bound_types"] == ["openAiApi"]
    put_nodes = {n["name"]: n for n in fake_n8n.puts[0]["payload"]["nodes"]}
    assert put_nodes["Summarize"]["credentials"]["openAiApi"] == {
        "id": "cred-openai-1",
        "name": "OpenAI key",
    }
    assert put_nodes["Read mail"]["credentials"]["gmailOAuth2"]["id"] == (
        "author-machine-id"
    )


# -- Vietnamese names ------------------------------------------------------------


async def test_rename_name_vi_set_and_clear(owner, fake_n8n, db):
    await _seed_template(db)
    renamed = owner.patch(
        f"{TEMPLATES}/templates/tpl-1/name-vi",
        json={"name_vi": "  Tóm tắt email buổi sáng  "},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name_vi"] == "Tóm tắt email buổi sáng"

    detail = owner.get(f"{TEMPLATES}/templates/tpl-1")
    assert detail.json()["name_vi"] == "Tóm tắt email buổi sáng"

    cleared = owner.patch(
        f"{TEMPLATES}/templates/tpl-1/name-vi", json={"name_vi": ""}
    )
    assert cleared.json()["name_vi"] is None

    missing = owner.patch(
        f"{TEMPLATES}/templates/nope/name-vi", json={"name_vi": "X"}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "template_not_found"


async def test_translate_names_without_provider_is_a_coded_error(owner, db):
    await _seed_template(db)
    response = owner.post(f"{TEMPLATES}/templates/translate-names", json={})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "credentials_missing"
