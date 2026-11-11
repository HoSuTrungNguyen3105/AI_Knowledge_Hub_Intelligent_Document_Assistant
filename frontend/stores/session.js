import { create } from "zustand";
import { authService } from "../services/auth";

let pendingSession = null;
export const useSession = create((set, get) => ({
  user: null,
  status: "idle",
  error: null,
  acceptUser: (user) => set({ user, status: "authenticated", error: null }),
  clear: () => set({ user: null, status: "guest", error: null }),
  hydrate: async (force = false) => {
    if (pendingSession) return pendingSession;
    if (!force && ["authenticated", "guest"].includes(get().status)) return;
    set({ status: "checking", error: null });
    pendingSession = authService.me()
      .then((user) => set({ user, status: "authenticated", error: null }))
      .catch((error) => set({
        user: null,
        status: [401, 403].includes(error.response?.status) ? "guest" : "unavailable",
        error,
      }))
      .finally(() => { pendingSession = null; });
    return pendingSession;
  },
}));
