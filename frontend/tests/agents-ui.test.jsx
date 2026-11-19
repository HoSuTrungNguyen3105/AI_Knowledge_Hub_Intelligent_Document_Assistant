// @vitest-environment jsdom
// Isolated API/provider fixtures for UI tests, never app data.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { agentsService } from "../services/agents";
import { useChatProviders } from "../hooks/use-chat-providers";
import { AgentEditor } from "../components/agents/agent-editor";
import { AgentList } from "../components/agents/agent-list";
import { AgentView } from "../components/agents/agent-view";
import { ExecutionDetail } from "../components/agents/execution-detail";
import { ExecutionHistory } from "../components/agents/execution-history";
import AgentsPage, { metadata } from "../app/(workspace)/agents/page";
import { sections } from "../utils/navigation";

vi.mock("../hooks/use-chat-providers", () => ({ useChatProviders: vi.fn() }));
vi.mock("next/link", async () => {
  const React = await import("react");
  return { default: ({ children, href, ...props }) => React.createElement("a", { href, ...props }, children) };
});
const mock = new MockAdapter(api);
const baseProviders = {
  available: [{ id: "groq", name: "Groq" }], providerId: "groq", setProviderId: vi.fn(),
  models: [{ id: "model", display_name: "Synced model", capabilities: { chat: true, function_calling: null } }],
  modelsLoading: false, modelsError: "", catalog: { loading: false, error: "" }, reload: vi.fn(),
};
const toolItems = [
  ...["calculator", "datetime", "data_analyzer"].map((name) => ({ name, description: `${name} description`, available: true, phase: 5, parameters: {} })),
  ...["document_search", "knowledge_search", "text_summarizer", "web_search"].map((name) => ({ name, description: `${name} description`, available: false, phase: 6, parameters: {} })),
];
const tools = { items: toolItems, loading: false, error: "" };
const agent = { id: "a", name: "Data Helper", description: "Analyze data", provider: "groq", model: "model", tools: ["calculator"], system_prompt: "Be careful", temperature: 0.5, max_output_tokens: 512, created_at: "2026-11-11T00:00:00Z", updated_at: "2026-11-11T00:00:00Z" };
const savedExecution = { id: "e", agent_id: "a", prompt: "Saved request", status: "success", content: "**Final answer**", step_count: 1, input_tokens: 10, output_tokens: 4, estimated_cost: 0.000014, latency_ms: 1000, created_at: "2026-11-11T00:00:00Z", steps: [{ index: 0, content: "Step explanation", tool_calls: [{ id: "t", name: "calculator", arguments: { expression: "2+2" }, status: "success", result: 4, latency_ms: 3 }] }], tool_executions: [{ tool_name: "calculator", result: 4 }] };
const viewController = {
  agent, activeId: "a", tools, busy: "", editing: false, setEditing: vi.fn(), saveAgent: vi.fn(), duplicateAgent: vi.fn(), setDeletion: vi.fn(), run: vi.fn(), stop: vi.fn(), isStreaming: false, streamError: "", reloadTools: vi.fn(),
  history: { items: [], loading: false, error: "" }, activeExecutionId: null, selectExecution: vi.fn(), reloadHistory: vi.fn(),
  execution: null, executionLoading: false, executionError: "", reloadExecution: vi.fn(),
};
beforeEach(() => {
  useChatProviders.mockReturnValue(baseProviders);
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); mock.reset(); vi.restoreAllMocks(); vi.clearAllMocks(); });

