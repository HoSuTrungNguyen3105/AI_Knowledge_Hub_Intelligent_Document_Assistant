"""Offline Agent API + loop contracts, not live provider evidence."""

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_compare import KEY, MODEL_A, chunk, parse_sse, seed, sse

from app.api.v1.agents import agent_http
from app.schemas.agents import AgentCreate, RunRequest
from app.services.agents import AgentLimits, AgentService
from app.services.ai.chat import ChatHTTP

BASE = "/api/v1/ai/agents"
PAYLOAD = {"name": "Math Agent", "provider": "openai", "model": MODEL_A, "tools": ["calculator"]}


@pytest.fixture(autouse=True)
def encryption(settings):
    settings.credential_encryption_key = SecretStr(Fernet.generate_key().decode())


@pytest.fixture
async def owner(client, register, db, settings):
    assert register(client).status_code == 201
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    await seed(db, settings, owner_id, price_in=0.000001, price_out=0.000002)
    return client, owner_id


@pytest.fixture
def mock_agent(app):
    def configure(handler=None):
        handler = handler or (lambda _: httpx.Response(200, text=sse(chunk("Answer"), "[DONE]")))
        app.dependency_overrides[agent_http] = lambda: ChatHTTP(
            transport=httpx.MockTransport(handler)
        )
    configure()
    return configure


def create(client, **overrides):
    response = client.post(BASE, json={**PAYLOAD, **overrides})
    assert response.status_code == 201, response.text
    assert KEY not in response.text
    return response.json()


def run(client, agent, prompt="Please calculate 2+2."):
    response = client.post(f"{BASE}/{agent['id']}/run", json={"prompt": prompt})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert KEY not in response.text
    return parse_sse(response.text)


def tool_chunk(name="calculator", arguments=None, index=0, call_id="call_a"):
    return {"choices": [{"delta": {"tool_calls": [{
        "index": index, "id": call_id,
        "function": {"name": name, "arguments": json.dumps(arguments or {"expression": "2+2"})},
    }]}}]}


def usage(i=10, o=4):
    return {"choices": [], "usage": {"prompt_tokens": i, "completion_tokens": o}}


@pytest.mark.parametrize("path", ["", "/tools", f"/{uuid4()}", f"/{uuid4()}/executions"])
def test_agents_require_auth(client, path):
    assert client.get(BASE + path).status_code == 401


async def test_studio_crud_duplicate_and_catalog(owner):
    client, _ = owner
    catalog = client.get(f"{BASE}/tools").json()["tools"]
    assert {t["name"] for t in catalog if t["available"]} == {
        "calculator", "datetime", "data_analyzer",
    }
    assert all(not t["available"] for t in catalog if t["phase"] is not None)
    agent = create(client, description="Math", system_prompt="Use tools.")
    assert agent["system_prompt"] == "Use tools."
    assert len(client.get(BASE).json()["agents"]) == 1
    updated = client.patch(f"{BASE}/{agent['id']}", json={"name": "Updated", "tools": []})
    assert updated.status_code == 200
    assert updated.json()["tools"] == []
    copied = client.post(f"{BASE}/{agent['id']}/duplicate")
    assert copied.status_code == 201
    assert copied.json()["name"] == "Updated (bản sao)"
    assert copied.json()["id"] != agent["id"]
    assert client.delete(f"{BASE}/{agent['id']}").status_code == 204
    assert client.get(f"{BASE}/{agent['id']}").status_code == 404


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"temperature": 3}, {"tools": ["web_search"]},
    {"tools": ["shell"]}, {"max_output_tokens": 0}, {"api_key": "never-store"},
])
async def test_create_validation(owner, changes):
    client, _ = owner
    response = client.post(BASE, json={**PAYLOAD, **changes})
    assert response.status_code == 422
    assert "never-store" not in response.text


@pytest.mark.parametrize("field", ["name", "provider", "model", "tools"])
async def test_patch_rejects_required_null(owner, field):
    client, _ = owner
    agent = create(client)
    response = client.patch(f"{BASE}/{agent['id']}", json={field: None})
    assert response.status_code == 422
    assert client.get(f"{BASE}/{agent['id']}").json()["name"] == "Math Agent"


