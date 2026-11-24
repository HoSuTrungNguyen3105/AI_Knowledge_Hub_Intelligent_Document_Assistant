import { api } from "./api";

const path = "/ai/n8n-factory";

// Cookie-authenticated bridge to the user's self-hosted n8n (workflow 07).
// A full 7-agent run takes minutes, so the shared 20s axios timeout is
// overridden per request; the backend timeout setting bounds the wait.
export const n8nFactoryService = {
  async run(payload, signal) {
    const { data } = await api.post(`${path}/run`, payload, { signal, timeout: 960000 });
    return data;
  },
};

export function getFactoryError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.code === "n8n_unreachable") {
    return "Không kết nối được n8n. Hãy chắc chắn n8n đang chạy (Docker: docker compose up -d trong thư mục n8n-ai-factory) rồi thử lại.";
  }
  if (detail && typeof detail === "object" && detail.code === "n8n_run_failed") {
    return "n8n trả lỗi khi chạy workflow. Mở tab Executions trong n8n (http://localhost:5678) để xem chi tiết.";
  }
  if (detail && typeof detail === "object" && detail.code === "agent_not_found") {
    return "Một Agent đã chọn không còn tồn tại. Hãy tải lại trang và chọn lại.";
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}
