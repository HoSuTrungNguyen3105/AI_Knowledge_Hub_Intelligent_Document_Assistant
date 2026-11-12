from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import jwt
import pytest
from conftest import PASSWORD

from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    verify_password,
)
from app.models.base import utcnow
from app.repositories.auth import AuthRepository


@pytest.mark.asyncio
async def test_register_normalizes_and_stores_only_hashes(client, register, db, settings):
    response = register(client, email="  PERSON@Example.COM  ")
    assert response.status_code == 201
    assert set(response.json()) == {"user"}
    user = response.json()["user"]
    assert set(user) == {"id", "name", "email", "created_at"}
    assert user["name"] == "Test Person"
    assert user["email"] == "person@example.com"
    assert datetime.fromisoformat(user["created_at"]).utcoffset() == timedelta(0)
    stored = await db.users.find_one({"_id": UUID(user["id"])})
    assert stored["password_hash"].startswith("$argon2id$")
    assert verify_password(PASSWORD, stored["password_hash"])
    token = await db.refresh_tokens.find_one({})
    raw_refresh = client.cookies.get(REFRESH_COOKIE)
    assert token["token_hash"] == hash_refresh_token(raw_refresh)
    assert len(token["token_hash"]) == 64
    assert len(raw_refresh) >= 43
    assert token["token_hash"] != raw_refresh
    assert timedelta(days=6, hours=23) < token["expires_at"] - utcnow() <= timedelta(days=7)
    assert decode_access_token(client.cookies.get(ACCESS_COOKIE), settings) == (
        stored["_id"],
        token["_id"],
    )
    claims = jwt.decode(client.cookies.get(ACCESS_COOKIE), options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60
    for secret in (PASSWORD, stored["password_hash"], token["token_hash"], raw_refresh):
        assert secret not in response.text
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == user
    assert me.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "invalid"},
        {"email": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"password": "x" * 9},
        {"password": "x" * 129},
        {"password": None},
        {"name": None},
        {"role": "admin"},
    ],
)
def test_registration_validation_does_not_echo_password(client, changes):
    payload = {"name": "User", "email": "user@example.com", "password": PASSWORD, **changes}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert PASSWORD not in response.text
    assert all("input" not in error for error in response.json()["detail"])


@pytest.mark.parametrize("password", ["a" * 10, "b" * 128])
def test_password_length_boundaries(client, register, password):
    assert register(client, password=password).status_code == 201
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "person@example.com", "password": password}
        ).status_code
        == 200
    )


@pytest.mark.asyncio
async def test_duplicate_email_and_failed_transaction_recovery(client, register, db, monkeypatch):
    assert register(client).status_code == 201
    assert register(client, email="PERSON@example.com").status_code == 409
    original = AuthRepository.user_by_email
    calls = 0

    async def registration_race(repository, email):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await original(repository, email)

    monkeypatch.setattr(AuthRepository, "user_by_email", registration_race)
    response = register(client)
    assert response.status_code == 409
    assert "INSERT" not in response.text
    assert await db.users.count_documents({}) == 1
    assert await db.refresh_tokens.count_documents({}) == 1
    assert await db.activity_logs.count_documents({}) == 1
    assert register(client, email="another@example.com").status_code == 201


@pytest.mark.asyncio
async def test_login_normalized_and_generic_invalid_credentials(client, register, db):
    register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": " PERSON@EXAMPLE.COM ", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "person@example.com"
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "person@example.com", "password": "wrong-password"}
    )
    missing = client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong-password"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json() == {"detail": "Invalid email or password"}
    assert await db.refresh_tokens.count_documents({}) == 2
    cursor = db.activity_logs.find({}).sort("created_at")
    activities = [doc["action"] async for doc in cursor]
    assert activities == ["auth.register", "auth.login"]


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/dashboard"])
def test_protected_routes_reject_missing_and_invalid_access(client, path):
    assert client.get(path).status_code == 401
    client.cookies.set(ACCESS_COOKIE, "not-a-jwt", path="/api/v1")
    assert client.get(path).status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotation_and_replay(client, client_factory, register, db):
    register(client)
    first = client.cookies.get(REFRESH_COOKIE)
    old_access = client.cookies.get(ACCESS_COOKIE)
    session = await db.refresh_tokens.find_one({})
    session_id = session["_id"]
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    second = client.cookies.get(REFRESH_COOKIE)
    assert second != first
    assert client.cookies.get(ACCESS_COOKIE) != old_access
    updated_session = await db.refresh_tokens.find_one({"_id": session_id})
    assert updated_session["_id"] == session_id
    assert updated_session["token_hash"] == hash_refresh_token(second)
    replay = client_factory()
    replay.cookies.set(REFRESH_COOKIE, first, path="/api/v1/auth")
    assert replay.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_concurrent_refresh_has_exactly_one_winner(client, client_factory, register):
    register(client)
    token = client.cookies.get(REFRESH_COOKIE)
    peers = [client_factory(), client_factory()]
    for peer in peers:
        peer.cookies.set(REFRESH_COOKIE, token, path="/api/v1/auth")
    barrier = Barrier(2)

    def refresh(peer):
        barrier.wait(timeout=5)
        return peer.post("/api/v1/auth/refresh").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(refresh, peers)) == [200, 401]


