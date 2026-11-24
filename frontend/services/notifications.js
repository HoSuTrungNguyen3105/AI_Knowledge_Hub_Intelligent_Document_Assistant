import { api } from "./api";

// In-app notifications (NEXORA Module 15): emitted by the backend when
// workflows finish, factory runs complete, approvals change state, ...
export const notificationsService = {
  async list(signal) {
    const { data } = await api.get("/ai/notifications", { signal });
    return data;
  },
  async markRead(id) {
    const { data } = await api.post(`/ai/notifications/${id}/read`);
    return data;
  },
  async markAllRead() {
    const { data } = await api.post("/ai/notifications/read-all");
    return data;
  },
};
