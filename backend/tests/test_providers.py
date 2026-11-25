"""Authenticated API contract mock tests for MongoDB backend."""

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.api.v1.providers import provider_http
from app.core.credential_vault import CredentialVault
from app.services.ai.http import ModelListingHTTP

BASE = "/api/v1/ai/providers"
KEY = "contract-only-api-key"
MODEL = {"id": "contract-only-model", "object": "model", "created": 1700000000, "owned_by": "test"}


@pytest.fixture(autouse=True)
def provider_settings(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    return settings


@pytest.fixture
def owner(client, register):
    assert register(client).status_code == 201
    return client


@pytest.fixture
def mock_http(app):
    def configure(handler=None):
        handler = handler or (
            lambda _: httpx.Response(200, json={"object": "list", "data": [MODEL]})
        )
        app.dependency_overrides[provider_http] = lambda: ModelListingHTTP(
            transport=httpx.MockTransport(handler)
        )

    configure()
    return configure


def saved(client, **fields):
    response = client.patch(f"{BASE}/openai", json={"api_key": KEY, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def metadata(client):
    return client.get(BASE).json()["providers"][0]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "", None),
        ("PATCH", "/openai", {"api_key": KEY}),
        ("GET", "/openai/models", None),
        ("POST", "/openai/test", None),
        ("DELETE", "/openai", None),
    ],
)
def test_all_provider_routes_require_auth(client, method, path, body):
    response = client.request(method, BASE + path, json=body)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_registry_and_unsaved_catalog(owner):
    response = owner.get(BASE)
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["encryption_ready"] is True
    providers = response.json()["providers"]
    assert [(p["id"], p["name"], p["implemented"]) for p in providers] == [
        ("openai", "OpenAI", True),
        ("gemini", "Google Gemini", True),
        ("groq", "Groq", True),
        ("anthropic", "Anthropic Claude", False),
        ("deepseek", "DeepSeek", False),
        ("ollama", "Ollama", True),
    ]
    assert all(
        not p["configured"] and not p["enabled"] and p["model_count"] == 0 for p in providers
    )
    assert owner.get(f"{BASE}/openai/models").json() == {
        "provider": "openai",
        "models": [],
        "synced_at": None,
    }
    assert_error(owner.post(f"{BASE}/openai/test"), 409, "credentials_missing")
    assert_error(owner.patch(f"{BASE}/openai", json={"enabled": True}), 409, "credentials_missing")


@pytest.mark.parametrize("slug", ["anthropic", "deepseek", "unknown"])
def test_future_and_unknown_providers(owner, slug):
    status, code = (
        (404, "provider_not_found") if slug == "unknown" else (409, "provider_not_implemented")
    )
    assert_error(owner.patch(f"{BASE}/{slug}", json={"api_key": KEY}), status, code)
    assert_error(owner.post(f"{BASE}/{slug}/test"), status, code)
    if slug == "unknown":
        assert_error(owner.get(f"{BASE}/{slug}/models"), status, code)
        assert_error(owner.delete(f"{BASE}/{slug}"), status, code)
    else:
        assert owner.get(f"{BASE}/{slug}/models").json()["models"] == []
        assert owner.delete(f"{BASE}/{slug}").status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"api_key": "short"},
        {"api_key": "a" * 4097},
        {"api_key": "ab cd12345"},
        {"api_key": "ab\ncd12345"},
        {"api_key": "abcd\u2603efgh"},
        {"api_key": "abc\x7fdefgh"},
        {"api_key": None},
        {"api_key": 12345678},
        {"api_key": {"password": KEY}},
        {"enabled": "true"},
        {"enabled": 1},
        {"enabled": None},
        {"default_model": ""},
        {"default_model": 123},
        {"default_model": "a" * 513},
        {"password": KEY},
        {"api_key": KEY, "base_url": "https://attacker.invalid"},
        {"api_key": KEY, "default_model": MODEL["id"]},
        {KEY: KEY},
    ],
)
def test_patch_validation_redacts_submitted_inputs(owner, body, caplog):
    assert_error(owner.patch(f"{BASE}/openai", json=body), 422, "invalid_provider_configuration")
    assert KEY not in caplog.text
    assert not metadata(owner)["configured"]


def test_invalid_json_is_redacted(owner):
    response = owner.patch(
        f"{BASE}/openai", content='{"api_key":"' + KEY, headers={"Content-Type": "application/json"}
    )
    assert_error(response, 422, "invalid_provider_configuration")


