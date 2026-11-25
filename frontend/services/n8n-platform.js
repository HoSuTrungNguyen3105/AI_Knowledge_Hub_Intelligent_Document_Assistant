import { api } from "./api";

const path = "/ai/n8n-platform";

// Management bridge to the user's self-hosted n8n (n8n Platform, phase 1).
// The backend talks to the n8n REST API with a server-side key; the browser
// only ever sees status and workflow metadata — never the key.
export const n8nPlatformService = {
  async getStatus(signal) {
    const { data } = await api.get(`${path}/status`, { signal });
    return data;
  },
  async listWorkflows(signal) {
    const { data } = await api.get(`${path}/workflows`, { signal });
    return data;
  },
  async setActive(id, active, signal) {
    const action = active ? "activate" : "deactivate";
    const { data } = await api.post(`${path}/workflows/${id}/${action}`, {}, { signal });
    return data;
  },
  async getWorkflow(id, signal) {
    const { data } = await api.get(`${path}/workflows/${id}`, { signal });
    return data;
  },
  async updateParameters(id, updates, signal) {
    const { data } = await api.post(`${path}/workflows/${id}/parameters`, { updates }, { signal });
    return data;
  },
  async createWorkflow(payload, signal) {
    const { data } = await api.post(`${path}/workflows`, payload, { signal });
    return data;
  },
};

// Human-readable text for the machine-readable status/sync error codes.
export function getN8nStatusText(code) {
  if (!code) return "";
  if (code === "n8n_api_not_configured") {
    return "Server chưa có N8N_API_KEY. Hãy tạo API key trong n8n (Settings → n8n API → Create an API key), đặt vào biến môi trường của backend rồi khởi động lại backend.";
  }
  if (code === "n8n_unreachable") {
    return "Không kết nối được n8n. Hãy chắc chắn n8n đang chạy (Docker: docker compose up -d trong thư mục n8n-ai-factory) và địa chỉ N8N_API_BASE_URL/N8N_WEBHOOK_BASE_URL trỏ đúng (qua Tailscale Funnel nếu backend ở trên Render).";
  }
  if (code === "n8n_api_unauthorized") {
    return "n8n từ chối API key. Hãy kiểm tra lại N8N_API_KEY trên server (key tạo trong n8n → Settings → n8n API).";
  }
  if (code === "n8n_api_failed") {
    return "n8n API trả lỗi. Hãy mở n8n để kiểm tra trạng thái của instance.";
  }
  if (code === "n8n_parameter_not_found") {
    return "Node hoặc tham số không còn tồn tại trong workflow (có thể workflow vừa được sửa trong n8n). Hãy đóng panel, bấm Làm mới rồi mở lại Cấu hình.";
  }
  if (code === "n8n_workflow_not_found") {
    return "Workflow không còn tồn tại trong n8n. Hãy bấm Làm mới để đồng bộ lại danh sách.";
  }
  if (code === "n8n_workflow_invalid") {
    return "Định nghĩa workflow chưa hợp lệ: cần có tên và ít nhất một node có đủ name + type (và đúng định dạng mà n8n chấp nhận). Hãy kiểm tra lại JSON.";
  }
  return code;
}

export function getN8nPlatformError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.code) {
    return getN8nStatusText(detail.code) || detail.message || fallback;
  }
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}
