"""Official REST contract mock tests, not live provider/key verification.

Fixture IDs deliberately say contract-only. Nothing in production uses these payloads.
MockTransport intercepts every request; assertions cover destination and auth headers.
"""

import asyncio
import json
import time

import httpx
import pytest
from pydantic import SecretStr

from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.http import HTTPLimits, ModelListingHTTP

KEY = SecretStr("contract-only-provider-key")
OPENAI_MODEL = {
    "id": "contract-only-openai-model",
    "object": "model",
    "created": 1700000000,
    "owned_by": "contract-owner",
    "shutdown_date": "2030-01-01",
}
# Groq is OpenAI-compatible but adds extra fields and uses "owner/model" ids.
GROQ_MODEL = {
    "id": "openai/gpt-oss-20b",
    "object": "model",
    "created": 1700000000,
    "owned_by": "OpenAI",
    "active": True,
    "context_window": 131072,
}


def adapter(provider, handler, **limits):
    return create_provider(
        provider,
        ModelListingHTTP(
            transport=httpx.MockTransport(handler),
            limits=HTTPLimits(**limits),
        ),
    )


def test_openai_contract_unknown_capabilities_and_fixed_endpoint():
    def handle(request):
        assert str(request.url) == "https://api.openai.com/v1/models"
        assert request.method == "GET"
        assert request.headers["authorization"] == f"Bearer {KEY.get_secret_value()}"
        assert not request.content
        return httpx.Response(200, json={"object": "list", "data": [OPENAI_MODEL]})

    model = adapter("openai", handle).list_models(KEY)[0]
    assert model.id == OPENAI_MODEL["id"]
    assert model.capabilities.model_dump() == dict.fromkeys(
        ["chat", "streaming", "tools", "embeddings"]
    )
    assert model.capability_source == "unknown"
    assert model.input_token_limit is model.output_token_limit is None


def test_groq_contract_openai_compatible_unknown_capabilities():
    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/models"
        assert request.method == "GET"
        assert request.headers["authorization"] == f"Bearer {KEY.get_secret_value()}"
        assert not request.content
        return httpx.Response(200, json={"object": "list", "data": [GROQ_MODEL]})

    model = adapter("groq", handle).list_models(KEY)[0]
    assert model.id == "openai/gpt-oss-20b"
    assert model.display_name == "openai/gpt-oss-20b"
    assert model.capabilities.model_dump() == dict.fromkeys(
        ["chat", "streaming", "tools", "embeddings"]
    )
    assert model.capability_source == "unknown"
    assert model.input_token_limit is model.output_token_limit is None


def test_gemini_contract_pagination_header_and_explicit_capabilities():
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/models"
        assert request.headers["x-goog-api-key"] == KEY.get_secret_value()
        assert "key" not in request.url.params
        assert 0 < int(request.url.params["pageSize"]) <= 1000
        if len(requests) == 1:
            assert "pageToken" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/contract-chat",
                            "displayName": "Contract chat",
                            "description": "Not a live model",
                            "inputTokenLimit": 100,
                            "outputTokenLimit": 50,
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ],
                    "nextPageToken": "contract-page-two",
                },
            )
        assert request.url.params["pageToken"] == "contract-page-two"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/contract-embed",
                        "supportedGenerationMethods": ["batchEmbedContents"],
                    },
                    {
                        "name": "models/contract-stream",
                        "supportedGenerationMethods": ["generateMessage", "streamGenerateContent"],
                    },
                    {"name": "models/contract-unknown"},
                ]
            },
        )

    models = adapter("gemini", handle).list_models(KEY)
    assert len(requests) == 2
    assert models[0].id == "contract-chat"
    assert models[0].input_token_limit == 100
    assert models[0].capabilities.model_dump() == {
        "chat": True,
        "streaming": None,
        "tools": None,
        "embeddings": False,
    }
    assert models[1].capabilities.embeddings is True
    assert models[1].capabilities.chat is False
    assert models[2].capabilities.streaming is True
    assert models[2].capabilities.tools is None
    assert models[3].capabilities.chat is None
    assert all(model.capability_source == "provider_metadata" for model in models)