@pytest.mark.asyncio
async def test_save_encrypts_at_rest_and_never_returns_credential_fields(owner, db, settings):
    result = saved(owner, api_key="  " + KEY + "  ")
    assert result["configured"] and result["enabled"]
    assert result["connection_status"] == "untested"
    credential = await db.user_provider_credentials.find_one({})
    assert KEY not in credential["encrypted_api_key"]
    assert (
        CredentialVault(settings.credential_encryption_key)
        .decrypt(credential["encrypted_api_key"], credential["user_id"], credential["provider"])
        .get_secret_value()
        == KEY
    )
    forbidden = {
        "credential_id",
        "user_id",
        "encrypted_api_key",
        "api_key",
        "key_prefix",
        "key_suffix",
    }
    assert forbidden.isdisjoint(result)
    assert str(credential["_id"]) not in owner.get(BASE).text
    assert credential["encrypted_api_key"] not in owner.get(BASE).text
    assert owner.patch(f"{BASE}/openai", json={"enabled": False}).json()["enabled"] is False


@pytest.mark.asyncio
async def test_read_only_connection_sync_even_when_disabled_and_default_validation(
    owner, mock_http, db
):
    saved(owner, enabled=False)
    assert_error(
        owner.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]}),
        409,
        "invalid_default_model",
    )
    response = owner.post(f"{BASE}/openai/test")
    assert response.status_code == 200
    result = response.json()
    assert result["scope"] == "model_listing"
    assert result["model_count"] == result["provider"]["model_count"] == 1
    assert result["provider"]["enabled"] is False
    assert result["provider"]["connection_status"] == "connected"
    models = owner.get(f"{BASE}/openai/models").json()
    assert models["models"][0]["capabilities"] == dict.fromkeys(
        ["chat", "streaming", "tools", "embeddings"]
    )
    assert models["models"][0]["capability_source"] == "unknown"
    assert models["synced_at"] == result["provider"]["models_synced_at"]
    assert (
        owner.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]}).json()["default_model"]
        == MODEL["id"]
    )
    assert_error(
        owner.patch(f"{BASE}/openai", json={"default_model": "unsynced"}),
        409,
        "invalid_default_model",
    )
    assert (
        owner.patch(f"{BASE}/openai", json={"default_model": None}).json()["default_model"] is None
    )


def test_api_gemini_catalog(owner, mock_http):
    mock_http(
        lambda _: httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/contract-gemini",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        )
    )
    assert owner.patch(f"{BASE}/gemini", json={"api_key": KEY}).status_code == 200
    assert owner.post(f"{BASE}/gemini/test").json()["model_count"] == 1
    model = owner.get(f"{BASE}/gemini/models").json()["models"][0]
    assert model["id"] == "contract-gemini"
    assert model["capabilities"]["chat"] is True
    assert model["capabilities"]["tools"] is None


def test_key_replacement_resets_cache_default_and_error_state(owner, mock_http):
    saved(owner)
    assert owner.post(f"{BASE}/openai/test").status_code == 200
    owner.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]})
    replacement = saved(owner, api_key="contract-new-key")
    assert replacement["connection_status"] == "untested"
    assert replacement["default_model"] is None
    assert replacement["models_synced_at"] is replacement["last_checked_at"] is None
    assert replacement["last_error_code"] is None
    assert replacement["model_count"] == 0
    assert owner.get(f"{BASE}/openai/models").json()["models"] == []


@pytest.mark.parametrize(
    "failure,code,status",
    [
        (401, "provider_authentication_failed", 400),
        (403, "provider_authentication_failed", 400),
        (429, "provider_rate_limited", 429),
        (503, "provider_unavailable", 502),
        ("timeout", "provider_timeout", 504),
        ("json", "invalid_provider_response", 502),
    ],
)
def test_failure_retains_cache_and_persists_only_safe_error(
    owner, mock_http, failure, code, status, caplog
):
    saved(owner)
    assert owner.post(f"{BASE}/openai/test").status_code == 200
    owner.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]})
    previous = owner.get(f"{BASE}/openai/models").json()

    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(KEY, request=request)
        return httpx.Response(200 if failure == "json" else failure, text=KEY)

    mock_http(handle)
    assert_error(owner.post(f"{BASE}/openai/test"), status, code)
    current = metadata(owner)
    assert current["connection_status"] == "error"
    assert current["last_error_code"] == code
    assert current["last_checked_at"] is not None
    assert current["default_model"] == MODEL["id"]
    assert owner.get(f"{BASE}/openai/models").json() == previous
    assert KEY not in caplog.text


def test_successful_empty_resync_clears_cache_and_invalid_default(owner, mock_http):
    saved(owner)
    owner.post(f"{BASE}/openai/test")
    owner.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]})
    mock_http(lambda _: httpx.Response(200, json={"object": "list", "data": []}))
    result = owner.post(f"{BASE}/openai/test").json()
    assert result["provider"]["connection_status"] == "connected"
    assert result["provider"]["default_model"] is None
    assert result["model_count"] == 0


