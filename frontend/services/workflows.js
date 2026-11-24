import { api, refreshClient } from "./api";
import { readSSE } from "./chat";

const teamsPath = "/ai/agent-teams";
const workflowsPath = "/ai/agent-workflows";
const teamPath = (id) => `${teamsPath}/${encodeURIComponent(id)}`;
const workflowPath = (id) => `${workflowsPath}/${encodeURIComponent(id)}`;

// Cookie-authenticated, owner-scoped API. Provider credentials never enter this service.
export const teamsService = {
  async list(signal) {
    const { data } = await api.get(teamsPath, { signal });
    return data.teams;
  },
  async create(payload, signal) {
    const { data } = await api.post(teamsPath, payload, { signal });
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(teamPath(id), { signal });
    return data;
  },
  async patch(id, payload, signal) {
    const { data } = await api.patch(teamPath(id), payload, { signal });
    return data;
  },
  async remove(id, signal) {
    await api.delete(teamPath(id), { signal });
  },
};

export const workflowsService = {
  async list(signal) {
    const { data } = await api.get(workflowsPath, { signal });
    return data.workflows;
  },
  async create(payload, signal) {
    const { data } = await api.post(workflowsPath, payload, { signal });
    return data;
  },
  async plan(payload, signal) {
    // One Leader pass that analyzes + decomposes + sizes the team;
    // generous timeout on purpose, like project analysis.
    const { data } = await api.post(`${workflowsPath}/plan`, payload, {
      signal,
      timeout: 240000,
    });
    return data;
  },
  async applyPlan(payload, signal) {
    const { data } = await api.post(`${workflowsPath}/plan/apply`, payload, { signal });
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(workflowPath(id), { signal });
    return data;
  },
  async remove(id, signal) {
    await api.delete(workflowPath(id), { signal });
  },
  async start(id, signal) {
    const { data } = await api.post(`${workflowPath(id)}/start`, {}, { signal });
    return data;
  },
  async pause(id, signal) {
    const { data } = await api.post(`${workflowPath(id)}/pause`, {}, { signal });
    return data;
  },
  async resume(id, signal) {
    const { data } = await api.post(`${workflowPath(id)}/resume`, {}, { signal });
    return data;
  },
  async cancel(id, signal) {
    const { data } = await api.post(`${workflowPath(id)}/cancel`, {}, { signal });
    return data;
  },
  async messages(id, signal) {
    const { data } = await api.get(`${workflowPath(id)}/messages`, { signal });
    return data.messages;
  },
  async tasks(id, signal) {
    const { data } = await api.get(`${workflowPath(id)}/tasks`, { signal });
    return data.tasks;
  },
  async events(id, signal) {
    const { data } = await api.get(`${workflowPath(id)}/events`, { signal });
    return data.events;
  },
  async files(id, signal) {
    const { data } = await api.get(`${workflowPath(id)}/files`, { signal });
    return data;
  },
};

export function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// Download the website ZIP artifact (owner-scoped; the backend rebuilds the
// ZIP from the stored validated files). Mirrors streamWorkflow's 401 flow.
export async function downloadWorkflowZip(id) {
  const url = `/api/v1${workflowPath(id)}/download.zip`;
  const init = { method: "GET", credentials: "include" };
  let response = await fetch(url, init);
  if (response.status === 401) {
    await refreshClient.post("/auth/refresh");
    response = await fetch(url, init);
  }
  if (!response.ok) throw { response: { status: response.status, data: null } };
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : "website.zip";
  triggerBlobDownload(blob, filename);
  return filename;
}

// GET SSE stream of workflow events (observation only; disconnecting does not
// cancel the workflow — cancellation is the dedicated POST /cancel action).
export async function streamWorkflow(id, { signal, onEvent } = {}) {
  const url = `/api/v1${workflowPath(id)}/stream`;
  const init = { method: "GET", credentials: "include", headers: { Accept: "text/event-stream" }, signal };
  let response = await fetch(url, init);
  if (response.status === 401) {
    await refreshClient.post("/auth/refresh");
    response = await fetch(url, init);
  }
  if (!response.ok) throw { response: { status: response.status, data: null } };
  await readSSE(response, onEvent || (() => {}));
}
