import { api, refreshClient } from "./api";

const conversationsPath = "/ai/chat/conversations";
const apiBase = "/api/v1";

// CRUD uses the shared axios client (cookie transport + 401 refresh interceptor).
export const chatService = {
  async list(signal) {
    const { data } = await api.get(conversationsPath, { signal });
    return data.conversations;
  },
  async create(payload) {
    const { data } = await api.post(conversationsPath, payload);
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(`${conversationsPath}/${id}`, { signal });
    return data;
  },
  async patch(id, values) {
    const { data } = await api.patch(`${conversationsPath}/${id}`, values);
    return data;
  },
  async remove(id) {
    await api.delete(`${conversationsPath}/${id}`);
  },
  sendMessage(id, content, options) {
    return streamChat(`${conversationsPath}/${id}/messages`, { content }, options);
  },
  regenerate(id, options) {
    return streamChat(`${conversationsPath}/${id}/regenerate`, {}, options);
  },
};

function parseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

// Consume a text/event-stream body, emitting one parsed object per SSE block.
export async function readSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) {
    const parsed = parseBlock(buffer);
    if (parsed) onEvent(parsed);
  }
}

async function openStream(url, body, signal) {
  const init = {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  };
  let response = await fetch(url, init);
  if (response.status === 401) {
    // Mirror the axios interceptor: refresh the cookie session once, then retry.
    await refreshClient.post("/auth/refresh");
    response = await fetch(url, init);
  }
  return response;
}

// Generation is streamed with fetch (axios cannot stream in the browser). Errors
// raised before the stream begins keep the axios error shape so getChatError can
// map the backend code; aborts propagate for the caller to treat as a stop.
export async function streamChat(path, body, { signal, onEvent } = {}) {
  let response;
  try {
    response = await openStream(`${apiBase}${path}`, body, signal);
  } catch (error) {
    const status = error?.response?.status;
    if ([401, 403].includes(status) && typeof window !== "undefined") {
      window.dispatchEvent(new Event("session-expired"));
    }
    throw error;
  }
  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    throw { response: { status: response.status, data } };
  }
  await readSSE(response, onEvent || (() => {}));
}