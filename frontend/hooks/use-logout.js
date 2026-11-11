"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authService } from "../services/auth";
import { getErrorMessage } from "../services/api";
import { useSession } from "../stores/session";
import { useNotice } from "../stores/notice";

export function useLogout() {
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  const clear = useSession((state) => state.clear);
  const show = useNotice((state) => state.show);
  async function logout() {
    if (busy) return;
    setBusy(true);
    try {
      await authService.logout();
      clear();
      show("Đã đăng xuất và thu hồi phiên đăng nhập.");
      router.replace("/login");
    } catch (error) {
      show(getErrorMessage(error), "error");
    } finally { setBusy(false); }
  }
  return { logout, busy };
}
