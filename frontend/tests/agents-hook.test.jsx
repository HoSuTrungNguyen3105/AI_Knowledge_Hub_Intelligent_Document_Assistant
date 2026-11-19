// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { agentsService } from "../services/agents";
import { useAgents } from "../hooks/use-agents";
import { useChatProviders } from "../hooks/use-chat-providers";
import { providerService } from "../services/providers";
import { useNotice } from "../stores/notice";

const mock = new MockAdapter(api);
const agent = (id) => ({ id, name: `Agent ${id}`, provider: "groq", model: "model", tools: [], system_prompt: "Role", temperature: null, max_output_tokens: null });
const execution = (id, agentId = "a") => ({ id, agent_id: agentId, prompt: "Q", status: "success", content: "Final", steps: [] });
function deferred() { let resolve, reject; const promise = new Promise((res, rej) => { resolve = res; reject = rej; }); return { promise, resolve, reject }; }
function streamed() {
  const runs = [];
  vi.spyOn(agentsService, "run").mockImplementation((id, payload, options) => {
    const pending = deferred();
    runs.push({ id, payload, ...options, ...pending });
    return pending.promise;
  });
  return runs;
}
async function select(result, id = "a") {
  act(() => result.current.selectAgent(id));
  await waitFor(() => expect(result.current.detailLoading).toBe(false));
  expect(result.current.agent.id).toBe(id);
}
async function start(result, runs, prompt = "Q") {
  act(() => result.current.run(prompt));
  await waitFor(() => expect(runs.length).toBeGreaterThan(0));
  return runs.at(-1);
}
beforeEach(() => {
  mock.onGet("/ai/agents").reply(200, { agents: [agent("a"), agent("b")] });
  mock.onGet("/ai/agents/tools").reply(200, { tools: [{ name: "calculator", available: true }] });
  mock.onGet(/\/ai\/agents\/[ab]$/).reply((config) => [200, agent(config.url.split("/").at(-1))]);
  mock.onGet(/\/ai\/agents\/[ab]\/executions$/).reply(200, { executions: [] });
  mock.onGet(/\/ai\/agents\/[ab]\/executions\//).reply((config) => [200, execution(config.url.split("/").at(-1), config.url.split("/")[3])]);
});
afterEach(() => { cleanup(); mock.reset(); vi.restoreAllMocks(); useNotice.setState({ notice: null }); });

describe("useAgents CRUD and loading", () => {
  it("derives initial and reload loading from revision counters", async () => {
    const { result } = renderHook(() => useAgents());
    expect(result.current.agents.loading).toBe(true);
    expect(result.current.tools.loading).toBe(true);
    await waitFor(() => expect(result.current.agents.loading).toBe(false));
    await waitFor(() => expect(result.current.tools.loading).toBe(false));
    act(() => { result.current.reloadList(); result.current.reloadTools(); });
    expect(result.current.agents.loading).toBe(true);
    expect(result.current.tools.loading).toBe(true);
    await waitFor(() => expect(result.current.agents.loading).toBe(false));
  });
  it("creates, edits, duplicates and deletes using real services", async () => {
    mock.onPost("/ai/agents").reply(201, agent("a"));
    mock.onPatch("/ai/agents/a").reply(200, agent("a"));
    mock.onPost("/ai/agents/a/duplicate").reply(201, agent("b"));
    mock.onDelete("/ai/agents/b").reply(204);
    const { result } = renderHook(() => useAgents());
    await act(async () => { await result.current.saveAgent({ name: "New" }); });
    await waitFor(() => expect(result.current.agent?.id).toBe("a"));
    await act(async () => { await result.current.saveAgent({ name: "Edit" }); });
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ name: "Edit" });
    await act(async () => { await result.current.duplicateAgent(); });
    await waitFor(() => expect(result.current.agent?.id).toBe("b"));
    act(() => result.current.setDeletion({ agentId: "b" }));
    await act(async () => { await result.current.confirmDeletion(); });
    expect(result.current.activeId).toBe(null);
    expect(result.current.deletion).toBe(null);
    expect(mock.history.delete[0].url).toBe("/ai/agents/b");
  });
  it("selects history detail and deletes only the confirmed execution", async () => {
    mock.onDelete("/ai/agents/a/executions/e").reply(204);
    const { result } = renderHook(() => useAgents());
    await select(result);
    act(() => result.current.selectExecution("e"));
    await waitFor(() => expect(result.current.execution?.id).toBe("e"));
    await act(async () => { await result.current.confirmDeletion(); });
    expect(mock.history.delete).toHaveLength(0);
    act(() => result.current.setDeletion({ agentId: "a", executionId: "e" }));
    await act(async () => { await result.current.confirmDeletion(); });
    expect(result.current.activeExecutionId).toBe(null);
    expect(result.current.execution).toBe(null);
    expect(result.current.activeId).toBe("a");
    expect(mock.history.delete[0].url).toBe("/ai/agents/a/executions/e");
  });
  it("reports CRUD failures through notice and keeps the selected agent", async () => {
    mock.onPatch("/ai/agents/a").reply(422, { detail: { message: "UPSTREAM" } });
    const show = vi.fn();
    const original = useNotice.getState().show;
    useNotice.setState({ show });
    try {
      const { result } = renderHook(() => useAgents());
      await select(result);
      await act(async () => { await result.current.saveAgent({ name: "" }); });
      expect(result.current.activeId).toBe("a");
      expect(result.current.busy).toBe("");
      expect(show).toHaveBeenCalledWith(expect.stringContaining("chưa hợp lệ"), "error");
      expect(show.mock.calls[0][0]).not.toContain("UPSTREAM");
    } finally { useNotice.setState({ show: original }); }
  });
  it("offers error state and a successful retry for detail", async () => {
    vi.spyOn(agentsService, "get").mockRejectedValueOnce({ response: { status: 404 } }).mockResolvedValue(agent("a"));
    const { result } = renderHook(() => useAgents());
    act(() => result.current.selectAgent("a"));
    await waitFor(() => expect(result.current.detailError).toContain("Không tìm thấy"));
    act(() => result.current.reloadDetail());
    expect(result.current.detailLoading).toBe(true);
    await waitFor(() => expect(result.current.agent?.id).toBe("a"));
    expect(result.current.detailError).toBe("");
  });
});

