"""Chat generation contract mock tests, not live provider/key verification.

MockTransport intercepts every request; assertions cover destination, auth and
payload shape. Fixture text deliberately says contract-only. Nothing here proves
a real generation succeeded; live verification is documented separately.
"""

import asyncio
import json
import time

import httpx
import pytest
from pydantic import SecretStr

from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP, ChatLimits
from app.services.ai.chat_types import ChatRequest, ChatTurn, ToolCall, ToolSpec

KEY = SecretStr("contract-only-chat-key")
REQ = ChatRequest(model="test-model", turns=(ChatTurn("user", "Hello"),))
TOOL = ToolSpec(
    name="calculator",
    description="Evaluate arithmetic.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
)
TOOL_REQ = ChatRequest(
    model="test-model", turns=(ChatTurn("user", "What is 2+2?"),), tools=(TOOL,)
)


def adapter(provider, handler, **limits):
    return create_provider(
        provider,
        chat_http=ChatHTTP(transport=httpx.MockTransport(handler), limits=ChatLimits(**limits)),
    )


def sse(*events):
    parts = []
    for event in events:
        data = "[DONE]" if event == "[DONE]" else json.dumps(event)
        parts.append(f"data: {data}\n\n")
    return "".join(parts)


def openai_chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


async def collect(provider, handler, request=REQ, **limits):
    return [event async for event in adapter(provider, handler, **limits).stream_chat(KEY, request)]


def test_openai_chat_contract_endpoint_auth_and_payload():
    def handle(request):
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {KEY.get_secret_value()}"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert body["messages"] == [{"role": "user", "content": "Hello"}]
        return httpx.Response(
            200,
            text=sse(
                openai_chunk("Hel"),
                openai_chunk("lo"),
                {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("openai", handle))
    deltas = [e.text for e in events if e.kind == "delta"]
    assert deltas == ["Hel", "lo"]
    usage = [e for e in events if e.kind == "usage"][-1]
    assert (usage.input_tokens, usage.output_tokens) == (5, 2)


def test_groq_chat_uses_groq_endpoint_and_bearer():
    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY.get_secret_value()}"
        return httpx.Response(200, text=sse(openai_chunk("ok"), "[DONE]"))

    events = asyncio.run(collect("groq", handle))
    assert [e.text for e in events if e.kind == "delta"] == ["ok"]


def test_gemini_chat_contract_endpoint_header_and_payload():
    def handle(request):
        assert request.url.scheme == "https"
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/models/test-model:streamGenerateContent"
        assert request.headers["x-goog-api-key"] == KEY.get_secret_value()
        assert request.url.params["alt"] == "sse"
        assert "key" not in request.url.params
        body = json.loads(request.content)
        assert body["contents"] == [{"role": "user", "parts": [{"text": "Hello"}]}]
        return httpx.Response(
            200,
            text=sse(
                {"candidates": [{"content": {"parts": [{"text": "Hi"}]}}]},
                {
                    "candidates": [{"content": {"parts": [{"text": " there"}]}}],
                    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
                },
            ),
        )

    events = asyncio.run(collect("gemini", handle))
    assert [e.text for e in events if e.kind == "delta"] == ["Hi", " there"]
    usage = [e for e in events if e.kind == "usage"][-1]
    assert (usage.input_tokens, usage.output_tokens) == (3, 4)


def test_system_prompt_temperature_and_token_limit_forwarded():
    request = ChatRequest(
        model="test-model",
        turns=(ChatTurn("user", "Hi"),),
        system_prompt="Be brief.",
        temperature=0.5,
        max_output_tokens=128,
    )

    def handle(request_):
        body = json.loads(request_.content)
        assert body["messages"][0] == {"role": "system", "content": "Be brief."}
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 128
        return httpx.Response(200, text=sse("[DONE]"))

    assert asyncio.run(collect("openai", handle, request=request)) == []


def test_gemini_system_instruction_and_generation_config():
    request = ChatRequest(
        model="test-model",
        turns=(ChatTurn("user", "Hi"), ChatTurn("assistant", "Hey")),
        system_prompt="Be brief.",
        temperature=0.2,
        max_output_tokens=64,
    )

    def handle(request_):
        body = json.loads(request_.content)
        assert body["systemInstruction"] == {"parts": [{"text": "Be brief."}]}
        assert body["generationConfig"] == {"temperature": 0.2, "maxOutputTokens": 64}
        assert body["contents"][1]["role"] == "model"
        return httpx.Response(200, text=sse({"candidates": []}))

    assert asyncio.run(collect("gemini", handle, request=request)) == []


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "provider_authentication_failed"),
        (403, "provider_authentication_failed"),
        (429, "provider_rate_limited"),
        (500, "provider_unavailable"),
        (503, "provider_unavailable"),
        (400, "provider_request_rejected"),
        (302, "generation_failed"),
        (307, "generation_failed"),
    ],
)
def test_chat_http_errors_redacted_and_redirects_never_followed(status, code, caplog):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status,
            text=f"upstream-secret {KEY.get_secret_value()}",
            headers={"Location": "https://attacker.invalid/steal"},
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle))
    assert len(requests) == 1
    assert error.value.code == code
    assert KEY.get_secret_value() not in str(error.value) + caplog.text
    assert "upstream-secret" not in str(error.value) + caplog.text


