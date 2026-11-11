"use client";

import { useEffect } from "react";
import { CheckCircle2, CircleAlert, X } from "lucide-react";
import { useNotice } from "../stores/notice";
import { useSession } from "../stores/session";

export function Providers({ children }) {
  const notice = useNotice((state) => state.notice);
  const dismiss = useNotice((state) => state.dismiss);
  const clear = useSession((state) => state.clear);
  useEffect(() => {
    const onExpired = () => clear();
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, [clear]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(dismiss, 5000);
    return () => clearTimeout(timer);
  }, [notice, dismiss]);
  return <>{children}{notice && <div className={`toast ${notice.type}`} role={notice.type === "error" ? "alert" : "status"}>
    {notice.type === "error" ? <CircleAlert size={20} /> : <CheckCircle2 size={20} />}
    <span>{notice.message}</span><button className="icon-button" aria-label="Đóng thông báo" onClick={dismiss}><X size={17} /></button>
  </div>}</>;
}
