import { api } from "./api";

const path = "/ai/seed/demo";

// NEXORA demo seeding for the signed-in account. The backend only allows
// this outside production, creates records flagged is_demo, and removal
// only ever touches those flagged records.
export const seedService = {
  async status(signal) {
    const { data } = await api.get(path, { signal });
    return data;
  },
  async apply(signal) {
    const { data } = await api.post(path, {}, { signal });
    return data;
  },
  async remove(signal) {
    const { data } = await api.delete(path, { signal });
    return data;
  },
};

export function getSeedError(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === "object" && detail.code === "seed_disabled") {
    return "Môi trường production không cho phép nạp dữ liệu demo.";
  }
  if (detail && typeof detail === "object" && detail.code === "seed_provider_required") {
    return "Hãy cấu hình ít nhất một provider (nhập key, kiểm tra kết nối để đồng bộ model) trước khi nạp dữ liệu demo.";
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") return detail;
  if (!error?.response) return "Không kết nối được máy chủ MindFlow. Hãy kiểm tra backend đang chạy.";
  return fallback;
}
