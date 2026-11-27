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
  async createWorkflow(payload, signal) {
    const { data } = await api.post(`${path}/workflows`, payload, { signal });
    return data;
  },
  // Workflow Management (rebuild): validate-only preview, full-JSON
  // update of an existing workflow, delete, live export, dashboard
  // statistics and the n8n execution history.
  async validateWorkflow(workflow, signal) {
    const { data } = await api.post(`${path}/workflows/validate`, { workflow }, { signal });
    return data;
  },
  async updateWorkflow(id, payload, signal) {
    const { data } = await api.put(`${path}/workflows/${id}`, payload, { signal });
    return data;
  },
  async deleteWorkflow(id, signal) {
    await api.delete(`${path}/workflows/${id}`, { signal });
  },
  async exportWorkflow(id, signal) {
    const { data } = await api.get(`${path}/workflows/${id}/export`, { signal });
    return data;
  },
  // Duplicate + definition snapshots (backup/restore): snapshots are
  // kept by the backend on every sync/create/update; restoring writes
  // one back onto the same workflow in n8n.
  async duplicateWorkflow(id, signal) {
    const { data } = await api.post(`${path}/workflows/${id}/duplicate`, {}, { signal });
    return data;
  },
  async listSnapshots(id, signal) {
    const { data } = await api.get(`${path}/workflows/${id}/snapshots`, { signal });
    return data;
  },
  async restoreSnapshot(id, snapshotId, signal) {
    const { data } = await api.post(
      `${path}/workflows/${id}/snapshots/${snapshotId}/restore`,
      {},
      { signal },
    );
    return data;
  },
  async getStats(signal) {
    const { data } = await api.get(`${path}/stats`, { signal });
    return data;
  },
  async listExecutions(params = {}, signal) {
    const query = {};
    if (params.workflowId) query.workflow_id = params.workflowId;
    if (params.status) query.status_filter = params.status;
    if (params.limit) query.limit = params.limit;
    const { data } = await api.get(`${path}/executions`, { params: query, signal });
    return data;
  },
  async getExecution(id, signal) {
    const { data } = await api.get(`${path}/executions/${id}`, { signal });
    return data;
  },
  async startRun(payload, signal) {
    const { data } = await api.post(`${path}/runs`, payload, { signal });
    return data;
  },
  async listRuns(signal) {
    const { data } = await api.get(`${path}/runs`, { signal });
    return data;
  },
  async stopRun(id, signal) {
    const { data } = await api.post(`${path}/runs/${id}/stop`, {}, { signal });
    return data;
  },
  async retryRun(id, signal) {
    const { data } = await api.post(`${path}/runs/${id}/retry`, {}, { signal });
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
  if (code === "execution_not_found") {
    return "Không tìm thấy execution này trong n8n (có thể đã bị n8n dọn theo chính sách lưu trữ).";
  }
  if (code === "n8n_workflow_not_found") {
    return "Workflow không còn tồn tại trong n8n. Hãy bấm Làm mới để đồng bộ lại danh sách.";
  }
  if (code === "n8n_snapshot_not_found") {
    return "Bản lưu này không còn tồn tại. Hãy mở lại danh sách bản lưu rồi thử lại.";
  }
  if (code === "n8n_workflow_inactive") {
    return "Workflow đang tắt trong n8n. Hãy Bật (Publish) workflow trước khi chạy.";
  }
  if (code === "n8n_workflow_no_webhook") {
    return "Workflow này không có Webhook trigger nên chưa chạy được từ MindFlow. Hãy mở n8n và thêm Webhook trigger.";
  }
  if (code === "n8n_run_not_found") {
    return "Không tìm thấy lượt chạy này. Hãy tải lại danh sách.";
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

// Human-readable text for the validate endpoint's problem codes.
export function getN8nValidateErrorText(code) {
  const texts = {
    workflow_not_an_object: "JSON phải là một object workflow của n8n.",
    workflow_name_missing: "Thiếu tên workflow (trường name).",
    workflow_nodes_missing: "Thiếu danh sách node (trường nodes) hoặc danh sách rỗng.",
    workflow_node_missing_name: "Có node chưa đặt tên (thiếu trường name).",
    workflow_node_missing_type: "Có node thiếu loại (trường type).",
    workflow_connections_invalid: "Trường connections phải là một object.",
  };
  return texts[code] || code;
}
