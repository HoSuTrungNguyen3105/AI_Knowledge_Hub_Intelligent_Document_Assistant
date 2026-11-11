"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, ServerOff } from "lucide-react";
import { useSession } from "../stores/session";
import { getErrorMessage } from "../services/api";

export function AuthGuard({ children }) {
  const router = useRouter();
  const status = useSession((state) => state.status);
  const error = useSession((state) => state.error);
  const hydrate = useSession((state) => state.hydrate);
  useEffect(() => { hydrate(); }, [hydrate]);
  useEffect(() => { if (status === "guest") router.replace("/login"); }, [status, router]);
  if (status === "unavailable") return <main className="session-state"><ServerOff size={32} /><h1>Chưa kết nối được máy chủ</h1><p>{getErrorMessage(error)}</p><button className="button primary" onClick={() => hydrate(true)}>Thử kết nối lại</button></main>;
  if (status !== "authenticated") return <main className="session-state" role="status"><LoaderCircle size={28} className="spin" /><p>Đang kiểm tra phiên đăng nhập…</p></main>;
  return children;
}
