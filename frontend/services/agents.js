import { api } from "./api";
import { streamChat } from "./chat";

const path = "/ai/agents";
const agentPath = (id) => `${path}/${encodeURIComponent(id)}`;
const executionPath = (id, executionId) => `${agentPath(id)}/executions/${encodeURIComponent(executionId)}`;

// Cookie-authenticated, owner-scoped API. Provider credentials never enter this service.
export const agentsService = {
  async list(signal) {
    const { data } = await api.get(path, { signal });
    return data.agents;
  },
  async tools(signal) {
    const { data } = await api.get(`${path}/tools`, { signal });
    return data.tools;
  },
  async create(payload, signal) {
    const { data } = await api.post(path, payload, { signal });
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(agentPath(id), { signal });
    return data;
  },
  async patch(id, payload, signal) {
    const { data } = await api.patch(agentPath(id), payload, { signal });
    return data;
  },
  async duplicate(id, signal) {
    const { data } = await api.post(`${agentPath(id)}/duplicate`, {}, { signal });
    return data;
  },
  async remove(id, signal) {
    await api.delete(agentPath(id), { signal });
  },
  async executions(id, signal) {
    const { data } = await api.get(`${agentPath(id)}/executions`, { signal });
    return data.executions;
  },
  async execution(id, executionId, signal) {
    const { data } = await api.get(executionPath(id, executionId), { signal });
    return data;
  },
  async removeExecution(id, executionId, signal) {
    await api.delete(executionPath(id, executionId), { signal });
  },
  run(id, payload, options) {
    return streamChat(`${agentPath(id)}/run`, payload, options);
  },
};