@pytest.mark.parametrize("token", [None, "invalid", "x" * 513])
def test_refresh_rejects_missing_or_invalid_cookie(client, token):
    if token:
        client.cookies.set(REFRESH_COOKIE, token, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


@pytest.mark.asyncio
async def test_expired_session_rejects_access_and_refresh(client, register, db):
    register(client)
    await db.refresh_tokens.update_many(
        {}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}}
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


@pytest.mark.asyncio
async def test_expired_access_can_refresh(client, register, settings):
    register(client)
    refresh = client.cookies.get(REFRESH_COOKIE)
    claims = jwt.decode(client.cookies.get(ACCESS_COOKIE), options={"verify_signature": False})
    claims["exp"] = utcnow() - timedelta(seconds=1)
    expired = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    client.cookies.clear()
    client.cookies.set(ACCESS_COOKIE, expired, path="/api/v1")
    client.cookies.set(REFRESH_COOKIE, refresh, path="/api/v1/auth")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 200


@pytest.mark.asyncio
async def test_access_requires_matching_active_session(client, register, settings, db):
    user = register(client).json()["user"]
    session = await db.refresh_tokens.find_one({})
    for user_id, session_id in [(UUID(user["id"]), uuid4()), (uuid4(), session["_id"])]:
        client.cookies.clear()
        client.cookies.set(
            ACCESS_COOKIE, create_access_token(user_id, session_id, settings), path="/api/v1"
        )
        assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("cookies", ["both", "access", "refresh", "expired_access"])
@pytest.mark.asyncio
async def test_logout_revokes_and_clears_cookies(
    client, client_factory, register, settings, db, cookies
):
    register(client)
    access, refresh = client.cookies.get(ACCESS_COOKIE), client.cookies.get(REFRESH_COOKIE)
    client.cookies.clear()
    if cookies in {"both", "access", "expired_access"}:
        logout_access = access
        if cookies == "expired_access":
            claims = jwt.decode(access, options={"verify_signature": False})
            claims["exp"] = utcnow() - timedelta(seconds=1)
            logout_access = jwt.encode(
                claims, settings.jwt_secret.get_secret_value(), algorithm="HS256"
            )
        client.cookies.set(ACCESS_COOKIE, logout_access, path="/api/v1")
    if cookies in {"both", "refresh"}:
        client.cookies.set(REFRESH_COOKIE, refresh, path="/api/v1/auth")
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert len(response.headers.get_list("set-cookie")) == 2
    assert all("Max-Age=0" in cookie for cookie in response.headers.get_list("set-cookie"))
    session = await db.refresh_tokens.find_one({})
    assert session["revoked_at"] is not None
    stale = client_factory()
    stale.cookies.set(ACCESS_COOKIE, access, path="/api/v1")
    stale.cookies.set(REFRESH_COOKIE, refresh, path="/api/v1/auth")
    assert stale.get("/api/v1/auth/me").status_code == 401
    assert stale.post("/api/v1/auth/refresh").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_logout_without_valid_session_is_idempotent(client):
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set(ACCESS_COOKIE, "bad", path="/api/v1")
    client.cookies.set(REFRESH_COOKIE, "bad", path="/api/v1/auth")
    assert client.post("/api/v1/auth/logout").status_code == 204