describe("useAgents independent streams and cancellation guards", () => {
  it("streams step text and a merged tool result before the final answer", async () => {
    const runs = streamed();
    const { result } = renderHook(() => useAgents());
    await select(result);
    const run = await start(result, runs, "  Q  ");
    expect(run.payload).toEqual({ prompt: "Q" });
    act(() => {
      run.onEvent({ event: "execution", data: { execution: { id: "e", agent_id: "a", status: "running" } } });
      run.onEvent({ event: "step_delta", data: { step_index: 0, text: "Thinking" } });
      run.onEvent({ event: "tool_call", data: { step_index: 0, tool_call: { id: "t", name: "calculator", arguments: { expression: "2+2" } } } });
      run.onEvent({ event: "tool_result", data: { step_index: 0, tool_call: { id: "t", status: "success", result: 4 } } });
    });
    expect(result.current.execution.steps[0]).toMatchObject({ content: "Thinking", tool_calls: [{ id: "t", result: 4 }] });
    act(() => run.onEvent({ event: "step_done", data: { step: { index: 0, content: "Saved", tool_calls: [] } } }));
    expect(result.current.execution.steps[0].content).toBe("Saved");
    await act(async () => {
      run.onEvent({ event: "done", data: { execution: execution("e") } });
      run.onEvent({ event: "step_delta", data: { step_index: 0, text: "Ignored after done" } });
      run.resolve();
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.execution.steps).toEqual([]);
    expect(result.current.execution.content).toBe("Final");
    expect(result.current.activeExecutionId).toBe("e");
    const secondRuns = runs.length;
    act(() => result.current.run("Second"));
    await waitFor(() => expect(runs).toHaveLength(secondRuns + 1));
    expect(runs[1].payload).toEqual({ prompt: "Second" });
    expect(result.current.execution.steps).toEqual([]);
    expect(result.current.execution.content).toBe("");
  });
  it("keeps execution_error visible and marks an interrupted stream as error", async () => {
    const runs = streamed();
    const { result } = renderHook(() => useAgents());
    await select(result);
    const run = await start(result, runs);
    act(() => run.onEvent({ event: "execution_error", data: { code: "agent_budget_exceeded", message: "UNSAFE" } }));
    expect(result.current.streamError).toContain("8000");
    expect(result.current.streamError).not.toContain("UNSAFE");
    await act(async () => run.resolve());
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    // No persisted id exists yet, but the current attempted run stays visible.
    expect(result.current.streamError).toContain("Luồng kết thúc");
  });
  it("reports pre-stream errors and releases the run lock", async () => {
    const runs = streamed();
    const { result } = renderHook(() => useAgents());
    await select(result);
    const run = await start(result, runs);
    await act(async () => run.reject({ response: { status: 409, data: { detail: { code: "model_not_tool_capable" } } } }));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.streamError).toContain("function calling");
  });
  it("stop keeps partial text and rejects late events and finally from the old stream", async () => {
    const runs = streamed();
    const { result } = renderHook(() => useAgents());
    await select(result);
    const old = await start(result, runs);
    act(() => {
      old.onEvent({ event: "execution", data: { execution: { id: "old", agent_id: "a", status: "running" } } });
      old.onEvent({ event: "step_delta", data: { step_index: 0, text: "Partial" } });
      result.current.stop();
    });
    expect(old.signal.aborted).toBe(true);
    expect(result.current.execution.status).toBe("stopped");
    expect(result.current.execution.steps[0].content).toBe("Partial");
    act(() => result.current.run("New"));
    await waitFor(() => expect(runs).toHaveLength(2));
    const current = runs[1];
    act(() => current.onEvent({ event: "execution", data: { execution: { id: "new", agent_id: "a", status: "running" } } }));
    await act(async () => {
      old.onEvent({ event: "done", data: { execution: execution("old") } });
      old.resolve();
    });
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.execution.id).toBe("new");
    expect(current.signal.aborted).toBe(false);
  });
  it("switching agents aborts immediately and cannot leak old output into a new stream", async () => {
    const runs = streamed();
    const { result } = renderHook(() => useAgents());
    await select(result);
    const old = await start(result, runs);
    await select(result, "b");
    expect(old.signal.aborted).toBe(true);
    expect(result.current.execution).toBe(null);
    act(() => result.current.run("B"));
    await waitFor(() => expect(runs).toHaveLength(2));
    act(() => runs[1].onEvent({ event: "execution", data: { execution: { id: "b-exec", agent_id: "b", status: "running" } } }));
    await act(async () => {
      old.onEvent({ event: "step_delta", data: { step_index: 0, text: "STALE" } });
      old.resolve();
    });
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.execution.agent_id).toBe("b");
    expect(result.current.execution.steps).toEqual([]);
  });
  it("unmount aborts the stream and ignores late callbacks", async () => {
    const runs = streamed();
    const { result, unmount } = renderHook(() => useAgents());
    await select(result);
    const run = await start(result, runs);
    unmount();
    expect(run.signal.aborted).toBe(true);
    await act(async () => { run.onEvent({ event: "done", data: { execution: execution("late") } }); run.resolve(); });
  });
});

