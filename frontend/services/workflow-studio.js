import api from "./api";

const path = "/ai/workflow-studio";

const STUDIO_ERRORS = {
  studio_graph_invalid:
    "Đồ thị chưa hợp lệ: node trùng tên, thiếu tham số bắt buộc, dùng loại node chưa hỗ trợ mà không có dữ liệu gốc, hoặc nối tới node không tồn tại.",
  n8n_api_not_configured:
    "Server chưa có N8N_API_KEY nên chưa lưu được vào n8n. Hãy đặt key trên server trước.",
  n8n_api_unauthorized:
    "n8n từ chối API key khi lưu workflow. Hãy kiểm tra key và quyền workflow trên n8n.",
  n8n_api_failed: "n8n không nhận workflow. Hãy mở n8n kiểm tra, hoặc thử lại sau.",
};

export function getWorkflowStudioError(error, fallback) {
  const code = error?.response?.data?.detail?.code;
  if (code && STUDIO_ERRORS[code]) return STUDIO_ERRORS[code];
  if (error?.response?.status === 401) {
    return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
  }
  return fallback;
}

export const workflowStudioService = {
  async getCatalog(signal) {
    const { data } = await api.get(`${path}/catalog`, { signal });
    return data;
  },
  async convert(graph, signal) {
    const { data } = await api.post(`${path}/convert`, graph, { signal });
    return data;
  },
  async parse(workflowJson, signal) {
    const { data } = await api.post(
      `${path}/parse`,
      { workflow_json: workflowJson },
      { signal },
    );
    return data;
  },
};
