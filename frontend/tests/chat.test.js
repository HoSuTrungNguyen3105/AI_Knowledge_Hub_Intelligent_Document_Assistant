// @vitest-environment jsdom
// Every response here is an isolated test fixture, never app data or a real key.
import { afterEach, describe, expect, it, vi } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api, refreshClient } from "../services/api";
import { chatService, readSSE, streamChat } from "../services/chat";
import { chatErrorFromEvent, formatLatency, formatTokens, getChatError, messageStatusLabels } from "../utils/chat";

const mock = new MockAdapter(api);
const refresh = new MockAdapter(refreshClient);

const SSE =
  'event: user_message\ndata: {"message":{"id":"m1","role":"user","content":"hi"}}\n\n' +
  'event: delta\ndata: {"text":"Hello"}\n\n' +
  'event: delta\ndata: {"text":" world"}\n\n' +
  'event: done\ndata: {"message":{"id":"m2","role":"assistant","content":"Hello world"}}\n\n';

// Minimal fetch-body stand-in: readSSE only needs body.getReader() + TextDecoder.
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

describe("chat REST contract", () => {
  it("lists conversations from the response envelope", async () => {
    mock.onGet("/ai/chat/conversations").reply(200, { conversations: [{ id: "c1" }] });
    expect(await chatService.list()).toEqual([{ id: "c1" }]);
  });
  it("creates a conversation with the exact payload", async () => {
    mock.onPost("/ai/chat/conversations").reply(201, { id: "c1", provider: "groq", model: "m" });
    const payload = { provider: "groq", model: "m", temperature: 0.5 };
    expect(await chatService.create(payload)).toMatchObject({ id: "c1" });
    expect(JSON.parse(mock.history.post[0].data)).toEqual(payload);
  });
  it("gets, patches and deletes a conversation by id", async () => {
    mock.onGet("/ai/chat/conversations/c1").reply(200, { id: "c1", messages: [] });
    mock.onPatch("/ai/chat/conversations/c1").reply(200, { id: "c1", title: "New" });
    mock.onDelete("/ai/chat/conversations/c1").reply(204);
    expect((await chatService.get("c1")).messages).toEqual([]);
    expect((await chatService.patch("c1", { title: "New" })).title).toBe("New");
    await chatService.remove("c1");
    expect(mock.history.delete).toHaveLength(1);
    expect(JSON.parse(mock.history.patch[0].data)).toEqual({ title: "New" });
  });
});

describe("SSE parsing", () => {
  it("emits events in order across chunk boundaries", async () => {
    const events = [];
    const chunks = [SSE.slice(0, 40), SSE.slice(40, 120), SSE.slice(120)];
    await readSSE({ body: bodyFrom(chunks) }, (event) => events.push(event));
    expect(events.map((event) => event.event)).toEqual(["user_message", "delta", "delta", "done"]);
    expect(events[1].data.text).toBe("Hello");
    expect(events[3].data.message.content).toBe("Hello world");
  });
  it("joins multi-line data and parses a trailing block without a blank line", async () => {
    const events = [];
    const text = 'event: delta\ndata: {"text":\ndata: "x"}\n\nevent: done\ndata: {"message":{"id":"m"}}';
    await readSSE({ body: bodyFrom([text]) }, (event) => events.push(event));
    expect(events[0]).toEqual({ event: "delta", data: { text: "x" } });
    expect(events[1].event).toBe("done");
  });
  it("ignores keep-alive comments and malformed JSON blocks", async () => {
    const events = [];
    const text = ': keep-alive\n\nevent: delta\ndata: not-json\n\nevent: delta\ndata: {"text":"ok"}\n\n';
    await readSSE({ body: bodyFrom([text]) }, (event) => events.push(event));
    expect(events).toEqual([{ event: "delta", data: { text: "ok" } }]);
  });
});

describe("streamChat transport", () => {
  it("POSTs with cookie credentials and streams parsed events", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(SSE));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    await streamChat("/ai/chat/conversations/c1/messages", { content: "hi" }, { onEvent: (event) => events.push(event) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/ai/chat/conversations/c1/messages");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.headers.Accept).toBe("text/event-stream");
    expect(JSON.parse(init.body)).toEqual({ content: "hi" });
    expect(events.map((event) => event.event)).toEqual(["user_message", "delta", "delta", "done"]);
  });
  it("maps a non-ok JSON error to the axios error shape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse('{"detail":{"code":"model_not_chat_capable"}}', 409)));
    await expect(streamChat("/ai/chat/conversations/c1/messages", { content: "hi" }, {}))
      .rejects.toMatchObject({ response: { status: 409, data: { detail: { code: "model_not_chat_capable" } } } });
  });
  it("tolerates a non-JSON error body", async () => {
    const response = { ok: false, status: 502, body: bodyFrom([]), json: async () => { throw new Error("no json"); } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    await expect(streamChat("/x", {}, {})).rejects.toMatchObject({ response: { status: 502, data: null } });
  });
  it("refreshes the session once on 401 then retries the stream", async () => {
    refresh.onPost("/auth/refresh").reply(200, {});
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, body: bodyFrom([]), json: async () => ({}) })
      .mockResolvedValueOnce(sseResponse(SSE));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    await streamChat("/ai/chat/conversations/c1/regenerate", {}, { onEvent: (event) => events.push(event) });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refresh.history.post).toHaveLength(1);
    expect(events.at(-1).event).toBe("done");
  });
  it("signals session-expired when the refresh is rejected", async () => {
    refresh.onPost("/auth/refresh").reply(401);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, body: bodyFrom([]), json: async () => ({}) }));
    let expired = false;
    const handler = () => { expired = true; };
    window.addEventListener("session-expired", handler);
    await expect(streamChat("/x", {}, {})).rejects.toBeTruthy();
    window.removeEventListener("session-expired", handler);
    expect(expired).toBe(true);
  });
  it("propagates an abort without refreshing the session", async () => {
    const abortError = Object.assign(new Error("aborted"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortError));
    await expect(streamChat("/x", {}, { signal: new AbortController().signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(refresh.history.post).toHaveLength(0);
  });
});

describe("chat error copy and formatting", () => {
  it("maps backend codes to fixed Vietnamese without echoing upstream text", () => {
    const error = { response: { status: 400, data: { detail: { code: "provider_authentication_failed", message: "LEAKED-KEY" } } } };
    expect(getChatError(error)).toContain("Provider từ chối");
    expect(getChatError(error)).not.toContain("LEAKED-KEY");
  });
  it("falls back by status for unknown codes and network errors", () => {
    expect(getChatError({ response: { status: 401 } })).toContain("hết hạn");
    expect(getChatError({ response: { status: 409 } })).toContain("không còn phù hợp");
    expect(getChatError({ response: { status: 422 } })).toContain("chưa hợp lệ");
    expect(getChatError({})).toContain("Không kết nối");
  });
  it("maps SSE error events and unknown codes safely", () => {
    expect(chatErrorFromEvent({ code: "provider_rate_limited" })).toContain("giới hạn");
    expect(chatErrorFromEvent({ code: "toString" })).toContain("gặp lỗi");
    expect(chatErrorFromEvent({})).toContain("gặp lỗi");
  });
  it("formats tokens and latency truthfully", () => {
    expect(formatTokens(null)).toBe("—");
    expect(formatTokens(undefined)).toBe("—");
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(1000)).toBe("1.000");
    expect(formatLatency(null)).toBe("");
    expect(formatLatency(500)).toBe("500 ms");
    expect(formatLatency(1500)).toBe("1.5 s");
    expect(messageStatusLabels.stopped).toBe("Đã dừng");
  });
});