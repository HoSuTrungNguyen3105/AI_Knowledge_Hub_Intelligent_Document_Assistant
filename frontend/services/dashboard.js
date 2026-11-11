import { api } from "./api";

export async function fetchDashboard(signal) {
  const { data } = await api.get("/dashboard", { signal });
  return data;
}
