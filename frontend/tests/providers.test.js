import { afterEach, describe, expect, it } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api, refreshClient } from "../services/api";
import { providerService } from "../services/providers";
import { capabilityLabel, filterModels, getProviderError, providerFailureReason, providerStatus, validateApiKey } from "../utils/providers";

const mock = new MockAdapter(api);
const refresh = new MockAdapter(refreshClient);
afterEach(() => { mock.reset(); refresh.reset(); });

describe("provider API contract", () => {
  it("lists provider metadata through the authenticated same-origin client", async () => {
    mock.onGet("/ai/providers").reply(200, { encryption_ready: true, providers: [] });
    expect(await providerService.list()).toEqual({ encryption_ready: true, providers: [] });
  });
  it("submits a key only in the write body, never a URL parameter", async () => {
    mock.onPatch("/ai/providers/openai").reply(200, { id: "openai", configured: true });
    await providerService.update("openai", { api_key: "test-only-example-key" });
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ api_key: "test-only-example-key" });
    expect(mock.history.patch[0].url).not.toContain("test-only-example-key");
  });
  it("uses saved credentials for test, without resending key", async () => {
    mock.onPost("/ai/providers/gemini/test").reply(200, { scope: "model_listing", model_count: 0 });
    const result = await providerService.test("gemini");
    expect(result.scope).toBe("model_listing");
    expect(mock.history.post[0].data).toBe("{}");
    expect(mock.history.post[0].timeout).toBe(45000);
  });
  it("does not refresh auth when upstream rejects a provider key", async () => {
    mock.onPost("/ai/providers/openai/test").reply(400, { detail: { code: "provider_authentication_failed" } });
    await expect(providerService.test("openai")).rejects.toMatchObject({ response: { status: 400 } });
    expect(refresh.history.post).toHaveLength(0);
  });
  it("loads model cache and removes a connection using correct methods", async () => {
    mock.onGet("/ai/providers/gemini/models").reply(200, { provider: "gemini", models: [], synced_at: null });
    mock.onDelete("/ai/providers/gemini").reply(204);
    expect((await providerService.models("gemini")).models).toEqual([]);
    await providerService.disconnect("gemini");
    expect(mock.history.delete).toHaveLength(1);
  });
});

describe("validation and truthful statuses", () => {
  it("validates key format without returning its contents", () => {
    expect(validateApiKey("  test-only-key  ")).toBe("");
    for (const key of ["", "short", "test key with spaces", "key\nheader", "áááááááá", "x".repeat(4097)]) expect(validateApiKey(key)).not.toBe("");
  });
  it("does not confuse saved or enabled with tested connectivity", () => {
    expect(providerStatus({ implemented: true, configured: true, enabled: true, connection_status: "untested" }).label).toBe("Chưa kiểm tra");
    expect(providerStatus({ implemented: true, configured: false }).label).toBe("Chưa kết nối");
    expect(providerStatus({ implemented: false }).label).toBe("Sắp tích hợp");
  });
  it("keeps capability uncertainty explicit", () => {
    expect(capabilityLabel(null)).toBe("Chưa xác định");
    expect(capabilityLabel(undefined)).toBe("Chưa xác định");
    expect(capabilityLabel(true)).toBe("Có");
    expect(capabilityLabel(false)).toBe("Không");
  });
  it("searches only the supplied model catalog", () => {
    expect(filterModels([{ id: "test-id", display_name: "Fixture Model" }], "fixture")).toHaveLength(1);
    expect(filterModels([], "gpt")).toEqual([]);
  });
  it("never displays raw upstream errors containing secrets", () => {
    const error = { response: { status: 400, data: { detail: { code: "provider_authentication_failed", message: "LEAKED-KEY" } } } };
    expect(getProviderError(error)).not.toContain("LEAKED-KEY");
    expect(getProviderError(error)).toContain("Provider từ chối");
    expect(getProviderError({ response: { status: 500, data: { detail: "LEAKED-KEY" } } })).not.toContain("LEAKED-KEY");
  });
  it("explains a stored failed check with its specific reason", () => {
    expect(providerFailureReason("provider_authentication_failed")).toContain("Provider từ chối");
    expect(providerFailureReason("provider_timeout")).toContain("quá lâu");
    expect(providerFailureReason("provider_rate_limited")).toContain("giới hạn");
    expect(providerFailureReason(undefined)).toContain("chưa thành công");
    expect(providerFailureReason("toString")).toContain("chưa thành công");
  });
});
