import { api } from "./api";

const path = "/ai/workflow-templates";

export const workflowTemplatesService = {
  async listSources(signal) {
    const { data } = await api.get(`${path}/sources`, { signal });
    return data;
  },
  async ensureDefaultSource(signal) {
    const { data } = await api.post(`${path}/sources/default`, {}, { signal });
    return data;
  },
  async createSource(payload, signal) {
    const { data } = await api.post(`${path}/sources`, payload, { signal });
    return data;
  },
  async importSource(id, signal) {
    const { data } = await api.post(`${path}/sources/${id}/import`, {}, { signal });
    return data;
  },
  async listImports(signal) {
    const { data } = await api.get(`${path}/imports`, { signal });
    return data;
  },
  async countTemplates(params, signal) {
    const { data } = await api.get(`${path}/templates`, {
      params: { ...params, limit: 1 },
      signal,
    });
    return data.total;
  },
};

export function getWorkflowTemplatesError(error, fallback) {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "object" && detail ? detail.code : "";
  if (code === "github_unreachable") {
    return "Không kết nối được GitHub (hoặc bị giới hạn lượt gọi API). Hãy thử lại sau ít phút.";
  }
  if (code === "template_source_exists") {
    return "Nguồn này đã được đăng ký rồi.";
  }
  if (code === "template_source_invalid") {
    return "URL nguồn chưa đúng định dạng kho GitHub (https://github.com/owner/repo).";
  }
  if (code === "template_source_not_found") {
    return "Không tìm thấy nguồn template. Hãy tải lại danh sách.";
  }
  if (typeof detail === "object" && detail?.message) return detail.message;
  return fallback;
}
