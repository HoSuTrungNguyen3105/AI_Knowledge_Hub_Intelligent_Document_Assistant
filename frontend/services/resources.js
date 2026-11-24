import { api } from "./api";

const base = "/ai/resources";

// Workforce resources (mindflow-workforce-feature.md): one list holding
// people and AI as project resources. The backend enforces that the
// profile block matches `type`; no provider key is ever stored here.
export const resourcesService = {
  async list(type, signal) {
    const { data } = await api.get(base, { params: type ? { type } : {}, signal });
    return data.resources || [];
  },
  async create(payload, signal) {
    const { data } = await api.post(base, payload, { signal });
    return data;
  },
  async patch(id, payload, signal) {
    const { data } = await api.patch(`${base}/${id}`, payload, { signal });
    return data;
  },
  async remove(id, signal) {
    await api.delete(`${base}/${id}`, { signal });
  },
};

const MESSAGES = {
  resource_not_found: "Nguồn lực không tồn tại hoặc không thuộc về bạn.",
  agent_not_found: "Agent được liên kết không tồn tại hoặc không thuộc về bạn.",
  invalid_provider_configuration: "Dữ liệu chưa hợp lệ — kiểm tra trạng thái sẵn sàng và khối hồ sơ khớp loại nguồn lực.",
};

export function getResourceError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && MESSAGES[detail.code]) return MESSAGES[detail.code];
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}
