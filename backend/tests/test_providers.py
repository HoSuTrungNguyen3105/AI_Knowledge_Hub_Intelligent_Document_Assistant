"""Authenticated API contract mock tests, not live provider verification.

The existing SQLite/session/auth fixtures are reused. provider_settings supplies an
isolated, generated Fernet key. mock_http overrides only outbound model-listing I/O.
"""

from io import StringIO
from pathlib import Path

import httpx
import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select

from alembic import command
from app.api.v1.providers import provider_http
from app.core.credential_vault import CredentialVault
from app.models import AIModel, AIRequest, Conversation, User, UserProviderCredential
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
        ("anthropic", "Anthropic Claude", False),
        ("deepseek", "DeepSeek", False),
        ("ollama", "Ollama", False),
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


@pytest.mark.parametrize("slug", ["anthropic", "deepseek", "ollama", "unknown"])
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


def test_save_encrypts_at_rest_and_never_returns_credential_fields(owner, db, settings):
    result = saved(owner, api_key="  " + KEY + "  ")
    assert result["configured"] and result["enabled"]
    assert result["connection_status"] == "untested"
    credential = db.scalar(select(UserProviderCredential))
    assert KEY not in credential.encrypted_api_key
    assert (
        CredentialVault(settings.credential_encryption_key)
        .decrypt(credential.encrypted_api_key, credential.user_id, credential.provider)
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
    assert str(credential.id) not in owner.get(BASE).text
    assert credential.encrypted_api_key not in owner.get(BASE).text
    assert owner.patch(f"{BASE}/openai", json={"enabled": False}).json()["enabled"] is False


def test_read_only_connection_sync_even_when_disabled_and_default_validation(owner, mock_http, db):
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
    assert db.scalar(select(func.count()).select_from(AIRequest)) == 0


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


def test_owner_isolation_delete_cascade_and_conversations_preserved(
    owner, client_factory, register, db, mock_http
):
    saved(owner)
    owner.post(f"{BASE}/openai/test")
    first_user = db.scalar(select(User))
    conversation = Conversation(
        user_id=first_user.id, title="Existing conversation", provider="openai", model=MODEL["id"]
    )
    db.add(conversation)
    db.commit()
    second = client_factory()
    register(second, email="another@example.com")
    assert not metadata(second)["configured"]
    assert second.get(f"{BASE}/openai/models").json()["models"] == []
    assert_error(second.post(f"{BASE}/openai/test"), 409, "credentials_missing")
    assert second.delete(f"{BASE}/openai").status_code == 204
    assert metadata(owner)["model_count"] == 1
    saved(second, api_key="other-contract-key")
    assert_error(
        second.patch(f"{BASE}/openai", json={"default_model": MODEL["id"]}),
        409,
        "invalid_default_model",
    )
    second.post(f"{BASE}/openai/test")
    for _ in range(2):
        response = owner.delete(f"{BASE}/openai")
        assert response.status_code == 204 and not response.content
    assert metadata(second)["configured"]
    assert metadata(second)["model_count"] == 1
    assert db.scalar(select(func.count()).select_from(UserProviderCredential)) == 1
    assert db.scalar(select(func.count()).select_from(AIModel)) == 1
    assert db.get(Conversation, conversation.id) is not None
    assert owner.get("/api/v1/dashboard").json()["total_conversations"] == 1


def test_swapped_owner_ciphertext_never_reaches_upstream(
    owner,
    client_factory,
    register,
    db,
    mock_http,
):
    saved(owner)
    original = db.scalar(select(UserProviderCredential))
    second = client_factory()
    register(second, email="ciphertext-swap@example.com")
    saved(second, api_key="second-contract-secret")
    other = db.scalar(
        select(UserProviderCredential).where(UserProviderCredential.user_id != original.user_id)
    )
    other.encrypted_api_key = original.encrypted_api_key
    db.commit()

    def forbidden(_):
        pytest.fail("A mismatched owner binding must never send credentials upstream")

    mock_http(forbidden)
    assert_error(second.post(f"{BASE}/openai/test"), 503, "encryption_unavailable")
    assert metadata(owner)["last_error_code"] is None


def test_cache_and_metadata_roll_back_atomically_on_database_failure(
    owner,
    mock_http,
    monkeypatch,
    caplog,
):
    from sqlalchemy.exc import SQLAlchemyError

    from app.repositories.providers import ProviderRepository

    saved(owner)
    owner.post(f"{BASE}/openai/test")
    before = metadata(owner)
    cache = owner.get(f"{BASE}/openai/models").json()

    def fail(repository, credential_id, _models):
        repository.clear_models(credential_id)
        raise SQLAlchemyError(KEY)

    monkeypatch.setattr(ProviderRepository, "replace_models", fail)
    assert_error(owner.post(f"{BASE}/openai/test"), 503, "database_unavailable")
    assert metadata(owner) == before
    assert owner.get(f"{BASE}/openai/models").json() == cache
    assert KEY not in caplog.text


def test_unexpected_provider_error_is_safe_and_not_cached(
    owner,
    client_factory,
    monkeypatch,
    caplog,
):
    from app.services.providers import ProviderService

    def fail(_service, _user_id):
        raise RuntimeError(KEY)

    monkeypatch.setattr(ProviderService, "catalog", fail)
    safe_client = client_factory(raise_server_exceptions=False)
    safe_client.cookies.update(owner.cookies)
    assert_error(safe_client.get(BASE), 500, "internal_server_error")
    assert KEY not in caplog.text


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


def test_migration_0002_offline_postgresql_and_scoped_downgrade():
    backend = Path(__file__).resolve().parents[1]
    output = StringIO()
    command.upgrade(
        Config(str(backend / "alembic.ini"), output_buffer=output),
        "0001_phase_one:0002_provider_management",
        sql=True,
    )
    sql = output.getvalue()
    assert "CREATE TABLE user_provider_credentials" in sql
    assert "CREATE TABLE ai_models" in sql
    assert "JSONB" in sql
    assert "UNIQUE (user_id, provider)" in sql
    assert "UNIQUE (credential_id, model_id)" in sql
    assert "CREATE TABLE users" not in sql
    output = StringIO()
    command.downgrade(
        Config(str(backend / "alembic.ini"), output_buffer=output),
        "0002_provider_management:0001_phase_one",
        sql=True,
    )
    assert "DROP TABLE ai_models" in output.getvalue()
    assert "DROP TABLE user_provider_credentials" in output.getvalue()
    assert "DROP TABLE conversations" not in output.getvalue()