async def test_owner_isolation_all_routes(owner, client_factory, register, mock_agent):
    client, _ = owner
    agent = create(client)
    execution = run(client, agent)[-1][1]["execution"]
    other = client_factory()
    register(other, email="other-agent@example.com")
    assert other.get(BASE).json()["agents"] == []
    paths = [f"/{agent['id']}", f"/{agent['id']}/executions",
             f"/{agent['id']}/executions/{execution['id']}"]
    for path in paths:
        assert other.get(BASE + path).status_code == 404
    assert other.patch(BASE + paths[0], json={"name": "stolen"}).status_code == 404
    assert other.delete(BASE + paths[0]).status_code == 404
    assert other.post(BASE + paths[0] + "/duplicate").status_code == 404
    assert other.post(BASE + paths[0] + "/run", json={"prompt": "x"}).status_code == 404
    assert other.delete(BASE + paths[2]).status_code == 404


async def test_real_tool_loop_sse_audit_and_estimated_cost(owner, mock_agent, db):
    client, user_id = owner
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            assert body["tools"][0]["function"]["name"] == "calculator"
            return httpx.Response(200, text=sse(tool_chunk(), usage(), "[DONE]"))
        assert body["messages"][-1] == {
            "role": "tool", "tool_call_id": "call_a",
            "content": '{"expression": "2+2", "result": 4}',
        }
        assert body["messages"][-2]["tool_calls"][0]["id"] == "call_a"
        return httpx.Response(200, text=sse(chunk("2+2 = 4."), usage(12, 5), "[DONE]"))
    mock_agent(handler)
    agent = create(client)
    events = run(client, agent)
    names = [name for name, _ in events]
    assert names == ["execution", "tool_call", "tool_result", "step_done", "step_delta",
                     "step_done", "done"]
    execution = events[-1][1]["execution"]
    assert execution["status"] == "success"
    assert execution["content"] == "2+2 = 4."
    assert execution["step_count"] == 2
    assert execution["provider"] == "openai" and execution["model"] == MODEL_A
    assert execution["input_tokens"] == 22 and execution["output_tokens"] == 9
    assert execution["estimated_cost"] == pytest.approx(0.00004)
    assert execution["steps"][0]["tool_calls"][0]["result"]["result"] == 4
    assert len(execution["tool_executions"]) == 1
    audit = await db.tool_executions.find_one({"user_id": user_id})
    assert audit["tool_name"] == "calculator"
    path = f"{BASE}/{agent['id']}/executions"
    assert len(client.get(path).json()["executions"]) == 1
    assert client.get(path + "/" + execution["id"]).json()["steps"] == execution["steps"]
    assert client.delete(path + "/" + execution["id"]).status_code == 204
    assert await db.tool_executions.count_documents({"user_id": user_id}) == 0


@pytest.mark.parametrize("tool,args,code", [
    ("shell", {"command": "rm -rf x"}, "tool_not_allowed"),
    ("datetime", {"operation": "now"}, "tool_not_allowed"),
    ("calculator", {"expression": "__import__('os')"}, "calculator_invalid"),
    ("calculator", {"expression": "1/0"}, "calculator_invalid"),
    ("calculator", {"wrong": True}, "tool_invalid_arguments"),
])
async def test_invalid_or_disabled_tool_returns_observation(owner, mock_agent, tool, args, code):
    client, _ = owner
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, text=sse(tool_chunk(tool, args), "[DONE]"))
        body = json.loads(request.content)
        assert json.loads(body["messages"][-1]["content"])["error"] == code
        return httpx.Response(200, text=sse(chunk("Tool unavailable."), "[DONE]"))
    mock_agent(handler)
    execution = run(client, create(client))[-1][1]["execution"]
    assert execution["status"] == "success"
    assert execution["tool_executions"][0]["error_code"] == code


