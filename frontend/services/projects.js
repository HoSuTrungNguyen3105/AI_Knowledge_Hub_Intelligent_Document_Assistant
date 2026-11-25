import { api } from "./api";

const base = "/ai/projects";
const projectPath = (id) => `${base}/${encodeURIComponent(id)}`;

// Workforce projects: CRUD + AI analyses + team recommendations
// (allocations). Cookie-authenticated and owner-scoped, like the rest.
export const projectsService = {
  async list(signal) {
    const { data } = await api.get(base, { signal });
    return data.projects;
  },
  async create(payload) {
    const { data } = await api.post(base, payload);
    return data;
  },
  async importFile(file, { name, techStack, provider, model }) {
    // Multipart upload: the backend reads the brief, creates the
    // project and runs analysis + recommendation in one request.
    const form = new FormData();
    form.append("file", file);
    form.append("name", name || "");
    form.append("tech_stack", techStack || "");
    form.append("provider", provider);
    form.append("model", model);
    const { data } = await api.post(`${base}/import`, form, { timeout: 240000 });
    return data;
  },
  async patch(id, payload) {
    const { data } = await api.patch(projectPath(id), payload);
    return data;
  },
  async remove(id) {
    await api.delete(projectPath(id));
  },
  async analyses(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/analyses`, { signal });
    return data.analyses;
  },
  async analyze(id, payload) {
    // One LLM pass over the requirements; generous timeout on purpose.
    const { data } = await api.post(`${projectPath(id)}/analyze`, payload, {
      timeout: 180000,
    });
    return data;
  },
  async recommend(id, analysisId) {
    const { data } = await api.post(`${projectPath(id)}/recommend`, {
      analysis_id: analysisId || undefined,
    });
    return data;
  },
  async allocations(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/allocations`, { signal });
    return data.allocations;
  },
  async reassign(id, allocationId, items) {
    const { data } = await api.patch(
      `${projectPath(id)}/allocations/${encodeURIComponent(allocationId)}`,
      { items },
    );
    return data;
  },
  async decide(id, allocationId, decision) {
    const { data } = await api.post(
      `${projectPath(id)}/allocations/${encodeURIComponent(allocationId)}/decide`,
      { decision },
    );
    return data;
  },
  // --- Discussion & decisions (Project_Discussion.md) ---
  async discussion(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/discussion`, { signal });
    return data.messages;
  },
  async postDiscussion(id, payload) {
    // Agent replies run synchronously server-side; allow minutes.
    const { data } = await api.post(`${projectPath(id)}/discussion`, payload, {
      timeout: 240000,
    });
    return data.messages;
  },
  async retryDiscussion(id, messageId) {
    const { data } = await api.post(
      `${projectPath(id)}/discussion/${encodeURIComponent(messageId)}/retry`,
      null,
      { timeout: 240000 },
    );
    return data.messages;
  },
  async convertTask(id, messageId, payload) {
    const { data } = await api.post(
      `${projectPath(id)}/discussion/${encodeURIComponent(messageId)}/convert-task`,
      payload,
    );
    return data;
  },
  async decisions(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/decisions`, { signal });
    return data.decisions;
  },
  async createDecision(id, payload) {
    const { data } = await api.post(`${projectPath(id)}/decisions`, payload);
    return data;
  },
  async patchDecision(id, decisionId, payload) {
    const { data } = await api.patch(
      `${projectPath(id)}/decisions/${encodeURIComponent(decisionId)}`,
      payload,
    );
    return data;
  },
};

const ERROR_MESSAGES = {
  project_not_found: "Không tìm thấy dự án này.",
  analysis_not_found: "Dự án chưa có bản phân tích nào.",
  analysis_invalid_response:
    "AI trả về nội dung không đọc được. Hãy thử model khác rồi phân tích lại.",
  allocation_not_found: "Không tìm thấy bản đề xuất phân công này.",
  allocation_hard_constraint:
    "Nguồn lực này bị ràng buộc cứng với task (ví dụ AI bị cấm phạm vi của task) nên không gán được.",
  allocation_already_decided: "Bản đề xuất này đã được duyệt hoặc từ chối rồi.",
  resource_not_found: "Không tìm thấy nguồn lực này trong Workforce.",
  project_file_too_large: "File dự án lớn hơn 5 MB.",
  project_file_empty: "File không có nội dung chữ đọc được.",
  project_file_unsupported: "Chỉ hỗ trợ file .md, .txt, .pdf hoặc .docx.",
  project_file_unreadable: "Không đọc được file — file có thể bị hỏng.",
  credentials_missing: "Provider này chưa được cấu hình key. Hãy mở trang Providers trước.",
  provider_disabled: "Provider này đang tắt. Hãy bật lại ở trang Providers.",
  model_not_synced: "Model chưa được đồng bộ cho provider này.",
  model_not_chat_capable: "Model này không hỗ trợ chat.",
  agent_not_found: "Không tìm thấy Agent này (có thể đã bị xoá).",
  agent_budget_exceeded:
    "Agent bị dừng vì vượt ngân sách xử lý (ngữ cảnh quá dài). Hãy hỏi ngắn gọn hơn hoặc thử lại.",
  agent_timeout: "Agent chạy quá thời gian cho phép nên bị dừng. Hãy thử lại.",
  agent_step_limit:
    "Agent đã dùng hết số bước xử lý cho phép. Hãy thử hỏi lại ngắn gọn hơn.",
  provider_request_rejected:
    "Provider từ chối yêu cầu — thường do key hoặc quyền truy cập model. Kiểm tra cấu hình ở trang Providers.",
  discussion_message_not_found: "Không tìm thấy tin nhắn này trong phần thảo luận.",
  decision_not_found: "Không tìm thấy quyết định này.",
  discussion_nothing_to_retry: "Không có câu trả lời lỗi nào để thử lại.",
};

export function projectErrorByCode(code, fallback = "Đã xảy ra lỗi.") {
  return ERROR_MESSAGES[code] || fallback;
}

export function getProjectError(error, fallback = "Đã xảy ra lỗi. Hãy thử lại.") {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "object" && detail !== null ? detail.code : null;
  if (code && ERROR_MESSAGES[code]) return ERROR_MESSAGES[code];
  if (typeof detail === "object" && detail !== null && detail.message) return detail.message;
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}