@pytest.mark.parametrize(
    "provider,payload",
    [
        ("openai", {"object": "list", "data": []}),
        ("groq", {"object": "list", "data": []}),
        ("gemini", {}),
        ("gemini", {"models": []}),
    ],
)
def test_valid_empty_catalog_is_success(provider, payload):
    assert adapter(provider, lambda _: httpx.Response(200, json=payload)).list_models(KEY) == []


@pytest.mark.parametrize(
    "status,code,http_status",
    [
        (401, "provider_authentication_failed", 400),
        (403, "provider_authentication_failed", 400),
        (429, "provider_rate_limited", 429),
        (500, "provider_unavailable", 502),
        (503, "provider_unavailable", 502),
        (400, "invalid_provider_response", 502),
        (302, "invalid_provider_response", 502),
        (307, "invalid_provider_response", 502),
    ],
)
def test_http_errors_redacted_and_redirects_never_followed(status, code, http_status, caplog):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status,
            text=f"upstream-secret {KEY.get_secret_value()}",
            headers={
                "Location": "https://attacker.invalid/steal",
                "Retry-After": KEY.get_secret_value(),
            },
        )

    with pytest.raises(ProviderError) as error:
        adapter("openai", handle).list_models(KEY)
    assert len(requests) == 1
    assert error.value.code == code
    assert error.value.status_code == http_status
    assert KEY.get_secret_value() not in str(error.value) + caplog.text
    assert "upstream-secret" not in str(error.value) + caplog.text


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout, "provider_timeout"),
        (httpx.ConnectTimeout, "provider_timeout"),
        (httpx.ConnectError, "provider_unavailable"),
        (httpx.RemoteProtocolError, "provider_unavailable"),
    ],
)
def test_network_exception_text_never_exposed(exception, code, caplog):
    def handle(request):
        raise exception(KEY.get_secret_value(), request=request)

    with pytest.raises(ProviderError) as error:
        adapter("gemini", handle).list_models(KEY)
    assert error.value.code == code
    assert KEY.get_secret_value() not in str(error.value) + caplog.text


@pytest.mark.parametrize(
    "provider,payload",
    [
        ("openai", {}),
        ("openai", []),
        ("openai", {"object": "list", "data": [{"id": "incomplete"}]}),
        ("openai", {"object": "list", "data": [OPENAI_MODEL, OPENAI_MODEL]}),
        ("openai", {"object": "list", "data": [OPENAI_MODEL | {"created": "123"}]}),
        ("gemini", {"models": "wrong"}),
        ("gemini", {"models": [{"name": "invalid-name"}]}),
        ("gemini", {"error": {"message": "not a catalog"}}),
        ("gemini", {"unexpected": "not a catalog"}),
        ("gemini", {"nextPageToken": KEY.get_secret_value()}),
        ("gemini", {"models": [{"name": "models/id", "supportedGenerationMethods": [True]}]}),
        ("gemini", {"models": [{"name": "models/id", "inputTokenLimit": -1}]}),
        ("gemini", {"models": [{"name": "models/id", "outputTokenLimit": 2**32}]}),
        ("gemini", {"models": [{"name": "models/id", "description": KEY.get_secret_value()}]}),
    ],
)
def test_invalid_schemas_duplicates_and_echoed_keys(provider, payload):
    with pytest.raises(ProviderError) as error:
        adapter(provider, lambda _: httpx.Response(200, json=payload)).list_models(KEY)
    assert error.value.code == "invalid_provider_response"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, content=b"[]"),
        httpx.Response(200, content=b"{}", headers={"Content-Length": "999999999"}),
        httpx.Response(200, content=b"{}", headers={"Content-Length": "invalid"}),
    ],
)
def test_invalid_json_or_oversized_declared_body(response):
    with pytest.raises(ProviderError) as error:
        adapter("openai", lambda _: response).list_models(KEY)
    assert error.value.code == "invalid_provider_response"


