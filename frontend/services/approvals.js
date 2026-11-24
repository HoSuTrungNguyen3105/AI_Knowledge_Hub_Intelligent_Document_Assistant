import { api } from "./api";

// Human approvals (NEXORA Module 10): workflows created with
// requires_approval park at a gate until the owner decides here.
export const approvalsService = {
  async list(status, signal) {
    const { data } = await api.get("/ai/approvals", {
      params: status ? { status } : {},
      signal,
    });
    return data.approvals;
  },
  async decide(id, decision, comment) {
    const { data } = await api.post(`/ai/approvals/${id}/decide`, {
      decision,
      comment: comment || null,
    });
    return data;
  },
};

export function getApprovalError(error) {
  const code = error?.response?.data?.detail?.code;
  if (code === "approval_already_decided") return "Yêu cầu này đã được quyết định rồi.";
  if (code === "approval_not_found") return "Không tìm thấy yêu cầu duyệt.";
  return error?.response?.data?.detail?.message || "Đã xảy ra lỗi. Vui lòng thử lại.";
}