async def test_capability_and_saved_config_rechecked_before_run(owner, db, mock_agent):
    client, _ = owner
    agent = create(client)
    await db.ai_models.update_many({}, {"$set": {"capabilities.tools": False}})
    response = client.post(f"{BASE}/{agent['id']}/run", json={"prompt": "x"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "model_not_tool_capable"
    assert await db.agent_executions.count_documents({}) == 0
    assert client.post(BASE, json=PAYLOAD).status_code == 409
    assert client.post(BASE, json={**PAYLOAD, "tools": []}).status_code == 201
    await db.user_provider_credentials.update_many({}, {"$set": {"enabled": False}})
    assert client.post(f"{BASE}/{agent['id']}/run", json={"prompt": "x"}).status_code == 409


@pytest.mark.parametrize("status,code", [(401, "provider_authentication_failed"),
                                       (429, "provider_rate_limited"),
                                       (500, "provider_unavailable")])
async def test_runtime_failure_persisted_and_redacted(owner, mock_agent, status, code):
    client, _ = owner
    mock_agent(lambda _: httpx.Response(status, text=KEY))
    events = run(client, create(client))
    assert events[-2] == ("execution_error", {"code": code, "message": events[-2][1]["message"]})
    assert events[-1][1]["execution"]["status"] == "error"


TOOL_REJECTION = {
    "error": {
        "code": "tool_use_failed",
        "message": "This model does not support tool use.",
        "type": "invalid_request_error",
    }
}


async def test_tools_unsupported_retries_step_without_tools(owner, mock_agent):
    client, _ = owner
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "tools" in body:
            return httpx.Response(400, json=TOOL_REJECTION)
        return httpx.Response(200, text=sse(chunk("Plain answer"), usage(), "[DONE]"))

    mock_agent(handler)
    events = run(client, create(client))
    names = [name for name, _ in events]
    assert "tools_fallback" in names
    assert events[names.index("tools_fallback")][1] == {
        "code": "model_tools_unsupported",
        "step_index": 0,
    }
    execution = events[-1][1]["execution"]
    assert execution["status"] == "success"
    assert execution["content"] == "Plain answer"
    assert len(bodies) == 2
    assert "tools" in bodies[0] and "tools" not in bodies[1]


async def test_tools_unsupported_persistent_rejection_keeps_real_code(owner, mock_agent):
    client, _ = owner
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json=TOOL_REJECTION)

    mock_agent(handler)
    events = run(client, create(client))
    errors = [data for name, data in events if name == "execution_error"]
    assert errors and errors[0]["code"] == "model_tools_unsupported"
    execution = events[-1][1]["execution"]
    assert execution["status"] == "error"
    assert execution["error_code"] == "model_tools_unsupported"
    # One attempt with tools, one fallback attempt without, then it stops.
    assert len(bodies) == 2 and "tools" not in bodies[1]


async def test_tools_unsupported_without_tools_does_not_retry(owner, mock_agent):
    client, _ = owner
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json=TOOL_REJECTION)

    mock_agent(handler)
    events = run(client, create(client, tools=[]))
    execution = events[-1][1]["execution"]
    assert execution["error_code"] == "model_tools_unsupported"
    assert len(bodies) == 1


async def test_empty_generation_is_not_success(owner, mock_agent):
    client, _ = owner
    mock_agent(lambda _: httpx.Response(200, text=sse("[DONE]")))
    execution = run(client, create(client))[-1][1]["execution"]
    assert execution["error_code"] == "generation_failed"


async def test_unknown_usage_stays_null_and_zero_usage_stays_zero(owner, mock_agent):
    client, _ = owner
    agent = create(client, tools=[])
    execution = run(client, agent)[-1][1]["execution"]
    assert execution["input_tokens"] is None and execution["estimated_cost"] is None
    mock_agent(lambda _: httpx.Response(200, text=sse(chunk("x"), usage(0, 0), "[DONE]")))
    execution = run(client, agent)[-1][1]["execution"]
    assert execution["input_tokens"] == 0 and execution["output_tokens"] == 0
    assert execution["estimated_cost"] == 0


async def service_prepared(owner, db, settings, handler, **limits):
    _, user_id = owner
    service = AgentService(db, settings, ChatHTTP(transport=httpx.MockTransport(handler)),
                           limits=AgentLimits(**limits))
    agent = await service.create_agent(user_id, AgentCreate(**PAYLOAD))
    return service, await service.prepare_run(user_id, agent.id, RunRequest(prompt="2+2?"))


async def test_step_limit_persists_bounded_trace(owner, db, settings):
    service, prepared = await service_prepared(
        owner, db, settings, lambda _: httpx.Response(200, text=sse(tool_chunk(), "[DONE]")),
        max_steps=2,
    )
    events = [e async for e in service.stream_prepared(prepared)]
    final = events[-1]["data"]["execution"]
    assert final["error_code"] == "agent_step_limit"
    assert len(final["steps"]) == 2