TOOL_ERROR_BODY = {
    "error": {
        "code": "tool_use_failed",
        "message": "The model 'test-model' does not support tool use.",
        "type": "invalid_request_error",
    }
}


def test_chat_http_400_tool_error_maps_to_model_tools_unsupported(caplog):
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("groq", lambda _: httpx.Response(400, json=TOOL_ERROR_BODY)))
    assert error.value.code == "model_tools_unsupported"
    assert KEY.get_secret_value() not in str(error.value) + caplog.text


def test_chat_http_400_other_error_maps_to_provider_request_rejected():
    body = {"error": {"code": "invalid_value", "message": "max_tokens must be positive."}}
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", lambda _: httpx.Response(400, json=body)))
    assert error.value.code == "provider_request_rejected"


def test_chat_http_400_non_json_body_maps_to_provider_request_rejected(caplog):
    def handle(request):
        return httpx.Response(400, text=f"bad request {KEY.get_secret_value()}")

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle))
    assert error.value.code == "provider_request_rejected"
    assert KEY.get_secret_value() not in str(error.value) + caplog.text


def test_sse_error_event_with_tool_blame_raises_model_tools_unsupported():
    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "error": {
                        "message": "Function calling is not supported for this model.",
                        "type": "invalid_request_error",
                    }
                },
                "[DONE]",
            ),
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("groq", handle))
    assert error.value.code == "model_tools_unsupported"


def test_sse_error_event_without_tool_blame_raises_provider_request_rejected():
    def handle(request):
        return httpx.Response(
            200, text=sse({"error": {"message": "Context length exceeded."}}, "[DONE]")
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle))
    assert error.value.code == "provider_request_rejected"


def test_gemini_sse_error_event_raises_classified_code():
    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "error": {
                        "code": 400,
                        "message": "Tool use is not supported.",
                        "status": "INVALID_ARGUMENT",
                    }
                },
                "[DONE]",
            ),
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("gemini", handle))
    assert error.value.code == "model_tools_unsupported"


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout, "provider_timeout"),
        (httpx.ConnectTimeout, "provider_timeout"),
        (httpx.ConnectError, "provider_unavailable"),
        (httpx.RemoteProtocolError, "provider_unavailable"),
    ],
)
def test_chat_network_exception_text_never_exposed(exception, code, caplog):
    def handle(request):
        raise exception(KEY.get_secret_value(), request=request)

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("gemini", handle))
    assert error.value.code == code
    assert KEY.get_secret_value() not in str(error.value) + caplog.text


def test_echoed_credential_in_delta_is_rejected():
    def handle(request):
        return httpx.Response(200, text=sse(openai_chunk(KEY.get_secret_value()), "[DONE]"))

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle))
    assert error.value.code == "generation_failed"


def test_credential_split_across_events_is_rejected():
    secret = KEY.get_secret_value()
    half = len(secret) // 2

    def handle(request):
        return httpx.Response(
            200, text=sse(openai_chunk(secret[:half]), openai_chunk(secret[half:]), "[DONE]")
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle))
    assert error.value.code == "generation_failed"


@pytest.mark.parametrize("body", ["data: not json\n\n", "data: [1,2,3]\n\n"])
def test_invalid_sse_payload_rejected(body):
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", lambda _: httpx.Response(200, text=body)))
    assert error.value.code == "generation_failed"


def test_response_byte_limit():
    with pytest.raises(ProviderError) as error:
        asyncio.run(
            collect("openai", lambda _: httpx.Response(200, text=sse(openai_chunk("x" * 50))),
                    max_response_bytes=10)
        )
    assert error.value.code == "generation_failed"