def test_total_response_bytes_limit_across_pages():
    payload = {"models": [], "nextPageToken": "another-page"}
    size = len(json.dumps(payload).encode())
    count = 0

    def handle(_):
        nonlocal count
        count += 1
        return httpx.Response(200, content=json.dumps(payload).encode())

    with pytest.raises(ProviderError) as error:
        adapter("gemini", handle, max_response_bytes=size + 1).list_models(KEY)
    assert count == 2
    assert error.value.code == "invalid_provider_response"


@pytest.mark.parametrize("repeated", [True, False])
def test_repeated_tokens_and_page_cap(repeated):
    count = 0

    def handle(_):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"nextPageToken": "same" if repeated else str(count)})

    with pytest.raises(ProviderError) as error:
        adapter("gemini", handle, max_pages=3).list_models(KEY)
    assert count == (2 if repeated else 3)
    assert error.value.code == "invalid_provider_response"


def test_duplicate_models_across_gemini_pages():
    count = 0

    def handle(_):
        nonlocal count
        count += 1
        return httpx.Response(
            200,
            json={
                "models": [{"name": "models/same"}],
                "nextPageToken": str(count),
            },
        )

    with pytest.raises(ProviderError) as error:
        adapter("gemini", handle).list_models(KEY)
    assert count == 2
    assert error.value.code == "invalid_provider_response"


@pytest.mark.parametrize(
    "provider,payload",
    [
        ("openai", {"object": "list", "data": [OPENAI_MODEL]}),
        ("groq", {"object": "list", "data": [GROQ_MODEL]}),
        ("gemini", {"models": [{"name": "models/contract-id"}]}),
    ],
)
def test_model_count_bound(provider, payload):
    with pytest.raises(ProviderError):
        adapter(provider, lambda _: httpx.Response(200, json=payload), max_models=0).list_models(
            KEY
        )


def test_whole_sync_deadline_cancels_slow_body_without_waiting_for_inactivity_timeout():
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b" "
                await asyncio.sleep(0.01)  # Simulated trickle; not a retry/poll loop.

    started = time.monotonic()
    with pytest.raises(ProviderError) as error:
        adapter(
            "openai", lambda _: httpx.Response(200, stream=SlowBody()), deadline_seconds=0.05
        ).list_models(KEY)
    assert error.value.code == "provider_timeout"
    assert time.monotonic() - started < 1


def test_deadline_does_not_wait_for_uncancellable_dns_executor():
    from threading import Event

    release = Event()

    async def handle(_):
        # OS DNS resolution can outlive coroutine cancellation. This executor
        # fixture reproduces that without using a real resolver or network.
        await asyncio.get_running_loop().run_in_executor(None, release.wait, 2)
        return httpx.Response(200, json={"object": "list", "data": []})

    started = time.monotonic()
    try:
        with pytest.raises(ProviderError) as error:
            adapter("openai", handle, deadline_seconds=0.05).list_models(KEY)
        assert error.value.code == "provider_timeout"
        assert time.monotonic() - started < 1
    finally:
        release.set()


def test_deadline_covers_all_pages_not_each_page():
    requests = 0

    async def handle(_):
        nonlocal requests
        requests += 1
        await asyncio.sleep(0.02)  # Contract mock latency, not a production retry.
        return httpx.Response(200, json={"nextPageToken": str(requests)})

    with pytest.raises(ProviderError) as error:
        adapter("gemini", handle, deadline_seconds=0.05).list_models(KEY)
    assert error.value.code == "provider_timeout"
    assert requests < 20


def test_streamed_body_limit_without_content_length():
    class LargeBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b" " * 20
            yield b" " * 20

    with pytest.raises(ProviderError) as error:
        adapter(
            "openai", lambda _: httpx.Response(200, stream=LargeBody()), max_response_bytes=30
        ).list_models(KEY)
    assert error.value.code == "invalid_provider_response"