async def test_budget_without_usage_still_limits_calls(owner, db, settings):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=sse(tool_chunk(), "[DONE]"))
    service, prepared = await service_prepared(owner, db, settings, handler, token_budget=1100)
    final = [e async for e in service.stream_prepared(prepared)][-1]["data"]["execution"]
    assert final["error_code"] == "agent_budget_exceeded"
    assert len(requests) <= 2
    assert all(0 < r["max_tokens"] <= 1100 for r in requests)


async def test_budget_rejects_large_prompt_before_stream(owner, db, mock_agent):
    client, _ = owner
    agent = create(client)
    response = client.post(f"{BASE}/{agent['id']}/run", json={"prompt": "x" * 16000})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "agent_budget_exceeded"
    assert await db.agent_executions.count_documents({}) == 0


async def test_budget_charges_real_usage_when_provider_reports_it(owner, db, settings):
    # Byte-heavy Vietnamese system prompt: the UTF-8 byte estimate of each
    # request is several thousand, so charging estimates (the old max()
    # accounting) would blow the default 8k budget before the second step.
    # The provider reports tiny real usage per step; real usage is charged.
    _, user_id = owner
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, text=sse(tool_chunk(), usage(10, 4), "[DONE]"))
        return httpx.Response(200, text=sse(chunk("4"), usage(12, 2), "[DONE]"))

    service = AgentService(db, settings, ChatHTTP(transport=httpx.MockTransport(handler)))
    agent = await service.create_agent(
        user_id,
        AgentCreate(
            **{
                **PAYLOAD,
                "system_prompt": "Bạn là trợ lý tính toán rất cẩn thận và tỉ mỉ. " * 100,
            }
        ),
    )
    prepared = await service.prepare_run(user_id, agent.id, RunRequest(prompt="2+2?"))
    final = [e async for e in service.stream_prepared(prepared)][-1]["data"]["execution"]
    assert final["status"] == "success", final
    assert final["error_code"] is None
    assert final["input_tokens"] == 22 and final["output_tokens"] == 6
    assert calls == 2


async def test_total_usage_budget_stops_before_tool_execution(owner, db, settings):
    service, prepared = await service_prepared(
        owner, db, settings,
        lambda _: httpx.Response(200, text=sse(tool_chunk(), usage(9000, 1), "[DONE]")),
    )
    final = [e async for e in service.stream_prepared(prepared)][-1]["data"]["execution"]
    assert final["error_code"] == "agent_budget_exceeded"
    assert final["input_tokens"] == 9000
    assert final["tool_executions"] == []


async def test_tool_per_step_limit_audited(owner, db, settings):
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        if calls > 1:
            return httpx.Response(200, text=sse(chunk("done"), "[DONE]"))
        return httpx.Response(200, text=sse(
            tool_chunk(index=0), tool_chunk(index=1, call_id="call_b"), "[DONE]",
        ))
    service, prepared = await service_prepared(
        owner, db, settings, handler, max_tool_calls_per_step=1,
    )
    final = [e async for e in service.stream_prepared(prepared)][-1]["data"]["execution"]
    assert final["tool_executions"][1]["status"] == "skipped"
    assert final["tool_executions"][1]["error_code"] == "tool_limit"


async def test_deadline_and_cancellation_save_partial_text(owner, db, settings):
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse(chunk("Partial")).encode()
            await asyncio.Event().wait()
    service, prepared = await service_prepared(
        owner, db, settings, lambda _: httpx.Response(200, stream=SlowBody()),
        deadline_seconds=0.05,
    )
    final = [e async for e in service.stream_prepared(prepared)][-1]["data"]["execution"]
    assert final["error_code"] == "agent_timeout" and final["content"] == "Partial"
    assert final["steps"][0]["content"] == "Partial"
    service.limits = AgentLimits()
    stream = service.stream_prepared(prepared)
    first = await anext(stream)
    delta = await anext(stream)
    assert delta["event"] == "step_delta"
    await stream.aclose()
    saved = await service.repo.get_execution(
        prepared.user_id, UUID(first["data"]["execution"]["id"])
    )
    assert saved.status == "stopped" and saved.content == "Partial"
    assert saved.steps[0].content == "Partial"


