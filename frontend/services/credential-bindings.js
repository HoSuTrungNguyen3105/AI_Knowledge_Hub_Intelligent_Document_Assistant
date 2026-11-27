import { api } from "./api";

const path = "/ai/credential-bindings";

export const credentialBindingsService = {
  async list(signal) {
    const { data } = await api.get(path, { signal });
    return data;
  },
  async set(credType, credentialId, signal) {
    const { data } = await api.put(
      path,
      { cred_type: credType, n8n_credential_id: credentialId },
      { signal },
    );
    return data;
  },
  async remove(credType, signal) {
    await api.delete(`${path}/${encodeURIComponent(credType)}`, { signal });
  },
  async applyInstalled(signal) {
    const { data } = await api.post(`${path}/apply-installed`, {}, { signal });
    return data;
  },
};

const ERROR_TEXT = {
  credential_binding_invalid:
    "Credential đó không còn trong n8n hoặc khác loại với mục đang gán. Hãy tải lại danh sách.",
  credential_binding_not_found: "Mục gán này đã được gỡ rồi. Hãy tải lại danh sách.",
  n8n_api_not_configured:
    "Server chưa có N8N_API_KEY nên chưa đọc được credential trong n8n. Hãy đặt key trên server trước.",
  n8n_unreachable: "Không kết nối được n8n. Hãy kiểm tra n8n đang chạy và đường Funnel.",
  n8n_api_unauthorized: "N8N_API_KEY bị n8n từ chối. Hãy kiểm tra lại key trên server.",
  n8n_api_failed: "n8n trả lỗi khi xử lý yêu cầu. Hãy thử lại sau ít phút.",
};

export function getCredentialBindingsError(error, fallback) {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "object" && detail ? detail.code : "";
  if (code && ERROR_TEXT[code]) return ERROR_TEXT[code];
  if (typeof detail === "object" && detail?.message) return detail.message;
  return fallback;
}
