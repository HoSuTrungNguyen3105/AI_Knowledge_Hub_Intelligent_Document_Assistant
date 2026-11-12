// @vitest-environment jsdom
// Every response here is an isolated test fixture, never app data or a real key.
import { afterEach, describe, expect, it, vi } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api, refreshClient } from "../services/api";
import { compareService } from "../services/compare";
import { compareErrorFromEvent, formatCost, getCompareError, runStatusLabels } from "../utils/compare";

const mock = new MockAdapter(api);
const refresh = new MockAdapter(refreshClient);

const EXECUTE_SSE =
  'event: comparison\ndata: {"comparison":{"id":"x1","runs":[]}}\n\n' +
  'event: run_delta\ndata: {"run_id":"r1","text":"Answer"}\n\n' +
  'event: run_delta\ndata: {"run_id":"r2","text":"Other"}\n\n' +
  'event: run_done\ndata: {"run":{"id":"r1","status":"success","content":"Answer"}}\n\n' +
  'event: run_error\ndata: {"run":{"id":"r2","status":"error","error_code":"generation_failed"}}\n\n' +
  'event: done\ndata: {"comparison":{"id":"x1","runs":[{"id":"r1"},{"id":"r2"}]}}\n\n';

function bodyFrom(chunks) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    getReader: () => ({
      read: async () => (index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : { done: true, value: undefined }),
    }),
  };
}
function sseResponse(text, status = 200) {
  return { ok: status >= 200 && status < 300, status, body: bodyFrom([text]), json: async () => JSON.parse(text) };
}

afterEach(() => { mock.reset(); refresh.reset(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("compare REST contract", () => {
  it("lists comparisons from the response envelope", async () => {
    mock.onGet("/ai/compare/comparisons").reply(200, { comparisons: [{ id: "x1" }] });
    expect(await compareService.list()).toEqual([{ id: "x1" }]);
  });
  it("creates a comparison with the exact payload", async () => {
    mock.onPost("/ai/compare/comparisons").reply(201, { id: "x1", runs: [] });
    const payload = { prompt: "So sánh", targets: [{ provider: "groq", model: "a" }, { provider: "groq", model: "b" }] };
    expect(await compareService.create(payload)).toMatchObject({ id: "x1" });
    expect(JSON.parse(mock.history.post[0].data)).toEqual(payload);
  });
  it("gets and deletes a comparison by id", async () => {
    mock.onGet("/ai/compare/comparisons/x1").reply(200, { id: "x1", runs: [] });
    mock.onDelete("/ai/compare/comparisons/x1").reply(204);
    expect((await compareService.get("x1")).runs).toEqual([]);
    await compareService.remove("x1");
    expect(mock.history.delete).toHaveLength(1);
  });
});

describe("compare SSE transport", () => {
  it("execute POSTs an empty body and streams parallel run events", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(EXECUTE_SSE));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    await compareService.execute("x1", { onEvent: (event) => events.push(event) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/ai/compare/comparisons/x1/execute");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body)).toEqual({});
    expect(events.map((event) => event.event)).toEqual(["comparison", "run_delta", "run_delta", "run_done", "run_error", "done"]);
    expect(events[1].data.run_id).toBe("r1");
    expect(events[4].data.run.error_code).toBe("generation_failed");
  });
  it("synthesize POSTs the chosen provider/model", async () => {
    const text = 'event: synthesis_delta\ndata: {"text":"Gộp"}\n\nevent: synthesis_done\ndata: {"synthesis":{"status":"success","content":"Gộp"}}\n\nevent: done\ndata: {"comparison":{"id":"x1"}}\n\n';
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(text));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    await compareService.synthesize("x1", { provider: "groq", model: "a" }, { onEvent: (event) => events.push(event) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/ai/compare/comparisons/x1/synthesize");
    expect(JSON.parse(init.body)).toEqual({ provider: "groq", model: "a" });
    expect(events.map((event) => event.event)).toEqual(["synthesis_delta", "synthesis_done", "done"]);
  });
  it("maps a validation error before the stream to the axios error shape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse('{"detail":{"code":"no_successful_runs"}}', 409)));
    await expect(compareService.synthesize("x1", { provider: "groq", model: "a" }, {}))
      .rejects.toMatchObject({ response: { status: 409, data: { detail: { code: "no_successful_runs" } } } });
  });
  it("refreshes the session once on 401 then retries execute", async () => {
    refresh.onPost("/auth/refresh").reply(200, {});
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, body: bodyFrom([]), json: async () => ({}) })
      .mockResolvedValueOnce(sseResponse(EXECUTE_SSE));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    await compareService.execute("x1", { onEvent: (event) => events.push(event) });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refresh.history.post).toHaveLength(1);
    expect(events.at(-1).event).toBe("done");
  });
});

describe("compare error copy and cost formatting", () => {
  it("maps backend codes to fixed Vietnamese without echoing upstream text", () => {
    const error = { response: { status: 409, data: { detail: { code: "no_successful_runs", message: "LEAKED-KEY" } } } };
    expect(getCompareError(error)).toContain("Chưa có câu trả lời thành công");
    expect(getCompareError(error)).not.toContain("LEAKED-KEY");
    expect(getCompareError({ response: { status: 422, data: { detail: { code: "invalid_comparison_targets" } } } })).toContain("2 đến 4");
  });
  it("falls back by status for unknown codes and network errors", () => {
    expect(getCompareError({ response: { status: 401 } })).toContain("hết hạn");
    expect(getCompareError({ response: { status: 409 } })).toContain("không còn phù hợp");
    expect(getCompareError({ response: { status: 422 } })).toContain("chưa hợp lệ");
    expect(getCompareError({})).toContain("Không kết nối");
  });
  it("maps SSE error events and unknown codes safely", () => {
    expect(compareErrorFromEvent({ code: "generation_failed" })).toContain("không hợp lệ");
    expect(compareErrorFromEvent({ code: "toString" })).toContain("gặp lỗi");
    expect(compareErrorFromEvent({})).toContain("gặp lỗi");
  });
  it("formats estimated cost truthfully and marks missing pricing", () => {
    expect(formatCost(null)).toBe("—");
    expect(formatCost(undefined)).toBe("—");
    expect(formatCost(1.3e-5)).toBe("$0.000013");
    expect(formatCost(0.02)).toBe("$0.0200");
    expect(formatCost(0)).toBe("$0.000000");
    expect(runStatusLabels.error).toBe("Lỗi");
    expect(runStatusLabels.pending).toBe("Đang chờ");
  });
});