async def test_tool_timeout_is_sanitized_and_loop_continues(owner, db, settings, monkeypatch):
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        text = sse(tool_chunk(), "[DONE]") if calls == 1 else sse(chunk("done"), "[DONE]")
        return httpx.Response(200, text=text)
    service, prepared = await service_prepared(owner, db, settings, handler)
    async def timeout(*args, **kwargs):
        # Close the unstarted to_thread coroutine rather than leak a warning.
        args[0].close()
        raise TimeoutError("private tool details")
    monkeypatch.setattr("app.services.agents.asyncio.wait_for", timeout)
    events = [e async for e in service.stream_prepared(prepared)]
    final = events[-1]["data"]["execution"]
    assert final["status"] == "success"
    assert final["tool_executions"][0]["error_code"] == "tool_timeout"
    assert "private tool details" not in json.dumps(events)


async def test_task_cancel_saves_partial_result(owner, db, settings):
    reached = asyncio.Event()
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse(chunk("Partial"), usage(2, 1)).encode()
            reached.set()
            await asyncio.Event().wait()
    service, prepared = await service_prepared(
        owner, db, settings, lambda _: httpx.Response(200, stream=SlowBody()),
    )
    async def consume():
        return [e async for e in service.stream_prepared(prepared)]
    task = asyncio.create_task(consume())
    await reached.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = (await service.repo.list_executions(prepared.user_id, prepared.agent.id))[0]
    assert saved.status == "stopped" and saved.content == "Partial"
    assert saved.input_tokens == 2 and saved.output_tokens == 1


async def test_unexpected_tool_exception_never_leaks(owner, db, settings, monkeypatch):
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        text = sse(tool_chunk(), "[DONE]") if calls == 1 else sse(chunk("done"), "[DONE]")
        return httpx.Response(200, text=text)
    def fail(*_):
        raise RuntimeError("private details " + KEY)
    monkeypatch.setattr("app.services.agents.execute_tool", fail)
    service, prepared = await service_prepared(owner, db, settings, handler)
    events = [e async for e in service.stream_prepared(prepared)]
    assert events[-1]["data"]["execution"]["tool_executions"][0]["error_code"] == "tool_failed"
    assert KEY not in json.dumps(events)


async def test_stop_immediately_after_execution_event(owner, db, settings):
    service, prepared = await service_prepared(
        owner, db, settings, lambda _: httpx.Response(200, text=sse(chunk("done"), "[DONE]")),
    )
    stream = service.stream_prepared(prepared)
    first = await anext(stream)
    await stream.aclose()
    saved = await service.repo.get_execution(
        prepared.user_id, UUID(first["data"]["execution"]["id"])
    )
    assert saved.status == "stopped" and saved.steps == []


@pytest.mark.parametrize("arguments", [{"values": [10**30]}, {"bad\x00key": 1}])
async def test_unencodable_arguments_rejected_before_trace_and_audit(
    owner, db, settings, arguments,
):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, text=sse(
                tool_chunk("data_analyzer", arguments), usage(), "[DONE]",
            ))
        body = json.loads(request.content)
        assert json.loads(body["messages"][-1]["content"]) == {
            "error": "tool_invalid_arguments",
        }
        return httpx.Response(200, text=sse(chunk("Rejected unsafe arguments."), usage(), "[DONE]"))
    service, prepared = await service_prepared(owner, db, settings, handler)
    agent = await service.create_agent(
        prepared.user_id, AgentCreate(**{**PAYLOAD, "tools": ["data_analyzer"]}),
    )
    prepared = await service.prepare_run(prepared.user_id, agent.id, RunRequest(prompt="Analyze."))
    events = [event async for event in service.stream_prepared(prepared)]
    final = events[-1]["data"]["execution"]
    assert final["status"] == "success"
    assert final["tool_executions"][0]["arguments"] == {
        "rejected_arguments": "invalid_or_out_of_range",
    }
    assert final["steps"][0]["tool_calls"][0]["error_code"] == "tool_invalid_arguments"
    assert final["tool_executions"][0]["error_code"] == "tool_invalid_arguments"
    saved = await service.repo.get_execution(prepared.user_id, UUID(final["id"]))
    assert saved.status != "running"