describe("Agent editor", () => {
  it("shows provider skeleton, error retry and real empty state", () => {
    const props = { tools, busy: false, onSave: vi.fn(), reloadTools: vi.fn() };
    useChatProviders.mockReturnValue({ ...baseProviders, catalog: { loading: true, error: "" } });
    const { rerender } = render(<AgentEditor {...props} />);
    expect(screen.getByRole("status", { name: "Đang tải provider" })).toBeTruthy();
    useChatProviders.mockReturnValue({ ...baseProviders, catalog: { loading: false, error: "Network error" } });
    rerender(<AgentEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại provider" }));
    expect(baseProviders.reload).toHaveBeenCalledTimes(1);
    useChatProviders.mockReturnValue({ ...baseProviders, available: [] });
    rerender(<AgentEditor {...props} />);
    expect(screen.getByRole("link", { name: "Mở Cài đặt AI" }).getAttribute("href")).toBe("/settings");
    expect(screen.getByText("Chưa có provider sẵn sàng")).toBeTruthy();
  });
  it("submits complete per-agent settings and only available selected tools", () => {
    const onSave = vi.fn();
    render(<AgentEditor tools={tools} busy={false} onSave={onSave} reloadTools={() => {}} />);
    const submit = screen.getByRole("button", { name: "Tạo Agent" });
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Tên Agent"), { target: { value: "  Helper  " } });
    fireEvent.change(screen.getByLabelText("Mô tả"), { target: { value: "  Work  " } });
    fireEvent.change(screen.getByLabelText("System prompt"), { target: { value: "Careful" } });
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "0.3" } });
    fireEvent.change(screen.getByLabelText("Giới hạn token ra"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /calculator description/ }));
    fireEvent.click(submit);
    expect(onSave).toHaveBeenCalledWith({ name: "Helper", description: "Work", provider: "groq", model: "model", system_prompt: "Careful", temperature: 0.3, max_output_tokens: 500, tools: ["calculator"] });
    expect(screen.getByText(/Khả năng function calling chưa xác định/)).toBeTruthy();
  });
  it("seeds edit values from the agent and preserves provider/model selection", () => {
    const onSave = vi.fn();
    render(<AgentEditor agent={agent} tools={tools} busy={false} onSave={onSave} reloadTools={() => {}} />);
    expect(useChatProviders).toHaveBeenCalledWith("groq");
    expect(screen.getByLabelText("Tên Agent").value).toBe("Data Helper");
    expect(screen.getByLabelText("System prompt").value).toBe("Be careful");
    fireEvent.click(screen.getByRole("button", { name: "Lưu Agent" }));
    expect(onSave).toHaveBeenCalledWith({ name: agent.name, description: agent.description, provider: "groq", model: "model", system_prompt: "Be careful", temperature: 0.5, max_output_tokens: 512, tools: ["calculator"] });
  });
  it("blocks known false tools and lets text-only configuration be saved", () => {
    useChatProviders.mockReturnValue({ ...baseProviders, available: [{ id: "groq", name: "Groq", capabilities: { function_calling: false } }] });
    render(<AgentEditor agent={agent} tools={tools} busy={false} onSave={() => {}} reloadTools={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /calculator description/ }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Lưu Agent" }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Bỏ chọn tất cả công cụ" }));
    expect(screen.getByRole("button", { name: "Lưu Agent" }).disabled).toBe(false);
  });
  it("disables all deferred tools, KB and Memory without claiming availability", () => {
    render(<AgentEditor tools={tools} busy={false} onSave={() => {}} reloadTools={() => {}} />);
    for (const name of ["document_search", "knowledge_search", "text_summarizer", "web_search"]) expect(screen.getByRole("checkbox", { name: new RegExp(name) }).matches(":disabled")).toBe(true);
    expect(screen.getByRole("checkbox", { name: /Knowledge Base/ }).matches(":disabled")).toBe(true);
    expect(screen.getByRole("checkbox", { name: /Memory/ }).matches(":disabled")).toBe(true);
  });
  it("blocks unavailable stored model rather than silently replacing it", () => {
    render(<AgentEditor agent={{ ...agent, model: "removed-model" }} tools={tools} busy={false} onSave={() => {}} reloadTools={() => {}} />);
    expect(screen.getByRole("button", { name: "Lưu Agent" }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Model đã đồng bộ"), { target: { value: "model" } });
    expect(screen.getByRole("button", { name: "Lưu Agent" }).disabled).toBe(false);
  });
  it("does not reuse a stale model after switching providers", () => {
    const props = { agent, tools, busy: false, onSave: vi.fn(), reloadTools: vi.fn() };
    const { rerender } = render(<AgentEditor {...props} />);
    useChatProviders.mockReturnValue({ ...baseProviders, providerId: "other", available: [{ id: "other", name: "Other" }], models: [{ id: "other-model", capabilities: {} }] });
    rerender(<AgentEditor {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Lưu Agent" }));
    expect(props.onSave).toHaveBeenCalledWith(expect.objectContaining({ provider: "other", model: "other-model" }));
  });
  it("blocks tool catalogue errors and invalid numeric limits, allows null defaults", () => {
    const onSave = vi.fn();
    const props = { tools: { ...tools, error: "Tools failed" }, busy: false, onSave, reloadTools: vi.fn() };
    const { rerender } = render(<AgentEditor {...props} />);
    fireEvent.change(screen.getByLabelText("Tên Agent"), { target: { value: "Helper" } });
    expect(screen.getByRole("button", { name: "Tạo Agent" }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại công cụ" }));
    expect(props.reloadTools).toHaveBeenCalledTimes(1);
    rerender(<AgentEditor {...props} tools={tools} />);
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "3" } });
    expect(screen.getByRole("button", { name: "Tạo Agent" }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Agent" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ temperature: null, max_output_tokens: null, tools: [] }));
  });
});

describe("Agent list, run view and execution details", () => {
  it("renders skeleton/error/empty/list states and initials avatar", () => {
    const controller = { agents: { items: [], loading: true, error: "" }, activeId: null, busy: "", selectAgent: vi.fn(), newAgent: vi.fn(), reloadList: vi.fn() };
    const { rerender } = render(<AgentList controller={controller} />);
    expect(screen.getByRole("status", { name: "Đang tải Agent" })).toBeTruthy();
    rerender(<AgentList controller={{ ...controller, agents: { items: [], loading: false, error: "Error" } }} />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại Agent" }));
    expect(controller.reloadList).toHaveBeenCalledTimes(1);
    rerender(<AgentList controller={{ ...controller, agents: { items: [], loading: false, error: "" } }} />);
    expect(screen.getByText("Chưa có Agent nào.")).toBeTruthy();
    rerender(<AgentList controller={{ ...controller, agents: { items: [agent], loading: false, error: "" } }} />);
    expect(screen.getByText("DH")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Data Helper/ }));
    expect(controller.selectAgent).toHaveBeenCalledWith("a");
  });
  it("requires execution prompt and sends only its trimmed text to the controller", () => {
    render(<AgentView controller={viewController} />);
    const button = screen.getByRole("button", { name: "Chạy Agent" });
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Yêu cầu thực thi"), { target: { value: "  Task  " } });
    fireEvent.click(button);
    expect(viewController.run).toHaveBeenCalledWith("Task");
    expect(screen.getByText(/6 bước · 120 giây · 8000/)).toBeTruthy();
    expect(screen.getByText(/Khả năng function calling chưa xác định/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Chỉnh sửa Agent" }));
    expect(viewController.setEditing).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: "Nhân bản Agent" }));
    expect(viewController.duplicateAgent).toHaveBeenCalledTimes(1);
  });
  it("blocks runs with explicit false function calling but allows text-only", () => {
    useChatProviders.mockReturnValue({ ...baseProviders, available: [{ id: "groq", name: "Groq", function_calling: false }] });
    const { rerender } = render(<AgentView controller={viewController} />);
    fireEvent.change(screen.getByLabelText("Yêu cầu thực thi"), { target: { value: "Task" } });
    expect(screen.getByRole("button", { name: "Chạy Agent" }).disabled).toBe(true);
    rerender(<AgentView controller={{ ...viewController, agent: { ...agent, tools: [] } }} />);
    expect(screen.getByRole("button", { name: "Chạy Agent" }).disabled).toBe(false);
  });
  it("shows stop while streaming and disables edits and history deletion", () => {
    render(<AgentView controller={{ ...viewController, isStreaming: true, history: { items: [savedExecution], loading: false, error: "" } }} />);
    fireEvent.click(screen.getByRole("button", { name: "Dừng thực thi" }));
    expect(viewController.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Chỉnh sửa Agent" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: /Xóa lượt thực thi:/ }).disabled).toBe(true);
  });
  it("renders actual step/tool trace, final Markdown, usage and estimated cost once", () => {
    render(<ExecutionDetail controller={{ ...viewController, execution: savedExecution }} />);
    expect(screen.getByText("Bước 1")).toBeTruthy();
    expect(screen.getByText("Step explanation")).toBeTruthy();
    expect(screen.getByText("Final answer").tagName).toBe("STRONG");
    expect(screen.getAllByText(/calculator · Hoàn tất/)).toHaveLength(1);
    expect(screen.getByText(/"expression": "2\+2"/)).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText("10 token vào")).toBeTruthy();
    expect(screen.getByText(/Chi phí ước tính: ≈ \$0.000014/)).toBeTruthy();
  });
  it("shows the historical target snapshot, never the current agent target", () => {
    render(<ExecutionDetail controller={{ ...viewController, execution: { ...savedExecution, provider: "openai", model: "historical-model" } }} />);
    expect(screen.getByLabelText("Model của lượt thực thi").textContent).toBe("Provider: openai · Model: historical-model");
    expect(screen.queryByText(/groq · model/)).toBeNull();
  });
  it("shows unknown historical target explicitly when no snapshot is available", () => {
    render(<ExecutionDetail controller={{ ...viewController, execution: savedExecution }} />);
    expect(screen.getByLabelText("Model của lượt thực thi").textContent).toBe("Provider: Chưa có thông tin · Model: Chưa có thông tin");
  });
  it("renders tool errors and missing final/pricing honestly", () => {
    render(<ExecutionDetail controller={{ ...viewController, execution: { ...savedExecution, status: "error", error_code: "agent_timeout", content: "", estimated_cost: null, steps: [{ index: 0, content: "Partial", tool_calls: [{ id: "t", name: "calculator", arguments: {}, status: "error", error_code: "tool_failed", result: null }] }] } }} />);
    expect(screen.getByText(/120 giây/)).toBeTruthy();
    expect(screen.getByText("tool_failed")).toBeTruthy();
    expect(screen.getByText("Lượt này chưa có câu trả lời cuối.")).toBeTruthy();
    expect(screen.getByText(/chưa có giá hoặc token/)).toBeTruthy();
  });
  it("offers execution detail retry and selectable/deletable history", () => {
    const { rerender } = render(<ExecutionDetail controller={{ ...viewController, executionError: "Failed" }} />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại lượt thực thi" }));
    expect(viewController.reloadExecution).toHaveBeenCalledTimes(1);
    rerender(<ExecutionHistory controller={{ ...viewController, history: { items: [savedExecution], loading: false, error: "" } }} />);
    fireEvent.click(screen.getByRole("button", { name: /Saved request Hoàn tất/ }));
    expect(viewController.selectExecution).toHaveBeenCalledWith("e");
    fireEvent.click(screen.getByRole("button", { name: /Xóa lượt thực thi:/ }));
    expect(viewController.setDeletion).toHaveBeenCalledWith({ agentId: "a", executionId: "e" });
  });
});

describe("real /agents page integration", () => {
  function routes() {
    mock.onGet("/ai/agents").reply(200, { agents: [agent] });
    mock.onGet("/ai/agents/tools").reply(200, { tools: toolItems });
    mock.onGet("/ai/agents/a").reply(200, agent);
    mock.onGet("/ai/agents/a/executions").reply(200, { executions: [savedExecution] });
    mock.onGet("/ai/agents/a/executions/e").reply(200, savedExecution);
  }
  it("resets an unsaved new-agent draft when Agent mới is requested", async () => {
    routes();
    render(<AgentsPage />);
    fireEvent.change(screen.getByLabelText("Tên Agent"), { target: { value: "Unsaved draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Agent mới" }));
    expect(screen.getByLabelText("Tên Agent").value).toBe("");
  });
  it("creates, edits and duplicates configuration from the concrete route", async () => {
    const records = [];
    mock.onGet("/ai/agents").reply(() => [200, { agents: records }]);
    mock.onGet("/ai/agents/tools").reply(200, { tools: toolItems });
    mock.onGet(/\/ai\/agents\/[ab]$/).reply((config) => [200, records.find((item) => item.id === config.url.split("/").at(-1))]);
    mock.onGet(/\/ai\/agents\/[ab]\/executions$/).reply(200, { executions: [] });
    mock.onPost("/ai/agents").reply((config) => {
      const created = { ...agent, ...JSON.parse(config.data) };
      records.push(created);
      return [201, created];
    });
    mock.onPatch("/ai/agents/a").reply((config) => {
      records[0] = { ...records[0], ...JSON.parse(config.data) };
      return [200, records[0]];
    });
    mock.onPost("/ai/agents/a/duplicate").reply(() => {
      const copy = { ...records[0], id: "b", name: "Copied Helper" };
      records.push(copy);
      return [201, copy];
    });
    render(<AgentsPage />);
    fireEvent.change(screen.getByLabelText("Tên Agent"), { target: { value: "Created Helper" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Tạo Agent" }).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Tạo Agent" }));
    await screen.findByRole("heading", { name: "Created Helper" });
    expect(JSON.parse(mock.history.post[0].data)).toMatchObject({ name: "Created Helper", provider: "groq", model: "model", tools: [] });
    fireEvent.click(screen.getByRole("button", { name: "Chỉnh sửa Agent" }));
    fireEvent.change(screen.getByLabelText("Tên Agent"), { target: { value: "Edited Helper" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Agent" }));
    await screen.findByRole("heading", { name: "Edited Helper" });
    expect(JSON.parse(mock.history.patch[0].data).name).toBe("Edited Helper");
    fireEvent.click(screen.getByRole("button", { name: "Nhân bản Agent" }));
    await screen.findByRole("heading", { name: "Copied Helper" });
    expect(mock.history.post.at(-1).url).toBe("/ai/agents/a/duplicate");
  });
  it("is a concrete route, not an upcoming placeholder, with confirmed agent deletion", async () => {
    routes();
    mock.onDelete("/ai/agents/a").reply(204);
    expect(metadata.title).toBe("Agent Studio");
    expect(sections.agents).toBeUndefined();
    render(<AgentsPage />);
    expect(screen.getByRole("heading", { name: "Agent Studio" })).toBeTruthy();
    await screen.findByRole("button", { name: /Data Helper groq/ });
    fireEvent.click(screen.getByRole("button", { name: /Data Helper groq/ }));
    await screen.findByRole("button", { name: "Xóa Agent" });
    fireEvent.click(screen.getByRole("button", { name: "Xóa Agent" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Xóa Agent này?" })).toBeTruthy();
    expect(mock.history.delete).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
    expect(mock.history.delete).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Xóa Agent" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Xóa Agent" }));
    await waitFor(() => expect(mock.history.delete).toHaveLength(1));
    await screen.findByRole("heading", { name: "Tạo Agent" });
  });
  it("selects saved execution details and confirms history deletion", async () => {
    routes();
    mock.onDelete("/ai/agents/a/executions/e").reply(204);
    render(<AgentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Data Helper groq/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Saved request Hoàn tất/ }));
    await screen.findByText("Final answer");
    fireEvent.click(screen.getByRole("button", { name: /Xóa lượt thực thi:/ }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Xóa lượt thực thi này?" })).toBeTruthy();
    expect(mock.history.delete).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Xóa lượt thực thi" }));
    await waitFor(() => expect(mock.history.delete[0]?.url).toBe("/ai/agents/a/executions/e"));
  });
  it("shows streamed steps and tool result live, then final answer", async () => {
    routes();
    let stream, resolve;
    vi.spyOn(agentsService, "run").mockImplementation((id, payload, options) => { stream = options; return new Promise((res) => { resolve = res; }); });
    render(<AgentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Data Helper groq/ }));
    await screen.findByLabelText("Yêu cầu thực thi");
    fireEvent.change(screen.getByLabelText("Yêu cầu thực thi"), { target: { value: "Live task" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Chạy Agent" }).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Chạy Agent" }));
    await waitFor(() => expect(stream).toBeTruthy());
    act(() => {
      stream.onEvent({ event: "execution", data: { execution: { id: "live", agent_id: "a", status: "running", prompt: "Live task" } } });
      stream.onEvent({ event: "step_delta", data: { step_index: 0, text: "Live explanation" } });
      stream.onEvent({ event: "tool_call", data: { step_index: 0, tool_call: { id: "t", name: "calculator", arguments: { expression: "2+2" }, status: "running" } } });
      stream.onEvent({ event: "tool_result", data: { step_index: 0, tool_call: { id: "t", status: "success", result: 4 } } });
    });
    expect(screen.getByText("Live explanation")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dừng thực thi" })).toBeTruthy();
    await act(async () => { stream.onEvent({ event: "done", data: { execution: { ...savedExecution, id: "live", prompt: "Live task" } } }); resolve(); });
    await screen.findByText("Final answer");
    expect(screen.queryByRole("button", { name: "Dừng thực thi" })).toBeNull();
  });
});
