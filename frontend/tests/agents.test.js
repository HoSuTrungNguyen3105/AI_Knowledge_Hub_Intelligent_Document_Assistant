// @vitest-environment jsdom
// Fixtures are test-only; no fake app records or provider credentials.
import { afterEach, describe, expect, it, vi } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api, refreshClient } from "../services/api";
import { agentsService } from "../services/agents";
import { agentErrorFromEvent, applyExecutionEvent, executionStatusLabels, getAgentError, toolCapability, traceValue } from "../utils/agents";

const mock = new MockAdapter(api);
const refresh = new MockAdapter(refreshClient);
afterEach(() => { mock.reset(); refresh.reset(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function response(chunks, status = 200) {
  let index = 0;
  return { ok: status === 200, status, json: async () => JSON.parse(chunks.join("")), body: { getReader: () => ({ read: async () => index < chunks.length ? { done: false, value: new TextEncoder().encode(chunks[index++]) } : { done: true } }) } };
}
const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

describe("Agent REST owner-scoped contract", () => {
  it("unwraps agent and tool envelopes through shared authenticated api", async () => {
    mock.onGet("/ai/agents").reply(200, { agents: [{ id: "a" }] });
    mock.onGet("/ai/agents/tools").reply(200, { tools: [{ name: "calculator", available: true, parameters: {} }] });
    const signal = new AbortController().signal;
    expect(await agentsService.list(signal)).toEqual([{ id: "a" }]);
    expect(await agentsService.tools(signal)).toMatchObject([{ name: "calculator", available: true }]);
    expect(mock.history.get[0].signal).toBe(signal);
    expect(mock.history.get[0].baseURL).toBe("/api/v1");
    expect(mock.history.get[0].withCredentials).toBe(true);
  });
  it("creates and patches exactly the configuration, without owner or keys", async () => {
    const payload = { name: "Research", description: "Test", provider: "groq", model: "model", system_prompt: "Role", temperature: 0.4, max_output_tokens: 500, tools: ["calculator"] };
    mock.onPost("/ai/agents").reply(201, { id: "a", ...payload });
    mock.onPatch("/ai/agents/a").reply(200, { id: "a", ...payload });
    expect(await agentsService.create(payload)).toMatchObject(payload);
    expect(await agentsService.patch("a", payload)).toMatchObject(payload);
    expect(JSON.parse(mock.history.post[0].data)).toEqual(payload);
    expect(JSON.parse(mock.history.patch[0].data)).toEqual(payload);
  });
  it("gets, duplicates and deletes by agent id", async () => {
    mock.onGet("/ai/agents/a").reply(200, { id: "a", tools: [] });
    mock.onPost("/ai/agents/a/duplicate").reply(201, { id: "copy" });
    mock.onDelete("/ai/agents/a").reply(204);
    expect(await agentsService.get("a")).toEqual({ id: "a", tools: [] });
    expect(await agentsService.duplicate("a")).toEqual({ id: "copy" });
    expect(JSON.parse(mock.history.post[0].data)).toEqual({});
    await agentsService.remove("a");
    expect(mock.history.delete).toHaveLength(1);
  });
  it("lists, selects and deletes executions within their agent", async () => {
    mock.onGet("/ai/agents/a/executions").reply(200, { executions: [{ id: "e" }] });
    mock.onGet("/ai/agents/a/executions/e").reply(200, { id: "e", steps: [], tool_executions: [] });
    mock.onDelete("/ai/agents/a/executions/e").reply(204);
    expect(await agentsService.executions("a")).toEqual([{ id: "e" }]);
    expect(await agentsService.execution("a", "e")).toMatchObject({ steps: [] });
    await agentsService.removeExecution("a", "e");
    expect(mock.history.delete[0].url).toBe("/ai/agents/a/executions/e");
  });
  it("escapes path identifiers instead of allowing path traversal", async () => {
    mock.onGet("/ai/agents/a%2Fb/executions/e%2Ff").reply(200, { id: "e/f" });
    expect(await agentsService.execution("a/b", "e/f")).toEqual({ id: "e/f" });
  });
  it("propagates forbidden/not-found responses without synthetic records", async () => {
    mock.onGet("/ai/agents/other").reply(404, { detail: { code: "agent_not_found" } });
    await expect(agentsService.get("other")).rejects.toMatchObject({ response: { status: 404 } });
  });
});

describe("Agent SSE uses streamChat", () => {
  it("streams all event types from split network chunks with prompt-only body", async () => {
    const events = [
      ["execution", { execution: { id: "e", agent_id: "a", status: "running" } }],
      ["step_delta", { step_index: 0, text: "Calculating" }],
      ["tool_call", { step_index: 0, tool_call: { id: "t", name: "calculator", arguments: { expression: "2+2" }, status: "running" } }],
      ["tool_result", { step_index: 0, tool_call: { id: "t", status: "success", result: 4 } }],
      ["step_done", { step: { index: 0, content: "Calculating", tool_calls: [] } }],
      ["execution_error", { code: "agent_step_limit", message: "Fixed server message" }],
      ["done", { execution: { id: "e", status: "error", content: "", steps: [] } }],
    ];
    const text = events.map(([name, data]) => event(name, data)).join("");
    const fetchMock = vi.fn().mockResolvedValue(response([text.slice(0, 20), text.slice(20, 75), text.slice(75)]));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const received = [];
    await agentsService.run("a", { prompt: "2+2" }, { signal: controller.signal, onEvent: (value) => received.push(value) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/ai/agents/a/run");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.signal).toBe(controller.signal);
    expect(JSON.parse(init.body)).toEqual({ prompt: "2+2" });
    expect(received).toEqual(events.map(([name, data]) => ({ event: name, data })));
  });
  it("refreshes cookie session once before retrying a 401", async () => {
    refresh.onPost("/auth/refresh").reply(200, {});
    const fetchMock = vi.fn().mockResolvedValueOnce(response(["{}"], 401)).mockResolvedValueOnce(response([event("done", { execution: { id: "e" } })]));
    vi.stubGlobal("fetch", fetchMock);
    await agentsService.run("a", { prompt: "Q" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refresh.history.post).toHaveLength(1);
  });
  it("preserves validation error codes raised before SSE", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(['{"detail":{"code":"model_not_tool_capable"}}'], 409)));
    await expect(agentsService.run("a", { prompt: "Q" })).rejects.toMatchObject({ response: { status: 409, data: { detail: { code: "model_not_tool_capable" } } } });
  });
  it("passes abort through, rather than fabricating a done event", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url, { signal }) => new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))))));
    const pending = agentsService.run("a", { prompt: "Q" }, { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("Agent utility safety and step reducer", () => {
  it.each(["agent_not_found", "execution_not_found", "invalid_agent_tools", "agent_budget_exceeded", "agent_step_limit", "agent_timeout", "model_not_tool_capable", "model_tools_unsupported", "provider_request_rejected", "tool_not_allowed"])("maps %s without echoing arbitrary upstream text", (code) => {
    const message = getAgentError({ response: { status: 409, data: { detail: { code, message: "PRIVATE-UPSTREAM" } } } });
    expect(message).not.toContain("PRIVATE-UPSTREAM");
    expect(message).not.toContain("không còn phù hợp");
  });
  it("handles unknown error codes, HTTP states and prototype names safely", () => {
    expect(agentErrorFromEvent({ code: "toString", message: "unsafe" })).not.toContain("unsafe");
    expect(getAgentError({ response: { status: 404 } })).toContain("tài khoản");
    expect(getAgentError({ response: { status: 422 } })).toContain("Agent chưa hợp lệ");
    expect(getAgentError({ response: { status: 401 } })).toContain("hết hạn");
    expect(getAgentError()).toContain("Không kết nối");
    expect(executionStatusLabels.stopped).toBe("Đã dừng");
  });
  it("blocks explicit false from provider or model, permits unknown honestly", () => {
    expect(toolCapability({ function_calling: false }, { capabilities: { tools: true } })).toBe(false);
    expect(toolCapability({ capabilities: { function_calling: false } }, {})).toBe(false);
    expect(toolCapability({}, { capabilities: { function_calling: false } })).toBe(false);
    expect(toolCapability({}, { capabilities: { tools: false } })).toBe(false);
    expect(toolCapability({}, {})).toBe(null);
    expect(toolCapability({}, { capabilities: { function_calling: true } })).toBe(true);
  });
  it("merges deltas, call/result events and authoritative step completion", () => {
    let state = { id: "e", agent_id: "a", steps: [], status: "running" };
    state = applyExecutionEvent(state, { event: "step_delta", data: { step_index: 1, text: "Final " } });
    state = applyExecutionEvent(state, { event: "step_delta", data: { step_index: 1, text: "text" } });
    state = applyExecutionEvent(state, { event: "tool_call", data: { step_index: 0, tool_call: { id: "t", name: "calculator", arguments: { expression: "2+2" } } } });
    state = applyExecutionEvent(state, { event: "tool_result", data: { step_index: 0, tool_call: { id: "t", status: "success", result: 4 } } });
    state = applyExecutionEvent(state, { event: "tool_result", data: { step_index: 0, tool_call: { id: "t", status: "success", result: 4 } } });
    expect(state.steps.map((step) => step.index)).toEqual([0, 1]);
    expect(state.steps[0].tool_calls).toHaveLength(1);
    expect(state.steps[0].tool_calls[0]).toMatchObject({ name: "calculator", result: 4 });
    expect(state.steps[1].content).toBe("Final text");
    state = applyExecutionEvent(state, { event: "step_done", data: { step: { index: 1, content: "Saved text", input_tokens: 10 } } });
    expect(state.steps[1].content).toBe("Saved text");
    state = applyExecutionEvent(state, { event: "done", data: { execution: { id: "e", status: "success", content: "Answer", steps: state.steps } } });
    expect(state.status).toBe("success");
    expect(state.agent_id).toBe("a");
  });
  it("ignores the tools_fallback notice event without touching state", () => {
    const state = { id: "e", agent_id: "a", steps: [], status: "running" };
    expect(applyExecutionEvent(state, { event: "tools_fallback", data: { code: "model_tools_unsupported", step_index: 0 } })).toBe(state);
  });
  it("marks execution errors and safely displays structured trace values", () => {
    expect(applyExecutionEvent({ steps: [] }, { event: "execution_error", data: { code: "agent_timeout" } })).toMatchObject({ status: "error", error_code: "agent_timeout" });
    expect(traceValue({ result: 4 })).toContain('"result": 4');
    expect(traceValue("text")).toBe("text");
    expect(traceValue(null)).toBe("—");
  });
});
