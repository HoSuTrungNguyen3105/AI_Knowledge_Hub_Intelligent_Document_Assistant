import { api } from "./api";

const base = "/ai/code-analyzer";
const projectPath = (id) => `${base}/projects/${encodeURIComponent(id)}`;

// Codebase Architecture Analyzer (PROJECT_SPEC.md): projects, the
// prebuilt diagram, per-file AI insights, ZIP upload and the demo seed.
export const codeAnalyzerService = {
  async list(signal) {
    const { data } = await api.get(`${base}/projects`, { signal });
    return data.projects;
  },
  async seedDemo() {
    const { data } = await api.post(`${base}/seed-demo`);
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(projectPath(id), { signal });
    return data;
  },
  async architecture(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/architecture`, { signal });
    return data.map;
  },
  async getFile(projectId, fileId, signal) {
    const { data } = await api.get(
      `${projectPath(projectId)}/files/${encodeURIComponent(fileId)}`,
      { signal },
    );
    return data;
  },
  async regenerate(id, provider, model) {
    const form = new FormData();
    if (provider && model) {
      form.append("provider", provider);
      form.append("model", model);
    }
    const { data } = await api.post(
      `${projectPath(id)}/report`,
      form,
      { timeout: 300000 },
    );
    return data;
  },
  async upload(file, provider, model) {
    const form = new FormData();
    form.append("file", file);
    if (provider && model) {
      form.append("provider", provider);
      form.append("model", model);
    }
    const { data } = await api.post(`${base}/upload`, form, { timeout: 300000 });
    return data;
  },
};

const ERROR_MESSAGES = {
  code_project_not_found: "Không tìm thấy dự án code này.",
  code_file_not_found: "Không tìm thấy file này trong dự án.",
  code_upload_too_large: "File ZIP lớn hơn giới hạn 25 MB.",
  code_upload_invalid: "File tải lên không phải file ZIP đọc được.",
  code_upload_empty:
    "Không tìm thấy file code nào phân tích được trong ZIP (đã lọc node_modules, file test, ảnh và file lock).",
  credentials_missing: "Provider đã chọn chưa lưu API key.",
  provider_disabled: "Provider đã chọn đang bị tắt.",
  model_not_synced: "Model đã chọn chưa được đồng bộ cho provider này.",
  seed_disabled: "Môi trường production không cho phép tạo dự án mẫu.",
};

export function getCodeError(error, fallback = "Đã xảy ra lỗi. Hãy thử lại.") {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "object" && detail !== null ? detail.code : null;
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  if (typeof detail === "object" && detail !== null && detail.message) {
    return detail.message;
  }
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}
