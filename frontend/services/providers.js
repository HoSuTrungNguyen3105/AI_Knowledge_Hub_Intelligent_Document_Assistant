import { api } from "./api";

const providerPath = (id) => `/ai/providers/${encodeURIComponent(id)}`;

export const providerService = {
  async list(signal) {
    const { data } = await api.get("/ai/providers", { signal });
    return data;
  },
  async models(id, signal) {
    const { data } = await api.get(`${providerPath(id)}/models`, { signal });
    return data;
  },
  async update(id, values) {
    const { data } = await api.patch(providerPath(id), values);
    return data;
  },
  async checkModel(id, modelId) {
    const { data } = await api.post(
      `${providerPath(id)}/models/${modelId}/check`, {}, { timeout: 130000 }
    );
    return data;
  },
  async test(id) {
    const { data } = await api.post(`${providerPath(id)}/test`, {}, { timeout: 45000 });
    return data;
  },
  async rateLimits(signal) {
    const { data } = await api.get("/ai/providers/rate-limits", { signal });
    return data;
  },
  async disconnect(id) {
    await api.delete(providerPath(id));
  },
};
