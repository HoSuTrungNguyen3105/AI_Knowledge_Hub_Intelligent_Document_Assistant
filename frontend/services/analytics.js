import { api } from "./api";

// Executive analytics (NEXORA Module 01): computed by the backend from
// the caller's real records — see /ai/analytics/overview.
export const analyticsService = {
  async overview(signal) {
    const { data } = await api.get("/ai/analytics/overview", { signal });
    return data;
  },
};
