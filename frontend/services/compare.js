import { api } from "./api";
import { streamChat } from "./chat";

const comparisonsPath = "/ai/compare/comparisons";

// CRUD uses the shared axios client (cookie transport + 401 refresh interceptor).
// Execute/synthesize reuse the chat SSE transport: one prompt fans out to several
// models in parallel, each run streaming independently. No key handling lives here.
export const compareService = {
  async list(signal) {
    const { data } = await api.get(comparisonsPath, { signal });
    return data.comparisons;
  },
  async create(payload) {
    const { data } = await api.post(comparisonsPath, payload);
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(`${comparisonsPath}/${id}`, { signal });
    return data;
  },
  async remove(id) {
    await api.delete(`${comparisonsPath}/${id}`);
  },
  execute(id, options) {
    return streamChat(`${comparisonsPath}/${id}/execute`, {}, options);
  },
  synthesize(id, payload, options) {
    return streamChat(`${comparisonsPath}/${id}/synthesize`, payload, options);
  },
};