"""Offline contracts for provider-reported rate limits.

The numbers shown in MindFlow must be the provider's own, read from
the x-ratelimit-* headers of a real chat response — never an internal
estimate. These tests pin the header parsing, the capture-to-record
persistence path, and the read endpoint's honest empty state.
"""

from uuid import UUID

from app.repositories.chat import ChatRepository
from app.services.ai.rate_limits import note_rate_limit, parse_rate_limit_headers

BASE = "/api/v1/ai/providers/rate-limits"
MODEL = "openai/gpt-oss-120b"

GROQ_HEADERS = {
    "x-ratelimit-limit-requests": "30",
    "x-ratelimit-remaining-requests": "29",
    "x-ratelimit-reset-requests": "0.5s",
    "x-ratelimit-limit-tokens": "8000",
    "x-ratelimit-remaining-tokens": "7900",
    "x-ratelimit-reset-tokens": "0.5s",
    "x-ratelimit-limit-requests-day": "1000",
    "x-ratelimit-remaining-requests-day": "987",
    "x-ratelimit-reset-requests-day": "2h35m10s",
    "x-ratelimit-limit-tokens-day": "200000",
    "x-ratelimit-remaining-tokens-day": "180000",
    "x-ratelimit-reset-tokens-day": "2h35m10s",
}


def test_parse_extracts_known_fields():
    snapshot = parse_rate_limit_headers(GROQ_HEADERS)
    assert snapshot["limit_requests"] == 30
    assert snapshot["remaining_requests_day"] == 987
    assert snapshot["remaining_tokens_day"] == 180000
    assert snapshot["reset_requests_day"] == "2h35m10s"


def test_parse_returns_none_without_headers():
    assert parse_rate_limit_headers({}) is None
    assert parse_rate_limit_headers(None) is None
    assert parse_rate_limit_headers({"content-type": "text/event-stream"}) is None


def test_parse_skips_unparseable_counts():
    snapshot = parse_rate_limit_headers(
        {"x-ratelimit-limit-requests": "soon", "x-ratelimit-remaining-requests": "3"}
    )
    assert snapshot == {"remaining_requests": 3}


async def test_endpoint_requires_auth(client):
    assert client.get(BASE).status_code == 401


async def test_endpoint_empty_until_a_call_is_recorded(client, register):
    assert register(client).status_code == 201
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"snapshots": []}


async def test_recorded_call_persists_provider_snapshot(client, register, db):
    assert register(client).status_code == 201
    user_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    note_rate_limit("groq", MODEL, GROQ_HEADERS)
    await ChatRepository(db).record_request(
        user_id, provider="groq", model=MODEL, status="success"
    )
    response = client.get(BASE)
    assert response.status_code == 200
    snapshots = response.json()["snapshots"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["provider"] == "groq"
    assert snapshot["model"] == MODEL
    assert snapshot["remaining_requests_day"] == 987
    assert snapshot["limit_tokens_day"] == 200000
    assert snapshot["captured_at"]


async def test_recorded_call_without_headers_stores_nothing(client, register, db):
    assert register(client).status_code == 201
    user_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await ChatRepository(db).record_request(
        user_id, provider="ollama", model="kimi-k2.7-code", status="error"
    )
    assert client.get(BASE).json() == {"snapshots": []}