def test_declared_content_length_over_limit():
    response = httpx.Response(
        200, text=sse("[DONE]"), headers={"Content-Length": "999999999"}
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", lambda _: response))
    assert error.value.code == "generation_failed"


def test_compressed_response_rejected():
    # Use a raw stream so httpx does not eagerly gzip-decode at construction;
    # the app must reject the declared content-encoding before reading the body.
    response = httpx.Response(
        200,
        stream=httpx.ByteStream(b"data: [DONE]\n\n"),
        headers={"Content-Encoding": "gzip"},
    )
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", lambda _: response))
    assert error.value.code == "generation_failed"


def test_chat_deadline_cancels_slow_body():
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b"data: " + b" " * 8
                await asyncio.sleep(0.01)

    started = time.monotonic()
    with pytest.raises(ProviderError) as error:
        asyncio.run(
            collect("openai", lambda _: httpx.Response(200, stream=SlowBody()),
                    deadline_seconds=0.05)
        )
    assert error.value.code == "provider_timeout"
    assert time.monotonic() - started < 1


def test_malformed_upstream_chunks_are_tolerated_without_crashing():
    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {"choices": "wrong"},
                {"choices": [{"delta": {"content": 123}}]},
                {"choices": [{"delta": {"content": "valid"}}]},
                {"usage": {"prompt_tokens": "bad", "completion_tokens": -1}},
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("openai", handle))
    assert [e.text for e in events if e.kind == "delta"] == ["valid"]
    usage = [e for e in events if e.kind == "usage"][-1]
    assert usage.input_tokens is None and usage.output_tokens is None


# --- Function calling (Phase 5). Contract-only; no live tool execution here. ---


def test_openai_forwards_tools_and_accumulates_streamed_tool_calls():
    def handle(request):
        body = json.loads(request.content)
        assert body["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Evaluate arithmetic.",
                    "parameters": TOOL.parameters,
                },
            }
        ]
        return httpx.Response(
            200,
            text=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {"name": "calculator", "arguments": ""},
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": '{"expr'}}
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": 'ession": "2+2"}'}}
                                ]
                            }
                        }
                    ]
                },
                {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("openai", handle, request=TOOL_REQ))
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert len(calls) == 1
    assert calls[0].id == "call_abc"
    assert calls[0].name == "calculator"
    assert calls[0].arguments == {"expression": "2+2"}


def test_groq_accumulates_tool_calls_like_openai():
    def handle(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "calculator"
        return httpx.Response(
            200,
            text=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_g",
                                        "function": {
                                            "name": "calculator",
                                            "arguments": '{"expression": "3*3"}',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("groq", handle, request=TOOL_REQ))
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert len(calls) == 1
    assert calls[0].arguments == {"expression": "3*3"}


def test_openai_multiple_tool_calls_emitted_in_index_order():
    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 1,
                                        "id": "call_b",
                                        "function": {"name": "datetime", "arguments": "{}"},
                                    },
                                    {
                                        "index": 0,
                                        "id": "call_a",
                                        "function": {
                                            "name": "calculator",
                                            "arguments": '{"expression": "1"}',
                                        },
                                    },
                                ]
                            }
                        }
                    ]
                },
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("openai", handle, request=TOOL_REQ))
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert [c.id for c in calls] == ["call_a", "call_b"]


def test_openai_serializes_assistant_tool_calls_and_tool_result_turns():
    request = ChatRequest(
        model="test-model",
        turns=(
            ChatTurn("user", "2+2?"),
            ChatTurn(
                "assistant",
                "",
                tool_calls=(
                    ToolCall(id="call_abc", name="calculator", arguments={"expression": "2+2"}),
                ),
            ),
            ChatTurn(
                "tool", '{"result": 4}', tool_call_id="call_abc", tool_name="calculator"
            ),
        ),
    )

    def handle(request_):
        body = json.loads(request_.content)
        assert body["messages"] == [
            {"role": "user", "content": "2+2?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "2+2"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_abc", "content": '{"result": 4}'},
        ]
        return httpx.Response(200, text=sse(openai_chunk("4"), "[DONE]"))

    events = asyncio.run(collect("openai", handle, request=request))
    assert [e.text for e in events if e.kind == "delta"] == ["4"]


def test_openai_tool_call_with_unparseable_arguments_falls_back_to_empty():
    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_x",
                                        "function": {"name": "calculator", "arguments": "not json"},
                                    }
                                ]
                            }
                        }
                    ]
                },
                "[DONE]",
            ),
        )

    events = asyncio.run(collect("openai", handle, request=TOOL_REQ))
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert len(calls) == 1
    assert calls[0].arguments == {}


def test_openai_tool_call_echoing_credential_is_rejected():
    secret = KEY.get_secret_value()

    def handle(request):
        return httpx.Response(
            200,
            text=sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_x",
                                        "function": {
                                            "name": "calculator",
                                            "arguments": json.dumps({"expression": secret}),
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                "[DONE]",
            ),
        )

    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("openai", handle, request=TOOL_REQ))
    assert error.value.code == "generation_failed"


