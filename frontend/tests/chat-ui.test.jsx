// @vitest-environment jsdom
// All fixtures here are isolated test data, never app records or real keys.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { Markdown } from "../components/chat/markdown";
import { MessageItem } from "../components/chat/message-item";
import { MessageList } from "../components/chat/message-list";
import { Composer } from "../components/chat/composer";
import { SetupPanel } from "../components/chat/setup-panel";
import { ConfigEditor } from "../components/chat/config-editor";
import { useChatProviders } from "../hooks/use-chat-providers";

vi.mock("next/link", async () => {
  const React = await import("react");
  return { default: ({ children, href, ...props }) => React.createElement("a", { href, ...props }, children) };
});

const mock = new MockAdapter(api);
afterEach(() => { cleanup(); mock.reset(); vi.restoreAllMocks(); });

describe("Markdown rendering", () => {
  it("renders GFM tables and code fences", () => {
    const { container } = render(<Markdown content={"# Tiêu đề\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n```js\nconst x = 1;\n```"} />);
    expect(screen.getByRole("heading", { name: "Tiêu đề" })).toBeTruthy();
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelector("pre code")?.textContent).toContain("const x = 1;");
  });
  it("does not inject raw HTML from model output", () => {
    const { container } = render(<Markdown content={'<img src=x onerror="alert(1)"><script>alert(2)</script>safe'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("safe");
  });
});

describe("MessageItem", () => {
  const userMessage = { id: "u1", role: "user", content: "Xin chào", status: "success" };
  const assistantMessage = { id: "a1", role: "assistant", content: "Trả lời", status: "success", model: "groq-model", input_tokens: 7, output_tokens: 3, latency_ms: 1200, error_code: null };

  it("renders user text plainly and copies to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<MessageItem message={userMessage} canRegenerate={false} onRegenerate={() => {}} />);
    expect(screen.getByText("Bạn")).toBeTruthy();
    expect(screen.getByText("Xin chào")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sao chép tin nhắn" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Xin chào"));
  });
  it("shows real usage meta and a regenerate action for the last assistant", () => {
    const onRegenerate = vi.fn();
    render(<MessageItem message={assistantMessage} canRegenerate onRegenerate={onRegenerate} />);
    expect(screen.getByText("groq-model")).toBeTruthy();
    expect(screen.getByText("7 token vào")).toBeTruthy();
    expect(screen.getByText("3 token ra")).toBeTruthy();
    expect(screen.getByText("1.2 s")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tạo lại câu trả lời" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });
  it("flags error and stopped assistant turns", () => {
    const { rerender } = render(<MessageItem message={{ ...assistantMessage, status: "error", error_code: "generation_failed" }} canRegenerate={false} onRegenerate={() => {}} />);
    expect(screen.getByText(/Không tạo được nội dung/)).toBeTruthy();
    expect(screen.getByText(/generation_failed/)).toBeTruthy();
    rerender(<MessageItem message={{ ...assistantMessage, status: "stopped" }} canRegenerate={false} onRegenerate={() => {}} />);
    expect(screen.getByText("Đã dừng giữa chừng")).toBeTruthy();
  });
});

describe("MessageList states", () => {
  const base = { messages: [], streaming: null, canRegenerate: false, onRegenerate: () => {}, loading: false, error: "", onRetry: () => {} };
  it("shows a loading status", () => {
    render(<MessageList {...base} loading />);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText("Đang tải hội thoại…")).toBeTruthy();
  });
  it("offers retry on error", () => {
    const onRetry = vi.fn();
    render(<MessageList {...base} error="Lỗi mạng" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
  it("shows an empty prompt when there are no messages", () => {
    render(<MessageList {...base} />);
    expect(screen.getByText("Bắt đầu trò chuyện")).toBeTruthy();
  });
  it("renders a streaming placeholder then live content", () => {
    const { rerender } = render(<MessageList {...base} streaming={{ text: "" }} />);
    expect(screen.getByText(/Đang soạn câu trả lời/)).toBeTruthy();
    rerender(<MessageList {...base} streaming={{ text: "Đang trả lời" }} />);
    expect(screen.getByText("Đang trả lời")).toBeTruthy();
  });
});

describe("Composer", () => {
  it("sends trimmed text on Enter and clears the field", () => {
    const onSend = vi.fn();
    render(<Composer disabled={false} isStreaming={false} onSend={onSend} onStop={() => {}} error="" />);
    const textarea = screen.getByLabelText("Nội dung tin nhắn");
    fireEvent.change(textarea, { target: { value: "  hi  " } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledWith("hi");
    expect(textarea.value).toBe("");
  });
  it("does not send on Shift+Enter", () => {
    const onSend = vi.fn();
    render(<Composer disabled={false} isStreaming={false} onSend={onSend} onStop={() => {}} error="" />);
    const textarea = screen.getByLabelText("Nội dung tin nhắn");
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });
  it("shows a stop control while streaming", () => {
    const onStop = vi.fn();
    render(<Composer disabled={false} isStreaming onSend={() => {}} onStop={onStop} error="" />);
    fireEvent.click(screen.getByRole("button", { name: "Dừng" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });
  it("surfaces a stream error and blocks sending when disabled", () => {
    const onSend = vi.fn();
    render(<Composer disabled isStreaming={false} onSend={onSend} onStop={() => {}} error="Provider lỗi" />);
    expect(screen.getByRole("alert").textContent).toContain("Provider lỗi");
    const textarea = screen.getByLabelText("Nội dung tin nhắn");
    fireEvent.change(textarea, { target: { value: "hi" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("SetupPanel", () => {
  const baseProviders = {
    catalog: { data: null, loading: false, error: "" },
    available: [{ id: "groq", name: "Groq" }],
    providerId: "groq",
    setProviderId: () => {},
    models: [{ id: "llama", display_name: "Llama", capabilities: { chat: true } }],
    modelsLoading: false,
    modelsError: "",
    reload: () => {},
  };
  it("links to settings when no provider is ready", () => {
    render(<SetupPanel providers={{ ...baseProviders, available: [], providerId: "", models: [] }} busy={false} onCreate={() => {}} />);
    expect(screen.getByText("Chưa có provider sẵn sàng")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Mở Cài đặt AI/ }).getAttribute("href")).toBe("/settings");
  });
  it("shows catalog loading and error states with retry", () => {
    const { rerender } = render(<SetupPanel providers={{ ...baseProviders, catalog: { data: null, loading: true, error: "" } }} busy={false} onCreate={() => {}} />);
    expect(screen.getByRole("status")).toBeTruthy();
    const reload = vi.fn();
    rerender(<SetupPanel providers={{ ...baseProviders, catalog: { data: null, loading: false, error: "Lỗi" }, reload }} busy={false} onCreate={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(reload).toHaveBeenCalledTimes(1);
  });
  it("submits only provider/model when optionals are empty", () => {
    const onCreate = vi.fn();
    render(<SetupPanel providers={baseProviders} busy={false} onCreate={onCreate} />);
    fireEvent.click(screen.getByRole("button", { name: /Bắt đầu hội thoại/ }));
    expect(onCreate).toHaveBeenCalledWith({ provider: "groq", model: "llama" });
  });
  it("includes optional settings when provided", () => {
    const onCreate = vi.fn();
    render(<SetupPanel providers={baseProviders} busy={false} onCreate={onCreate} />);
    fireEvent.change(screen.getByLabelText("Tên hội thoại (tùy chọn)"), { target: { value: "  Học tập  " } });
    fireEvent.change(screen.getByLabelText("System prompt (tùy chọn)"), { target: { value: "Bạn là trợ lý" } });
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "0.7" } });
    fireEvent.change(screen.getByLabelText("Giới hạn token ra"), { target: { value: "512" } });
    fireEvent.click(screen.getByRole("button", { name: /Bắt đầu hội thoại/ }));
    expect(onCreate).toHaveBeenCalledWith({ provider: "groq", model: "llama", title: "Học tập", system_prompt: "Bạn là trợ lý", temperature: 0.7, max_output_tokens: 512 });
  });
  it("disables submit when no chat model is synced", () => {
    render(<SetupPanel providers={{ ...baseProviders, models: [] }} busy={false} onCreate={() => {}} />);
    expect(screen.getByRole("button", { name: /Bắt đầu hội thoại/ }).disabled).toBe(true);
  });
});

describe("ConfigEditor", () => {
  it("saves null for empty optionals", () => {
    const onSave = vi.fn();
    render(<ConfigEditor conversation={{ id: "c1", system_prompt: null, temperature: null, max_output_tokens: null }} busy={false} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình/ }));
    expect(onSave).toHaveBeenCalledWith({ system_prompt: null, temperature: null, max_output_tokens: null });
  });
  it("trims a blank system prompt to null and parses numbers", () => {
    const onSave = vi.fn();
    render(<ConfigEditor conversation={{ id: "c1", system_prompt: "Giữ nguyên", temperature: 0.4, max_output_tokens: 256 }} busy={false} onSave={onSave} />);
    fireEvent.change(screen.getByLabelText("System prompt"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Temperature"), { target: { value: "1.2" } });
    fireEvent.click(screen.getByRole("button", { name: /Lưu cấu hình/ }));
    expect(onSave).toHaveBeenCalledWith({ system_prompt: null, temperature: 1.2, max_output_tokens: 256 });
  });
});

describe("useChatProviders", () => {
  it("filters to configured+enabled providers and chat-capable models", async () => {
    const providers = [
      { id: "groq", name: "Groq", implemented: true, configured: true, enabled: true },
      { id: "openai", name: "OpenAI", implemented: true, configured: false, enabled: false },
      { id: "anthropic", name: "Anthropic", implemented: false, configured: true, enabled: true },
    ];
    mock.onGet("/ai/providers").reply(200, { encryption_ready: true, providers });
    mock.onGet("/ai/providers/groq/models").reply(200, {
      provider: "groq",
      models: [
        { id: "chat-yes", capabilities: { chat: true } },
        { id: "chat-unknown", capabilities: { chat: null } },
        { id: "chat-no", capabilities: { chat: false } },
      ],
      synced_at: "2026-11-11T00:00:00Z",
    });
    const { result } = renderHook(() => useChatProviders());
    await waitFor(() => expect(result.current.catalog.loading).toBe(false));
    await waitFor(() => expect(result.current.modelsLoading).toBe(false));
    expect(result.current.available.map((provider) => provider.id)).toEqual(["groq"]);
    expect(result.current.providerId).toBe("groq");
    expect(result.current.models.map((model) => model.id)).toEqual(["chat-yes", "chat-unknown"]);
    expect(result.current.encryptionReady).toBe(true);
  });
});