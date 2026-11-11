"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { authService } from "../services/auth";
import { getErrorMessage } from "../services/api";
import { useSession } from "../stores/session";
import { useNotice } from "../stores/notice";

export function useAuthForm(mode) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const acceptUser = useSession((state) => state.acceptUser);
  const show = useNotice((state) => state.show);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const values = { email: String(form.get("email")).trim(), password: String(form.get("password")) };
    if (mode === "register") {
      values.name = String(form.get("name")).trim();
      if (!values.name) { setError("Vui lòng nhập tên của bạn."); return; }
      if (values.password !== form.get("confirmPassword")) { setError("Hai mật khẩu chưa khớp nhau."); return; }
    }
    setBusy(true);
    setError("");
    try {
      const user = await authService[mode](values);
      acceptUser(user);
      show(mode === "register" ? "Tài khoản đã được tạo. Chào mừng bạn!" : "Đăng nhập thành công.");
      router.replace("/dashboard");
    } catch (failure) {
      setError(getErrorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return { submit, busy, error };
}
