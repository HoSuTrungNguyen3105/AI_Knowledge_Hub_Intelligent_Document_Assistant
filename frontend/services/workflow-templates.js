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
  async listTemplates(params, signal) {
    const { data } = await api.get(`${path}/templates`, { params, signal });
    return data;
  },
  async getStats(signal) {
    const { data } = await api.get(`${path}/templates/stats`, { signal });
    return data;
  },
  async getTemplate(id, signal) {
    const { data } = await api.get(`${path}/templates/${id}`, { signal });
    return data;
  },
  async reviewTemplate(id, reviewStatus, signal) {
    const { data } = await api.patch(
      `${path}/templates/${id}/review`,
      { review_status: reviewStatus },
      { signal },
    );
    return data;
  },
  async listMine(signal) {
    const { data } = await api.get(`${path}/mine`, { signal });
    return data;
  },
  async syncCandidates(signal) {
    const { data } = await api.get(`${path}/sync-candidates`, { signal });
    return data;
  },
  async install(templateIds, signal) {
    const { data } = await api.post(
      `${path}/install`,
      { template_ids: templateIds },
      { signal },
    );
    return data;
  },
  async updateMine(id, signal) {
    const { data } = await api.post(`${path}/mine/${id}/update`, {}, { signal });
    return data;
  },
  async removeMine(id, signal) {
    await api.delete(`${path}/mine/${id}`, { signal });
  },
  async listVersions(id, signal) {
    const { data } = await api.get(`${path}/templates/${id}/versions`, { signal });
    return data;
  },
  async getVersion(id, version, signal) {
    const { data } = await api.get(`${path}/templates/${id}/versions/${version}`, { signal });
    return data;
  },
  async diffVersions(id, fromVersion, toVersion, signal) {
    const { data } = await api.get(`${path}/templates/${id}/diff`, {
      params: { from_version: fromVersion, to_version: toVersion },
      signal,
    });
    return data;
  },
  async restoreVersion(id, version, signal) {
    const { data } = await api.post(
      `${path}/templates/${id}/versions/${version}/restore`,
      {},
      { signal },
    );
    return data;
  },
  async contribute(payload, signal) {
    const { data } = await api.post(`${path}/templates/contribute`, payload, { signal });
    return data;
  },
  async askAssistant(id, payload, signal) {
    const { data } = await api.post(`${path}/templates/${id}/assistant`, payload, { signal });
    return data;
  },
  async applyAssistant(id, payload, signal) {
    const { data } = await api.post(`${path}/templates/${id}/assistant/apply`, payload, {
      signal,
    });
    return data;
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
  if (code === "template_not_approved") {
    return "Template chưa được duyệt nên chưa cài được. Hãy duyệt template trước.";
  }
  if (code === "user_workflow_not_found") {
    return "Không tìm thấy workflow đã cài này. Hãy tải lại danh sách.";
  }
  if (code === "n8n_api_not_configured") {
    return "Server chưa có N8N_API_KEY nên chưa cài được template vào n8n. Hãy đặt key trên server trước.";
  }
  if (code === "template_version_not_found") {
    return "Không tìm thấy phiên bản này của template.";
  }
  if (code === "template_contribute_invalid") {
    return "JSON gửi lên không phải workflow n8n hợp lệ (cần có nodes là danh sách, mỗi node có name và type).";
  }
  if (code === "template_assistant_unavailable") {
    return "Chưa có provider AI nào được cấu hình và bật kèm model chat đã đồng bộ. Hãy cấu hình ở trang Providers trước.";
  }
  if (code === "generation_failed") {
    return "AI không trả về kết quả. Hãy thử lại, hoặc đổi provider/model khác.";
  }
  if (code === "provider_request_rejected") {
    return "Provider AI đã từ chối yêu cầu (thường do key hết quyền gọi model này hoặc model không còn khả dụng). Hãy kiểm tra ở trang Providers: bấm Kiểm tra kết nối, hoặc chọn model khác.";
  }
  if (code === "provider_unauthorized" || code === "invalid_api_key") {
    return "API key của provider không hợp lệ. Hãy cập nhật key ở trang Providers.";
  }
  if (code === "n8n_workflow_not_found") {
    return "Workflow tương ứng không còn trong n8n (có thể đã bị xóa tay). Hãy gỡ khỏi tài khoản rồi cài lại.";
  }
  if (typeof detail === "object" && detail?.message) return detail.message;
  return fallback;
}