describe("Agent provider picker integration", () => {
  it("initializes from saved provider rather than the first configured provider, and reloads both resources", async () => {
    const providers = ["first", "saved"].map((id) => ({ id, implemented: true, configured: true, enabled: true }));
    vi.spyOn(providerService, "list").mockResolvedValue({ providers });
    vi.spyOn(providerService, "models").mockResolvedValue({ models: [{ id: "synced", capabilities: { chat: true, function_calling: null } }] });
    const { result } = renderHook(() => useChatProviders("saved"));
    await waitFor(() => expect(result.current.catalog.loading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(result.current.providerId).toBe("saved");
    expect(result.current.models[0].id).toBe("synced");
    act(() => result.current.reload());
    expect(result.current.catalog.loading).toBe(true);
    expect(result.current.modelsLoading).toBe(true);
    await waitFor(() => expect(result.current.catalog.loading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(providerService.models.mock.calls[0][0]).toBe("saved");
  });
  it("ignores provider model failures from the previous selection", async () => {
    const old = deferred();
    const providers = ["first", "second"].map((id) => ({ id, implemented: true, configured: true, enabled: true }));
    vi.spyOn(providerService, "list").mockResolvedValue({ providers });
    vi.spyOn(providerService, "models").mockImplementationOnce(() => old.promise).mockResolvedValueOnce({ models: [{ id: "second-model" }] });
    const { result } = renderHook(() => useChatProviders("first"));
    await waitFor(() => expect(providerService.models).toHaveBeenCalledTimes(1));
    act(() => result.current.setProviderId("second"));
    await waitFor(() => expect(result.current.models[0]?.id).toBe("second-model"));
    await act(async () => old.reject({ response: { status: 500 } }));
    expect(result.current.modelsError).toBe("");
    expect(result.current.providerId).toBe("second");
  });
});

describe("useAgents stale response guards", () => {
  it("ignores old detail success and error across A → B → A", async () => {
    const old = deferred();
    const fresh = deferred();
    vi.spyOn(agentsService, "get").mockImplementationOnce(() => old.promise).mockResolvedValueOnce(agent("b")).mockImplementationOnce(() => fresh.promise);
    const { result } = renderHook(() => useAgents());
    act(() => result.current.selectAgent("a"));
    await waitFor(() => expect(agentsService.get).toHaveBeenCalledTimes(1));
    await select(result, "b");
    act(() => result.current.selectAgent("a"));
    await waitFor(() => expect(agentsService.get).toHaveBeenCalledTimes(3));
    await act(async () => fresh.resolve({ ...agent("a"), name: "Fresh" }));
    await act(async () => old.resolve({ ...agent("a"), name: "Stale" }));
    expect(result.current.agent.name).toBe("Fresh");
    expect(result.current.detailError).toBe("");
  });
  it("ignores stale execution detail after selecting another history row", async () => {
    const old = deferred();
    vi.spyOn(agentsService, "execution").mockImplementationOnce(() => old.promise).mockResolvedValueOnce(execution("new"));
    const { result } = renderHook(() => useAgents());
    await select(result);
    act(() => result.current.selectExecution("old"));
    await waitFor(() => expect(agentsService.execution).toHaveBeenCalledTimes(1));
    act(() => result.current.selectExecution("new"));
    await waitFor(() => expect(result.current.execution?.id).toBe("new"));
    await act(async () => old.reject({ response: { status: 404 } }));
    expect(result.current.execution.id).toBe("new");
    expect(result.current.executionError).toBe("");
  });
  it("ignores a stale list response after reload", async () => {
    const old = deferred();
    vi.spyOn(agentsService, "list").mockImplementationOnce(() => old.promise).mockResolvedValueOnce([agent("b")]);
    const { result } = renderHook(() => useAgents());
    await waitFor(() => expect(agentsService.list).toHaveBeenCalledTimes(1));
    act(() => result.current.reloadList());
    await waitFor(() => expect(result.current.agents.items[0]?.id).toBe("b"));
    await act(async () => old.resolve([agent("a")]));
    expect(result.current.agents.items.map((item) => item.id)).toEqual(["b"]);
  });
  it("does not select a late CRUD response after the user changes agents", async () => {
    const old = deferred();
    vi.spyOn(agentsService, "patch").mockImplementation(() => old.promise);
    const { result } = renderHook(() => useAgents());
    await select(result);
    let pending;
    act(() => { pending = result.current.saveAgent({ name: "A" }); });
    await select(result, "b");
    await act(async () => { old.resolve(agent("a")); await pending; });
    expect(result.current.activeId).toBe("b");
    expect(result.current.busy).toBe("");
  });
});
