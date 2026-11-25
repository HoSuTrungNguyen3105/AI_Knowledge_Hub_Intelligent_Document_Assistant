import { api } from "./api";

export const authService = {
  async register(values) {
    const { data } = await api.post("/auth/register", values, { skipAuthRefresh: true });
    return data.user;
  },
  async login(values) {
    const { data } = await api.post("/auth/login", values, { skipAuthRefresh: true });
    return data.user;
  },
  async updateProfile(values) {
    const { data } = await api.patch("/auth/me", values);
    return data;
  },
  async me() {
    const { data } = await api.get("/auth/me");
    return data;
  },
  async logout() {
    await api.post("/auth/logout", {}, { skipAuthRefresh: true });
  },
};
