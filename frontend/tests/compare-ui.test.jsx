// @vitest-environment jsdom
// All fixtures here are isolated test data, never app records or real keys.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { compareService } from "../services/compare";
import { RunColumn } from "../components/compare/run-column";
import { CompareSetup } from "../components/compare/compare-setup";
import { ComparisonList } from "../components/compare/comparison-list";
import { ComparisonView } from "../components/compare/comparison-view";
import { SynthesisPanel } from "../components/compare/synthesis-panel";
import { useCompare } from "../hooks/use-compare";

vi.mock("next/link", async () => {
  const React = await import("react");
  return { default: ({ children, href, ...props }) => React.createElement("a", { href, ...props }, children) };
});

const mock = new MockAdapter(api);
// jsdom does not implement the dialog element API used by ConfirmDialog.
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); mock.reset(); vi.restoreAllMocks(); });

const baseProviders = {
  catalog: { data: null, loading: false, error: "" },
  available: [{ id: "groq", name: "Groq" }],
  providerId: "groq",
  setProviderId: () => {},
  models: [{ id: "a", display_name: "Model A", capabilities: { chat: true } }, { id: "b", display_name: "Model B", capabilities: { chat: true } }],
  modelsLoading: false,
  modelsError: "",
  reload: () => {},
};

const successRun = { id: "r1", provider: "groq", model: "a", status: "success", content: "Answer A", input_tokens: 7, output_tokens: 3, latency_ms: 1200, error_code: null, estimated_cost: 1.3e-5 };

describe("RunColumn", () => {
  it("shows provider, model, status and real usage meta with estimated cost", () => {
    render(<RunColumn run={successRun} streaming={false} />);
    expect(screen.getByText("groq")).toBeTruthy();
    expect(screen.getByText("a")).toBeTruthy();
    expect(screen.getByText("Hoàn tất")).toBeTruthy();
    expect(screen.getByText("7 token vào")).toBeTruthy();
    expect(screen.getByText("3 token ra")).toBeTruthy();
    expect(screen.getByText("1.2 s")).toBeTruthy();
    expect(screen.getByText("≈ $0.000013")).toBeTruthy();
  });
  it("copies the answer to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<RunColumn run={successRun} streaming={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Sao chép câu trả lời của a" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Answer A"));
  });
  it("flags a failed run without hiding the error code", () => {
    render(<RunColumn run={{ ...successRun, status: "error", content: "", error_code: "generation_failed", estimated_cost: null }} streaming={false} />);
    expect(screen.getByText("Lỗi")).toBeTruthy();
    expect(screen.getByText(/Không tạo được nội dung/)).toBeTruthy();
    expect(screen.getByText(/generation_failed/)).toBeTruthy();
  });
  it("shows a waiting placeholder then live streaming text", () => {
    const pending = { ...successRun, status: "pending", content: "", input_tokens: null, output_tokens: null, latency_ms: null, estimated_cost: null };
    const { rerender } = render(<RunColumn run={pending} streaming />);
    expect(screen.getByText(/Đang tạo câu trả lời/)).toBeTruthy();
    rerender(<RunColumn run={pending} liveText="Đang trả lời" streaming />);
    expect(screen.getByText("Đang trả lời")).toBeTruthy();
  });
});

