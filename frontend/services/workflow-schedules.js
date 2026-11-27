import { api } from "./api";

const path = "/ai/workflow-schedules";

// Workflow schedules (Scheduler phase 1): configuration for when a saved
// AI Factory request should fire through n8n. The backend stores the
// schedule and computes next runs; activation lands in phase 2.
export const workflowSchedulesService = {
  async list({ status, search } = {}, signal) {
    const params = {};
    if (status) params.status = status;
    if (search) params.search = search;
    const { data } = await api.get(path, { params, signal });
    return data;
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
  async pause(id, signal) {
    const { data } = await api.post(`${path}/${id}/pause`, {}, { signal });
    return data;
  },
  async resume(id, signal) {
    const { data } = await api.post(`${path}/${id}/resume`, {}, { signal });
    return data;
  },
  async runNow(id, signal) {
    const { data } = await api.post(`${path}/${id}/run-now`, {}, { signal });
    return data;
  },
  async listExecutions(id, signal) {
    const { data } = await api.get(`${path}/${id}/executions`, { signal });
    return data;
  },
  async preview(payload, signal) {
    const { data } = await api.post(`${path}/preview`, payload, { signal });
    return data;
  },
  async getHealth(signal) {
    const { data } = await api.get(`${path}/health`, { signal });
    return data;
  },
};

const SCHEDULE_ERRORS = {
  schedule_not_found: "Lịch này không còn tồn tại. Tải lại danh sách rồi thử lại.",
  schedule_invalid:
    "Cấu hình lịch chưa hợp lệ. Kiểm tra giờ, ngày trong tuần hoặc biểu thức cron.",
  schedule_in_past: "Lịch chạy một lần phải đặt ở thời điểm trong tương lai.",
};

export function getScheduleError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail?.code && SCHEDULE_ERRORS[detail.code]) return SCHEDULE_ERRORS[detail.code];
  if (typeof detail === "string") return detail;
  return fallback;
}
