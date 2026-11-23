import pytest
from conftest import ORIGIN, PASSWORD

from app.core.middleware import RateLimiter
from app.core.security import ACCESS_COOKIE, REFRESH_COOKIE
from app.repositories.auth import AuthRepository
from app.services.auth import AuthService


@pytest.mark.parametrize("secure", [False, True])
def test_cookie_flags_and_scopes(client_factory, settings, register, secure):
    settings.cookie_secure = secure
    client = client_factory(base_url="https://testserver" if secure else "http://testserver")
    response = register(client)
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert ("Secure" in cookie) is secure
        assert "Domain=" not in cookie
    assert any(f"{ACCESS_COOKIE}=" in cookie and "Path=/api/v1;" in cookie for cookie in cookies)
    assert any(
        f"{REFRESH_COOKIE}=" in cookie and "Path=/api/v1/auth;" in cookie for cookie in cookies
    )
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 200
    logout = client.post("/api/v1/auth/logout")
    for cookie in logout.headers.get_list("set-cookie"):
        assert "Max-Age=0" in cookie
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert ("Secure" in cookie) is secure
    assert client.cookies.get(ACCESS_COOKIE) is None
    assert client.cookies.get(REFRESH_COOKIE) is None


@pytest.mark.parametrize(
    "origin", ["https://attacker.example", "null", "http://localhost:3000.evil"]
)
def test_csrf_rejects_untrusted_origin_without_cookies(client, register, origin):
    client.headers["Origin"] = origin
    assert register(client).status_code == 403


@pytest.mark.parametrize("path", ["register", "login", "refresh", "logout"])
def test_csrf_rejects_cookie_request_without_origin(client, register, path):
    register(client)
    del client.headers["Origin"]
    response = client.post(f"/api/v1/auth/{path}", json={})
    assert response.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_csrf_blocks_foreign_origin_with_cookies_and_allows_server_clients(client, register):
    del client.headers["Origin"]
    assert register(client).status_code == 201  # No Origin and no Cookie is a server client.
    assert client.post("/api/v1/auth/refresh").status_code == 403
    client.headers["Origin"] = "https://attacker.example"
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers["Origin"] = ORIGIN
    assert client.post("/api/v1/auth/refresh").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_cors_explicit_allowlist(client):
    allowed = client.options(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    rejected = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_auth_rate_limit_ignores_spoofed_client_ip(client, settings):
    settings.auth_rate_limit = 2
    settings.api_rate_limit = 100
    for number in range(2):
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"X-Forwarded-For": f"192.0.2.{number}"}
            ).status_code
            == 204
        )
    blocked = client.post("/api/v1/auth/logout", headers={"X-Forwarded-For": "198.51.100.99"})
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert client.get("/api/v1/health").status_code == 200


def test_general_api_rate_limit(client, settings):
    settings.api_rate_limit = 3
    for _ in range(3):
        assert client.get("/api/v1/health").status_code == 200
    blocked = client.get("/api/v1/health")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_rate_limit_window_expiry_and_client_isolation(settings):
    settings.api_rate_limit = 1
    limiter = RateLimiter(settings)
    assert limiter.check("192.0.2.1", auth=False, now=0) is None
    assert limiter.check("192.0.2.1", auth=False, now=1) == 59
    assert limiter.check("192.0.2.2", auth=False, now=1) is None
    assert limiter.check("192.0.2.1", auth=False, now=60) is None


def test_safe_database_error_response(client, monkeypatch):
    from pymongo.errors import ConnectionFailure

    async def fail(_repository, _email):
        raise ConnectionFailure("secret-db-password")

    monkeypatch.setattr(AuthRepository, "user_by_email", fail)
    response = client.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "secret" not in response.text


def test_safe_unexpected_error(client_factory, monkeypatch):
    def fail(_service, _payload):
        raise RuntimeError("internal secret")

    monkeypatch.setattr(AuthService, "login", fail)
    client = client_factory(raise_server_exceptions=False)
    response = client.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_openapi_has_only_implemented_routes_and_safe_responses(app):
    schema = app.openapi()
    assert set(schema["paths"]) == {
        "/api/v1/ai/providers",
        "/api/v1/ai/providers/{provider}",
        "/api/v1/ai/providers/{provider}/test",
        "/api/v1/ai/providers/{provider}/models",
        "/api/v1/ai/chat/conversations",
        "/api/v1/ai/chat/conversations/{conversation_id}",
        "/api/v1/ai/chat/conversations/{conversation_id}/messages",
        "/api/v1/ai/chat/conversations/{conversation_id}/regenerate",
        "/api/v1/ai/compare/comparisons",
        "/api/v1/ai/compare/comparisons/{comparison_id}",
        "/api/v1/ai/compare/comparisons/{comparison_id}/execute",
        "/api/v1/ai/compare/comparisons/{comparison_id}/synthesize",
        "/api/v1/ai/agents/tools",
        "/api/v1/ai/agents",
        "/api/v1/ai/agents/{agent_id}",
        "/api/v1/ai/agents/{agent_id}/duplicate",
        "/api/v1/ai/agents/{agent_id}/executions",
        "/api/v1/ai/agents/{agent_id}/executions/{execution_id}",
        "/api/v1/ai/agents/{agent_id}/run",
        "/api/v1/ai/agent-teams",
        "/api/v1/ai/agent-teams/{team_id}",
        "/api/v1/ai/agent-workflows",
        "/api/v1/ai/agent-workflows/{workflow_id}",
        "/api/v1/ai/agent-workflows/{workflow_id}/start",
        "/api/v1/ai/agent-workflows/{workflow_id}/pause",
        "/api/v1/ai/agent-workflows/{workflow_id}/resume",
        "/api/v1/ai/agent-workflows/{workflow_id}/cancel",
        "/api/v1/ai/agent-workflows/{workflow_id}/files",
        "/api/v1/ai/agent-workflows/{workflow_id}/download.zip",
        "/api/v1/ai/agent-workflows/{workflow_id}/messages",
        "/api/v1/ai/agent-workflows/{workflow_id}/tasks",
        "/api/v1/ai/agent-workflows/{workflow_id}/events",
        "/api/v1/ai/agent-workflows/{workflow_id}/stream",
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/dashboard",
    }
    for name in ["UserResponse", "AuthResponse", "DashboardResponse", "ActivityResponse"]:
        response_schema = str(schema["components"]["schemas"][name]).lower()
        assert "password" not in response_schema
        assert "token" not in response_schema
        assert "storage_path" not in response_schema