def test_gemini_forwards_function_declarations_and_emits_tool_call():
    def handle(request):
        body = json.loads(request.content)
        assert body["tools"] == [
            {
                "functionDeclarations": [
                    {
                        "name": "calculator",
                        "description": "Evaluate arithmetic.",
                        "parameters": TOOL.parameters,
                    }
                ]
            }
        ]
        return httpx.Response(
            200,
            text=sse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "calculator",
                                            "args": {"expression": "2+2"},
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "candidates": [{"content": {"parts": [{"text": "done"}]}}],
                    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
                },
            ),
        )

    events = asyncio.run(collect("gemini", handle, request=TOOL_REQ))
    calls = [e.tool_call for e in events if e.kind == "tool_call"]
    assert len(calls) == 1
    assert calls[0].name == "calculator"
    assert calls[0].arguments == {"expression": "2+2"}
    assert calls[0].id == "gemini_calculator_1"
    assert [e.text for e in events if e.kind == "delta"] == ["done"]


def test_gemini_serializes_function_call_and_function_response_turns():
    request = ChatRequest(
        model="test-model",
        turns=(
            ChatTurn("user", "2+2?"),
            ChatTurn(
                "assistant",
                "",
                tool_calls=(
                    ToolCall(
                        id="gemini_calculator_1",
                        name="calculator",
                        arguments={"expression": "2+2"},
                    ),
                ),
            ),
            ChatTurn(
                "tool", '{"result": 4}', tool_call_id="gemini_calculator_1", tool_name="calculator"
            ),
        ),
    )

    def handle(request_):
        body = json.loads(request_.content)
        assert body["contents"] == [
            {"role": "user", "parts": [{"text": "2+2?"}]},
            {
                "role": "model",
                "parts": [{"functionCall": {"name": "calculator", "args": {"expression": "2+2"}}}],
            },
            {
                "role": "function",
                "parts": [
                    {"functionResponse": {"name": "calculator", "response": {"result": 4}}}
                ],
            },
        ]
        return httpx.Response(200, text=sse({"candidates": []}))

    assert asyncio.run(collect("gemini", handle, request=request)) == []


def test_gemini_function_response_wraps_non_object_content():
    request = ChatRequest(
        model="test-model",
        turns=(
            ChatTurn("user", "hi"),
            ChatTurn("tool", "plain text result", tool_call_id="x", tool_name="calculator"),
        ),
    )

    def handle(request_):
        body = json.loads(request_.content)
        assert body["contents"][1] == {
            "role": "function",
            "parts": [
                {
                    "functionResponse": {
                        "name": "calculator",
                        "response": {"result": "plain text result"},
                    }
                }
            ],
        }
        return httpx.Response(200, text=sse({"candidates": []}))

    assert asyncio.run(collect("gemini", handle, request=request)) == []


@pytest.mark.parametrize("provider", ["openai", "groq", "gemini"])
def test_no_tools_key_when_request_has_no_tools(provider):
    def handle(request):
        body = json.loads(request.content)
        assert "tools" not in body
        return httpx.Response(200, text=sse("[DONE]"))

    assert asyncio.run(collect(provider, handle)) == []


@pytest.mark.parametrize("index", [-1, 16])
def test_openai_tool_accumulator_bounds(index):
    payload = {"choices": [{"delta": {"tool_calls": [{
        "index": index, "function": {"name": "calculator", "arguments": "{}"},
    }]}}]}
    with pytest.raises(ProviderError, match="invalid generation"):
        asyncio.run(collect("openai", lambda _: httpx.Response(200, text=sse(payload)), TOOL_REQ))


@pytest.mark.parametrize("provider", ["openai", "groq"])
def test_decoded_tool_arguments_reject_unicode_escaped_credential(provider):
    encoded = "".join(f"\\u{ord(char):04x}" for char in KEY.get_secret_value())
    arguments = '{"expression":"' + encoded + '"}'
    payload = {"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "call_x",
        "function": {"name": "calculator", "arguments": arguments},
    }]}}]}
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect(provider, lambda _: httpx.Response(200, text=sse(payload)), TOOL_REQ))
    assert error.value.code == "generation_failed"


def test_gemini_decoded_tool_arguments_reject_credential():
    encoded = "".join(f"\\u{ord(char):04x}" for char in KEY.get_secret_value())
    body = ('data: {"candidates":[{"content":{"parts":[{"functionCall":'
            '{"name":"calculator","args":{"expression":"' + encoded + '"}}}]}}]}\n\n')
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect("gemini", lambda _: httpx.Response(200, text=body), TOOL_REQ))
    assert error.value.code == "generation_failed"