import { api } from "./api";

const base = "/ai/evaluations";

const ERROR_MESSAGES = {
  eval_dataset_not_found: "Không tìm thấy dataset.",
  eval_run_not_found: "Không tìm thấy lượt đánh giá.",
  eval_prompt_not_found: "Không tìm thấy prompt.",
  eval_no_cases: "Dataset chưa có test case nào.",
  eval_no_targets: "Hãy chọn ít nhất một model để đánh giá.",
  eval_run_too_large: "Lượt chạy quá lớn (số case × số model). Hãy tách dataset hoặc giảm số model.",
  eval_import_invalid: "Nội dung import không hợp lệ. Kiểm tra lại định dạng JSON/CSV.",
  eval_prompt_template_invalid: "Template prompt phải chứa {input}.",
  agent_not_found: "Không tìm thấy Agent.",
  credentials_missing: "Provider chưa được cấu hình key.",
  provider_disabled: "Provider đang bị tắt.",
  model_not_synced: "Model chưa được đồng bộ cho provider này.",
  model_not_chat_capable: "Model này không hỗ trợ chat.",
};

export function evalErrorByCode(code) {
  return ERROR_MESSAGES[code] || "Đã xảy ra lỗi. Vui lòng thử lại.";
}

export function getEvalError(error) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.code) {
    return evalErrorByCode(detail.code);
  }
  return "Đã xảy ra lỗi. Vui lòng thử lại.";
}

export const evaluationsService = {
  async overview(signal) {
    const { data } = await api.get(`${base}/overview`, { signal });
    return data;
  },
  async listDatasets(signal) {
    const { data } = await api.get(`${base}/datasets`, { signal });
    return data.datasets;
  },
  async createDataset(payload) {
    const { data } = await api.post(`${base}/datasets`, payload);
    return data;
  },
  async getDataset(id, signal) {
    const { data } = await api.get(`${base}/datasets/${id}`, { signal });
    return data;
  },
  async updateDataset(id, payload) {
    const { data } = await api.patch(`${base}/datasets/${id}`, payload);
    return data;
  },
  async removeDataset(id) {
    await api.delete(`${base}/datasets/${id}`);
  },
  async importDataset(payload) {
    const { data } = await api.post(`${base}/datasets/import`, payload);
    return data;
  },
  async exportDataset(id) {
    const { data } = await api.get(`${base}/datasets/${id}/export`);
    return data;
  },
  async listPrompts(signal) {
    const { data } = await api.get(`${base}/prompts`, { signal });
    return data.prompts;
  },
  async createPrompt(payload) {
    const { data } = await api.post(`${base}/prompts`, payload);
    return data;
  },
  async updatePrompt(id, payload) {
    const { data } = await api.patch(`${base}/prompts/${id}`, payload);
    return data;
  },
  async removePrompt(id) {
    await api.delete(`${base}/prompts/${id}`);
  },
  async listRuns(params, signal) {
    const { data } = await api.get(`${base}/runs`, { params, signal });
    return data.runs;
  },
  async createRun(payload) {
    const { data } = await api.post(`${base}/runs`, payload, { timeout: 900000 });
    return data;
  },
  async getRun(id, signal) {
    const { data } = await api.get(`${base}/runs/${id}`, { signal });
    return data;
  },
  async cancelRun(id) {
    const { data } = await api.post(`${base}/runs/${id}/cancel`, {});
    return data;
  },
  async setBaseline(id) {
    const { data } = await api.post(`${base}/runs/${id}/baseline`, {});
    return data;
  },
  async compareRuns(baselineId, currentId) {
    const { data } = await api.get(`${base}/runs/compare`, {
      params: { baseline_id: baselineId, current_id: currentId },
    });
    return data;
  },
};
