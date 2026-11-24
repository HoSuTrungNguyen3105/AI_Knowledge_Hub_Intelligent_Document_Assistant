import { api } from "./api";

const path = "/ai/n8n-factory";

// Cookie-authenticated bridge to the user's self-hosted n8n (workflow 07).
// Runs are asynchronous: creating a run returns as soon as n8n has accepted
// it, the workflow executes in the background and calls MindFlow back with
// the final package. The page polls the run — no request stays open for
// the minutes a full run takes, so the default axios timeout is fine.
export const n8nFactoryService = {
  async createRun(payload, signal) {
    const { data } = await api.post(`${path}/runs`, payload, { signal });
    return data;
  },
  async listRuns(signal) {
    const { data } = await api.get(`${path}/runs`, { signal });
    return data;
  },
  async getRun(id, signal) {
    const { data } = await api.get(`${path}/runs/${id}`, { signal });
    return data;
  },
  async cancelRun(id, signal) {
    const { data } = await api.post(`${path}/runs/${id}/cancel`, {}, { signal });
    return data;
  },
};

export function getFactoryError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.code === "n8n_unreachable") {
    return "Không kết nối được n8n. Hãy chắc chắn n8n đang chạy (Docker: docker compose up -d trong thư mục n8n-ai-factory) rồi thử lại.";
  }
  if (detail && typeof detail === "object" && detail.code === "n8n_run_failed") {
    return "n8n từ chối lượt chạy. Hãy kiểm tra workflow 07 đã được import bản mới nhất và đang Publish/Active trong n8n (http://localhost:5678).";
  }
  if (detail && typeof detail === "object" && detail.code === "agent_not_found") {
    return "Một Agent đã chọn không còn tồn tại. Hãy tải lại trang và chọn lại.";
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}

// Human-readable explanation for a finished run's machine-readable error.
export function getRunErrorText(run) {
  if (!run?.error) return "";
  if (run.error === "n8n_unreachable") {
    return "Không kết nối được n8n khi bắt đầu lượt chạy này.";
  }
  if (run.error === "n8n_run_failed") {
    return "n8n từ chối lượt chạy này (workflow 07 chưa Publish/Active?).";
  }
  if (run.error === "run_timed_out") {
    return "Quá thời gian chờ mà n8n chưa báo kết quả về. Hãy mở Executions trong n8n để xem lượt chạy có kẹt không, và kiểm tra backend MindFlow có nhận được callback không (địa chỉ N8N_FACTORY_CALLBACK_BASE_URL, backend cần nghe ở 0.0.0.0:8000).";
  }
  return run.error;
}