describe("CompareSetup", () => {
  it("links to settings when no provider is ready", () => {
    render(<CompareSetup providers={{ ...baseProviders, available: [], providerId: "", models: [] }} busy={false} onCreate={() => {}} />);
    expect(screen.getByText("Chưa có provider sẵn sàng")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Mở Cài đặt AI/ }).getAttribute("href")).toBe("/settings");
  });
  it("requires two distinct targets and submits the exact payload", () => {
    const onCreate = vi.fn();
    render(<CompareSetup providers={baseProviders} busy={false} onCreate={onCreate} />);
    const submit = screen.getByRole("button", { name: /Tạo phép so sánh/ });
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Câu hỏi chung"), { target: { value: "  So sánh A và B  " } });
    fireEvent.click(screen.getByRole("button", { name: /Thêm model vào so sánh/ }));
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: /Thêm model vào so sánh/ }));
    expect(submit.disabled).toBe(false);
    fireEvent.click(submit);
    expect(onCreate).toHaveBeenCalledWith({ prompt: "So sánh A và B", targets: [{ provider: "groq", model: "a" }, { provider: "groq", model: "b" }] });
  });
  it("prevents adding the same model twice and allows removal", () => {
    render(<CompareSetup providers={baseProviders} busy={false} onCreate={() => {}} />);
    const add = screen.getByRole("button", { name: /Thêm model vào so sánh/ });
    fireEvent.click(add);
    expect(screen.getByRole("button", { name: /Model đã có trong danh sách/ }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Bỏ Groq Model A" }));
    expect(screen.queryByRole("button", { name: "Bỏ Groq Model A" })).toBeNull();
  });
  it("includes optional settings when provided", () => {
    const onCreate = vi.fn();
    render(<CompareSetup providers={baseProviders} busy={false} onCreate={onCreate} />);
    fireEvent.change(screen.getByLabelText("Câu hỏi chung"), { target: { value: "Q" } });
    fireEvent.click(screen.getByRole("button", { name: /Thêm model vào so sánh/ }));
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "b" } });
    fireEvent.click(screen.getByRole("button", { name: /Thêm model vào so sánh/ }));
    fireEvent.change(screen.getByLabelText("Tên phép so sánh (tùy chọn)"), { target: { value: " Tiêu đề " } });
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "0.7" } });
    fireEvent.click(screen.getByRole("button", { name: /Tạo phép so sánh/ }));
    expect(onCreate).toHaveBeenCalledWith({ prompt: "Q", targets: [{ provider: "groq", model: "a" }, { provider: "groq", model: "b" }], title: "Tiêu đề", temperature: 0.7 });
  });
});

describe("ComparisonList", () => {
  const base = { activeId: null, onSelect: () => {}, onNew: () => {}, onReload: () => {}, busy: "" };
  it("shows an empty state", () => {
    render(<ComparisonList {...base} comparisons={{ items: [], loading: false, error: "" }} />);
    expect(screen.getByText("Chưa có phép so sánh nào.")).toBeTruthy();
  });
  it("renders a comparison with its target count", () => {
    const item = { id: "x1", title: "Tiêu đề", targets: [{ provider: "groq", model: "a" }, { provider: "groq", model: "b" }], has_synthesis: true, updated_at: "2026-11-11T10:00:00Z" };
    render(<ComparisonList {...base} comparisons={{ items: [item], loading: false, error: "" }} />);
    expect(screen.getByText("Tiêu đề")).toBeTruthy();
    expect(screen.getByText(/2 model · groq, groq/)).toBeTruthy();
  });
});

describe("SynthesisPanel", () => {
  const base = { providers: baseProviders, synthesis: null, liveText: "", busy: false, streaming: false, onSynthesize: () => {} };
  it("explains when there is nothing to synthesize and disables the action", () => {
    render(<SynthesisPanel {...base} canSynthesize={false} />);
    expect(screen.getByText(/Chưa có câu trả lời thành công/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Tổng hợp câu trả lời/ }).disabled).toBe(true);
  });
  it("submits the chosen provider/model when synthesis is possible", () => {
    const onSynthesize = vi.fn();
    render(<SynthesisPanel {...base} canSynthesize onSynthesize={onSynthesize} />);
    fireEvent.click(screen.getByRole("button", { name: /Tổng hợp câu trả lời/ }));
    expect(onSynthesize).toHaveBeenCalledWith({ provider: "groq", model: "a" });
  });
});