@pytest.mark.parametrize("first,last,inputs,outputs", [
    ((10, 4), (None, None), None, None),
    ((None, None), (10, 4), None, None),
    ((10, None), (12, 4), 22, None),
    ((None, 4), (12, 5), None, 9),
])
async def test_usage_missing_in_any_attempted_step_is_not_a_complete_total(
    owner, mock_agent, first, last, inputs, outputs,
):
    client, _ = owner
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        event = tool_chunk() if calls == 1 else chunk("done")
        counts = first if calls == 1 else last
        return httpx.Response(200, text=sse(event, usage(*counts), "[DONE]"))
    mock_agent(handler)
    final = run(client, create(client))[-1][1]["execution"]
    assert final["input_tokens"] == inputs
    assert final["output_tokens"] == outputs
    assert final["estimated_cost"] is None
    assert final["steps"][0]["input_tokens"] == first[0]
    assert final["steps"][1]["output_tokens"] == last[1]


async def test_http_stream_wrapper_close_finalizes_inner_execution(owner, db, settings):
    from app.api.v1.agents import _stream

    service, prepared = await service_prepared(
        owner, db, settings, lambda _: httpx.Response(200, text=sse(chunk("done"), "[DONE]")),
    )
    body = _stream(service.stream_prepared(prepared)).body_iterator
    first = await anext(body)
    execution_id = UUID(parse_sse(first)[0][1]["execution"]["id"])
    await body.aclose()
    saved = await service.repo.get_execution(prepared.user_id, execution_id)
    assert saved.status == "stopped"
    assert await db.ai_requests.count_documents({"user_id": prepared.user_id}) == 1


async def test_cancel_during_terminal_persistence_finishes_exactly_once(
    owner, db, settings, monkeypatch,
):
    service, prepared = await service_prepared(
        owner, db, settings,
        lambda _: httpx.Response(200, text=sse(chunk("done"), usage(), "[DONE]")),
    )
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.repo.update_execution
    async def delayed_update(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(service.repo, "update_execution", delayed_update)
    async def consume():
        return [event async for event in service.stream_prepared(prepared)]
    task = asyncio.create_task(consume())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = (await service.repo.list_executions(prepared.user_id, prepared.agent.id))[0]
    assert saved.status == "success" and saved.content == "done"
    assert len(saved.steps) == 1
    assert await db.ai_requests.count_documents({"user_id": prepared.user_id}) == 1


async def test_gemini_signed_parallel_calls_replayed_without_public_metadata(
    owner, db, settings,
):
    _, user_id = owner
    await seed(db, settings, user_id, provider="gemini")
    requests = []
    signature = "opaque-test-signature"
    parts = [
        {"functionCall": {"id": "gem_a", "name": "calculator", "args": {"expression": "2+2"}},
         "thoughtSignature": signature},
        {"functionCall": {"id": "gem_b", "name": "calculator", "args": {"expression": "3*3"}}},
    ]
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, text=sse({"candidates": [{"content": {"parts": parts}}]}))
        assert body["contents"][1] == {"role": "model", "parts": parts}
        responses = body["contents"][2]
        assert responses["role"] == "function" and len(body["contents"]) == 3
        assert [part["functionResponse"]["id"] for part in responses["parts"]] == [
            "gem_a", "gem_b",
        ]
        assert [part["functionResponse"]["response"]["result"]
                for part in responses["parts"]] == [4, 9]
        return httpx.Response(200, text=sse(
            {"candidates": [{"content": {"parts": [{"text": "4 and 9"}]}}]},
        ))
    service = AgentService(db, settings, ChatHTTP(transport=httpx.MockTransport(handler)))
    agent = await service.create_agent(user_id, AgentCreate(**{**PAYLOAD, "provider": "gemini"}))
    prepared = await service.prepare_run(user_id, agent.id, RunRequest(prompt="Calculate both."))
    events = [event async for event in service.stream_prepared(prepared)]
    final = events[-1]["data"]["execution"]
    assert final["status"] == "success" and final["content"] == "4 and 9"
    assert len(final["tool_executions"]) == 2
    assert signature not in json.dumps(events)
    assert "replay_metadata" not in json.dumps(events)
    saved = await service.repo.get_execution(user_id, UUID(final["id"]))
    assert signature not in saved.model_dump_json()