def test_missing_encryption_preserves_auth_dashboard_and_existing_metadata(
    owner, settings, mock_http
):
    saved(owner)
    settings.credential_encryption_key = None
    assert owner.get(BASE).json()["encryption_ready"] is False
    assert owner.get("/api/v1/auth/me").status_code == 200
    assert owner.get("/api/v1/dashboard").status_code == 200
    assert_error(
        owner.patch(f"{BASE}/openai", json={"api_key": "new-contract-key"}),
        503,
        "encryption_unavailable",
    )
    assert_error(owner.post(f"{BASE}/openai/test"), 503, "encryption_unavailable")
    assert metadata(owner)["last_error_code"] == "encryption_unavailable"
    assert owner.delete(f"{BASE}/openai").status_code == 204


def test_wrong_encryption_key_is_safe_and_can_be_replaced(owner, settings, mock_http):
    saved(owner)
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())
    assert_error(owner.post(f"{BASE}/openai/test"), 503, "encryption_unavailable")
    saved(owner)
    assert owner.post(f"{BASE}/openai/test").status_code == 200


def test_provider_application_rate_limit_has_safe_detail(owner, app):
    app.state.rate_limiter.settings.api_rate_limit = 1
    assert_error(owner.get(BASE), 429, "request_rate_limited")


def test_csrf_no_store_and_cors_for_new_mutations(owner):
    response = owner.patch(
        f"{BASE}/openai", json={"api_key": KEY}, headers={"Origin": "https://attacker.invalid"}
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    for method in ["PATCH", "DELETE"]:
        response = owner.options(
            f"{BASE}/openai", headers={"Access-Control-Request-Method": method}
        )
        assert response.status_code == 200
        assert method in response.headers["access-control-allow-methods"]

@pytest.fixture
def mock_chat(app):
    from app.api.v1.providers import provider_chat_http
    from app.services.ai.chat import ChatHTTP

    def configure(handler):
        app.dependency_overrides[provider_chat_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )

    return configure


def _sync_model(owner, mock_http, model_id):
    mock_http(lambda _: httpx.Response(
        200, json={"object": "list", "data": [dict(MODEL, id=model_id)]}
    ))
    assert owner.post(f"{BASE}/openai/test").status_code == 200


def test_models_carry_reference_pricing_and_empty_health(owner, mock_http):
    saved(owner)
    _sync_model(owner, mock_http, "gpt-4o-mini")
    models = owner.get(f"{BASE}/openai/models").json()["models"]
    assert len(models) == 1
    pricing = models[0]["pricing"]
    assert pricing["tier"] == "priced"
    assert pricing["source"] == "reference"
    assert pricing["input_per_million"] == pytest.approx(0.15)
    assert pricing["output_per_million"] == pytest.approx(0.60)
    assert models[0]["health_status"] is None


def test_check_model_ok_persists_health(owner, mock_http, mock_chat):
    saved(owner)
    _sync_model(owner, mock_http, "gpt-4o-mini")
    sse = 'data: {"choices": [{"delta": {"content": "pong"}}]}\n\ndata: [DONE]\n\n'
    mock_chat(lambda _: httpx.Response(
        200, text=sse, headers={"content-type": "text/event-stream"}
    ))
    result = owner.post(f"{BASE}/openai/models/gpt-4o-mini/check")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "ok" and body["error_code"] is None
    model = owner.get(f"{BASE}/openai/models").json()["models"][0]
    assert model["health_status"] == "ok"
    assert model["health_checked_at"] is not None


def test_check_model_records_provider_error(owner, mock_http, mock_chat):
    saved(owner)
    _sync_model(owner, mock_http, "gpt-4o-mini")
    mock_chat(lambda _: httpx.Response(503, json={"error": {"message": "busy"}}))
    result = owner.post(f"{BASE}/openai/models/gpt-4o-mini/check")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "error"
    assert body["error_code"] == "provider_unavailable"
    model = owner.get(f"{BASE}/openai/models").json()["models"][0]
    assert model["health_status"] == "error"
    assert model["health_error_code"] == "provider_unavailable"


def test_check_model_requires_synced_model(owner, mock_http):
    assert_error(
        owner.post(f"{BASE}/openai/models/gpt-4o-mini/check"),
        409, "credentials_missing",
    )
    saved(owner)
    _sync_model(owner, mock_http, "gpt-4o-mini")
    assert_error(
        owner.post(f"{BASE}/openai/models/other-model/check"),
        409, "model_not_synced",
    )