describe("ComparisonView", () => {
  const controller = {
    comparison: { id: "x1", title: "Tiêu đề", prompt: "Câu hỏi chung", runs: [successRun, { ...successRun, id: "r2", model: "b", status: "pending", content: "" }], synthesis: null },
    detailLoading: false, detailError: "", runText: {}, synthesisText: "", phase: null, isStreaming: false,
    streamError: "", busy: "", confirmDelete: false, setConfirmDelete: () => {}, canExecute: true, canSynthesize: true,
    execute: vi.fn(), synthesize: () => {}, stop: () => {}, deleteComparison: () => {}, reloadDetail: () => {},
  };
  it("renders the prompt, one column per run and a re-run action", () => {
    render(<ComparisonView controller={controller} providers={baseProviders} />);
    expect(screen.getByText("Câu hỏi chung")).toBeTruthy();
    expect(screen.getByText("Answer A")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Chạy lại/ }));
    expect(controller.execute).toHaveBeenCalledTimes(1);
  });
  it("offers retry when the detail fails to load", () => {
    const reloadDetail = vi.fn();
    render(<ComparisonView controller={{ ...controller, comparison: null, detailError: "Lỗi mạng", reloadDetail }} providers={baseProviders} />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(reloadDetail).toHaveBeenCalledTimes(1);
  });
});

describe("useCompare", () => {
  const detail = {
    id: "x1", title: "T", prompt: "Q", synthesis: null,
    runs: [
      { id: "r1", provider: "groq", model: "a", status: "pending", content: "" },
      { id: "r2", provider: "groq", model: "b", status: "pending", content: "" },
    ],
  };
  const finalDetail = {
    ...detail,
    runs: [
      { id: "r1", provider: "groq", model: "a", status: "success", content: "Answer A" },
      { id: "r2", provider: "groq", model: "b", status: "error", content: "", error_code: "generation_failed" },
    ],
  };

  it("execute streams parallel runs and isolates a failure", async () => {
    mock.onGet("/ai/compare/comparisons").reply(200, { comparisons: [] });
    mock.onGet("/ai/compare/comparisons/x1").reply(200, detail);
    vi.spyOn(compareService, "execute").mockImplementation((id, { onEvent }) => {
      onEvent({ event: "comparison", data: { comparison: detail } });
      onEvent({ event: "run_delta", data: { run_id: "r1", text: "Answer" } });
      onEvent({ event: "run_done", data: { run: finalDetail.runs[0] } });
      onEvent({ event: "run_error", data: { run: finalDetail.runs[1] } });
      onEvent({ event: "done", data: { comparison: finalDetail } });
      return Promise.resolve();
    });
    const { result } = renderHook(() => useCompare());
    act(() => result.current.selectComparison("x1"));
    await waitFor(() => expect(result.current.comparison?.id).toBe("x1"));
    act(() => result.current.execute());
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    const runs = result.current.comparison.runs;
    expect(runs.find((run) => run.id === "r1").status).toBe("success");
    expect(runs.find((run) => run.id === "r2").status).toBe("error");
    expect(result.current.canSynthesize).toBe(true);
  });

  it("synthesize streams a combined answer", async () => {
    mock.onGet("/ai/compare/comparisons").reply(200, { comparisons: [] });
    mock.onGet("/ai/compare/comparisons/x1").reply(200, finalDetail);
    vi.spyOn(compareService, "synthesize").mockImplementation((id, payload, { onEvent }) => {
      onEvent({ event: "synthesis_delta", data: { text: "Gộp" } });
      onEvent({ event: "synthesis_done", data: { synthesis: { provider: "groq", model: "a", status: "success", content: "Gộp" } } });
      onEvent({ event: "done", data: { comparison: { ...finalDetail, synthesis: { provider: "groq", model: "a", status: "success", content: "Gộp" } } } });
      return Promise.resolve();
    });
    const { result } = renderHook(() => useCompare());
    act(() => result.current.selectComparison("x1"));
    await waitFor(() => expect(result.current.comparison?.id).toBe("x1"));
    act(() => result.current.synthesize({ provider: "groq", model: "a" }));
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.comparison.synthesis.content).toBe("Gộp");
  });

  it("create selects the new comparison", async () => {
    mock.onGet("/ai/compare/comparisons").reply(200, { comparisons: [] });
    mock.onGet("/ai/compare/comparisons/x1").reply(200, detail);
    vi.spyOn(compareService, "create").mockResolvedValue({ id: "x1" });
    const { result } = renderHook(() => useCompare());
    await act(async () => { await result.current.createComparison({ prompt: "Q", targets: [{ provider: "groq", model: "a" }, { provider: "groq", model: "b" }] }); });
    await waitFor(() => expect(result.current.activeId).toBe("x1"));
  });
});