import { create } from "zustand";

export const useNotice = create((set) => ({
  notice: null,
  show: (message, type = "success") => set({ notice: { message, type, id: Date.now() } }),
  dismiss: () => set({ notice: null }),
}));
