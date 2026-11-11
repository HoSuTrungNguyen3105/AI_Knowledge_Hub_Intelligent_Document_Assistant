// @vitest-environment jsdom
// All provider responses in this file are isolated test fixtures, never app data.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { api } from "../services/api";
import { ProviderSettings } from "../components/providers/provider-settings";
import { useSession } from "../stores/session";
import { useNotice } from "../stores/notice";

const mock = new MockAdapter(api);
let provider;
const emptyModels = { provider: "openai", models: [], synced_at: null };
const modelFixture = { id: "test-model", display_name: "Test-only model", capabilities: { chat: null, streaming: null, tools: null, embeddings: null }, input_token_limit: null, output_token_limit: null };

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  provider = { id: "openai", name: "OpenAI", implemented: true, configured: false, enabled: false, connection_status: "not_configured", default_model: null, model_count: 0, last_checked_at: null, models_synced_at: null, last_error_code: null };
  useSession.setState({ user: { id: "test-user", name: "Người kiểm thử", email: "test@example.com" }, status: "authenticated" });
  useNotice.setState({ notice: null });
  mock.onGet("/ai/providers").reply(() => [200, { encryption_ready: true, providers: [provider] }]);
  mock.onGet("/ai/providers/openai/models").reply(200, emptyModels);
});
afterEach(() => { cleanup(); mock.reset(); });

async function ready() {
  render(<ProviderSettings />);
  await screen.findByLabelText("Nhập API key");
  await screen.findByText("Chưa có model nào được đồng bộ.");
}

describe("provider management UI", () => {
  it("renders an empty real-API state without invented model options", async () => {
    await ready();
    expect(screen.getByRole("button", { name: "Kiểm tra & đồng bộ model" }).disabled).toBe(true);
    expect(screen.getByRole("combobox").options.length).toBe(1);
  });
  it("clears the key field after submission and displays only configured metadata", async () => {
    mock.onPatch("/ai/providers/openai").reply(() => {
      provider = { ...provider, configured: true, enabled: true, connection_status: "untested" };
      return [200, provider];
    });
    await ready();
    const key = screen.getByLabelText("Nhập API key");
    fireEvent.change(key, { target: { value: "test-only-key-never-rendered" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu API key" }));
    await screen.findByText("Chưa kiểm tra");
    expect(key.value).toBe("");
    expect(document.body.textContent).not.toContain("test-only-key-never-rendered");
    expect(localStorage.getItem("api_key")).toBeNull();
  });
  it("blocks secret submission when encryption is unavailable", async () => {
    mock.onGet("/ai/providers").reply(200, { encryption_ready: false, providers: [provider] });
    await ready();
    expect(screen.getByRole("button", { name: "Lưu API key" }).disabled).toBe(true);
    expect(screen.getByLabelText("Nhập API key").disabled).toBe(true);
    expect(screen.getByText("Chưa thể lưu API key an toàn")).toBeTruthy();
  });
  it("validates key characters before making a request", async () => {
    await ready();
    fireEvent.change(screen.getByLabelText("Nhập API key"), { target: { value: "invalid key with spaces" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu API key" }));
    await screen.findByRole("alert");
    expect(mock.history.patch).toHaveLength(0);
  });
  it("syncs models, preserves unknown capabilities and saves a selected default", async () => {
    provider = { ...provider, configured: true, enabled: true, connection_status: "untested" };
    mock.onPost("/ai/providers/openai/test").reply(() => {
      provider = { ...provider, connection_status: "connected", models_synced_at: "2026-11-11T08:00:00Z", model_count: 1 };
      mock.onGet("/ai/providers/openai/models").reply(200, { ...emptyModels, models: [modelFixture], synced_at: provider.models_synced_at });
      return [200, { provider, model_count: 1, scope: "model_listing" }];
    });
    mock.onPatch("/ai/providers/openai").reply((config) => {
      provider = { ...provider, ...JSON.parse(config.data) };
      return [200, provider];
    });
    render(<ProviderSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Kiểm tra & đồng bộ model" }));
    await screen.findByText("Đã xác minh danh sách model");
    await screen.findByText("Test-only model");
    expect(screen.getAllByText("Chưa xác định").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "test-model" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu model" }));
    await waitFor(() => expect(mock.history.patch).toHaveLength(1));
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ default_model: "test-model" });
  });
  it("requires confirmation to remove credentials and permits cancellation", async () => {
    provider = { ...provider, configured: true, connection_status: "untested" };
    mock.onDelete("/ai/providers/openai").reply(204);
    render(<ProviderSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Xóa API key" }));
    await screen.findByRole("dialog");
    expect(mock.history.delete).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(mock.history.delete).toHaveLength(0);
  });
});
