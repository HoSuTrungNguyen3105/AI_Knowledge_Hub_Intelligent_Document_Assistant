"""Exercise the REAL HTTP auth/dashboard stack through Next.js or FastAPI.

Usage: python scripts/smoke_http.py --base-url http://localhost:3000
Creates one test account (not automatically deleted). No API keys required.
"""
import argparse
from http.cookiejar import CookieJar
import json
import secrets
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--origin", default="http://localhost:3000")
    options = parser.parse_args()
    base = options.base_url.rstrip("/") + "/api/v1"
    cookies = CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(method: str, path: str, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=body, method=method, headers={
            "Content-Type": "application/json", "Origin": options.origin,
        })
        try:
            response = client.open(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        content = response.read()
        return response.status, json.loads(content) if content else None

    email = f"smoke-{secrets.token_hex(5)}@example.com"
    password = secrets.token_urlsafe(20)
    status, _ = request("GET", "/health")
    assert status == 200, f"Health failed: HTTP {status}"
    status, data = request("POST", "/auth/register", {"name": "HTTP Smoke Test", "email": email, "password": password})
    assert status == 201, f"Register failed: HTTP {status}"
    user_id = data["user"]["id"]
    status, data = request("GET", "/auth/me")
    assert status == 200 and data["id"] == user_id, "Profile mismatch"
    assert not any(key in data for key in ("password_hash", "token_hash", "password", "access_token")), "Secret exposed"
    status, data = request("GET", "/dashboard")
    assert status == 200, "Dashboard failed"
    for key in ("total_documents", "total_knowledge_bases", "total_conversations", "ai_requests_usage"):
        assert data[key] == 0, f"Unexpected initial counter: {key}"
    assert data["recent_activity"], "Registration activity missing"
    old_refresh = next(cookie.value for cookie in cookies if cookie.name == "kh_refresh")
    status, _ = request("POST", "/auth/refresh", {})
    assert status == 200, "Refresh failed"
    new_refresh = next(cookie.value for cookie in cookies if cookie.name == "kh_refresh")
    assert old_refresh != new_refresh, "Refresh token did not rotate"
    status, _ = request("POST", "/auth/logout", {})
    assert status == 204, "Logout failed"
    status, _ = request("GET", "/auth/me")
    assert status == 401, "Profile still accessible after logout"
    status, _ = request("POST", "/auth/login", {"email": email, "password": password})
    assert status == 200, "Login failed"
    status, _ = request("POST", "/auth/logout", {})
    assert status == 204
    print("PASS: health, register, profile, dashboard, refresh rotation, logout, protected profile, login.")
    print(f"Created test account: {email}. No credentials printed.")


if __name__ == "__main__":
    main()
