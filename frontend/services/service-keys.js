import { api } from "./api";

const path = "/ai/service-keys";

// Service key vault: the browser only ever sends values (on create/edit)
// and reads back which fields have a value — stored values are never
// returned by the API, so nothing here can leak a key into the page.
export const serviceKeysService = {
  async listPresets(signal) {
    const { data } = await api.get(`${path}/presets`, { signal });
    return data.items ?? [];
  },
  async list(signal) {
    const { data } = await api.get(path, { signal });
    return data.items ?? [];
  },
  async create(payload, signal) {
    const { data } = await api.post(path, payload, { signal });
    return data;
  },
  async update(id, payload, signal) {
    const { data } = await api.patch(`${path}/${id}`, payload, { signal });
    return data;
  },
  async remove(id, signal) {
    await api.delete(`${path}/${id}`, { signal });
  },
  async push(id, signal) {
    const { data } = await api.post(`${path}/${id}/push`, {}, { signal });
    return data;
  },
};

const ERROR_TEXT = {
  service_key_invalid:
    "Dữ liệu chưa hợp lệ: thiếu trường bắt buộc, hoặc giá trị không lưu được (chỉ gồm ký tự ASCII không khoảng trắng, dài 8–4096 ký tự).",
  service_key_not_found: "Mục key này không còn tồn tại.",
  encryption_unavailable:
    "Server chưa cấu hình khoá mã hoá credential — chưa lưu được key.",
  n8n_api_not_configured:
    "Server chưa cấu hình N8N_API_KEY nên chưa đẩy được sang n8n.",
  n8n_unreachable:
    "Không kết nối được n8n. Hãy bật Docker + n8n ở máy và kiểm tra đường Funnel.",
  n8n_api_unauthorized:
    "n8n từ chối API key của server. Kiểm tra lại N8N_API_KEY trên server.",
  n8n_api_failed: "n8n trả lỗi khi nhận credential. Mở n8n để xem chi tiết.",
};

export function getServiceKeyError(error) {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "object" && detail !== null ? detail.code : null;
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  if (error?.response) return "Máy chủ trả lỗi. Hãy thử lại sau ít phút.";
  return "Không kết nối được máy chủ. Hãy kiểm tra kết nối và backend.";
}
