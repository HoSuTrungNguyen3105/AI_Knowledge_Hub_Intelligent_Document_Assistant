import { api } from "./api";

const base = "/ai/workspaces";

// Workspace Management (NEXORA Module 02). Every call is scoped by the
// backend to workspaces the caller belongs to; roles are enforced there.
export const workspacesService = {
  async list(signal) {
    const { data } = await api.get(base, { signal });
    return data.workspaces || [];
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
  async listMembers(id, signal) {
    const { data } = await api.get(`${base}/${id}/members`, { signal });
    return data.members || [];
  },
  async addMember(id, payload, signal) {
    const { data } = await api.post(`${base}/${id}/members`, payload, { signal });
    return data;
  },
  async patchMember(id, userId, payload, signal) {
    const { data } = await api.patch(`${base}/${id}/members/${userId}`, payload, { signal });
    return data;
  },
  async removeMember(id, userId, signal) {
    await api.delete(`${base}/${id}/members/${userId}`, { signal });
  },
};

const MESSAGES = {
  workspace_user_not_found: "Không có tài khoản MindFlow nào dùng email này.",
  workspace_member_exists: "Tài khoản này đã là thành viên của workspace.",
  workspace_forbidden: "Vai trò của bạn trong workspace này không cho phép thao tác đó.",
  workspace_owner_immutable: "Không thể đổi vai trò hoặc xoá chủ sở hữu workspace.",
  workspace_personal_undeletable: "Không thể xoá không gian cá nhân.",
  workspace_not_found: "Workspace không tồn tại hoặc bạn không phải thành viên.",
};

export function getWorkspaceError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && MESSAGES[detail.code]) return MESSAGES[detail.code];
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}
