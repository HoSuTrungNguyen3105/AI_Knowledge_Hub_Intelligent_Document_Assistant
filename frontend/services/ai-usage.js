import { api } from "./api";

const path = "/ai/ai-usage";

export const aiUsageService = {
  async overview(params) {
    const { data } = await api.get(`${path}/overview`, { params });
    return data;
  },
  async timeseries(params) {
    const { data } = await api.get(`${path}/timeseries`, { params });
    return data;
  },
  async providers(params) {
    const { data } = await api.get(`${path}/providers`, { params });
    return data;
  },
  async models(params) {
    const { data } = await api.get(`${path}/models`, { params });
    return data;
  },
  async agents(params) {
    const { data } = await api.get(`${path}/agents`, { params });
    return data;
  },
  async workflows() {
    const { data } = await api.get(`${path}/workflows`);
    return data;
  },
  async history(params) {
    const { data } = await api.get(`${path}/history`, { params });
    return data;
  },
  async exportCsv(params) {
    const { data } = await api.get(`${path}/export`, {
      params,
      responseType: "blob",
    });
    return data;
  },
  async pricing() {
    const { data } = await api.get(`${path}/pricing`);
    return data;
  },
  async updatePricing(payload) {
    const { data } = await api.put(`${path}/pricing`, payload);
    return data;
  },
  async budgets() {
    const { data } = await api.get(`${path}/budgets`);
    return data;
  },
  async upsertBudget(payload) {
    const { data } = await api.put(`${path}/budgets`, payload);
    return data;
  },
};

export function getAiUsageError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.message) {
    return detail.message;
  }
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}
