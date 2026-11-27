"use client";

import { useEffect, useRef, useState } from "react";
import { setServerStatus } from "../utils/server-status";
import { WAKE_PING_PATH } from "../utils/wake-backend";

// Wake-up strip shown only while the backend is still starting
// (Render free tier sleeps after ~15 idle minutes and needs
// 30-90 seconds to come back). It polls the lightweight
// /health/ping endpoint: a fast first answer means the strip never
// appears at all (no flash on warm loads); success fills the bar
// to 100% and fades it out; no answer after GIVE_UP_MS means a
// real outage, not a wake-up, and only then is an error shown.
const POLL_MS = 3000;
const GRACE_MS = 1500;
const GIVE_UP_MS = 120000;

async function pingServer() {
  try {
    const response = await fetch(WAKE_PING_PATH, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export function ServerWakeBanner() {
  const [phase, setPhase] = useState("hidden"); // hidden | waking | done | offline
  const [progress, setProgress] = useState(0);
  const [cycle, setCycle] = useState(0);
  const phaseRef = useRef("hidden");

  useEffect(() => {
    let cancelled = false;
    let pollTimer = null;
    let tickTimer = null;
    let hideTimer = null;
    const startedAt = Date.now();
    phaseRef.current = "hidden";
    setPhase("hidden");
    setProgress(0);
    setServerStatus("checking");

    const succeed = () => {
      if (cancelled) return;
      setServerStatus("online");
      setProgress(100);
      if (pollTimer) clearInterval(pollTimer);
      if (tickTimer) clearInterval(tickTimer);
      if (phaseRef.current !== "hidden") {
        phaseRef.current = "done";
        setPhase("done");
        hideTimer = setTimeout(() => {
          if (cancelled) return;
          phaseRef.current = "hidden";
          setPhase("hidden");
        }, 700);
      }
    };

    const attempt = async () => {
      if (await pingServer()) succeed();
    };
    attempt();
    pollTimer = setInterval(attempt, POLL_MS);
    tickTimer = setInterval(() => {
      if (cancelled) return;
      const elapsed = Date.now() - startedAt;
      if (phaseRef.current === "hidden" && elapsed >= GRACE_MS) {
        phaseRef.current = "waking";
        setPhase("waking");
        setServerStatus("waking");
      }
      if (phaseRef.current === "waking") {
        setProgress(Math.min(90, 90 * (1 - Math.exp(-elapsed / 30000))));
        if (elapsed >= GIVE_UP_MS) {
          phaseRef.current = "offline";
          setPhase("offline");
          setServerStatus("offline");
          if (pollTimer) clearInterval(pollTimer);
          if (tickTimer) clearInterval(tickTimer);
        }
      }
    }, 200);

    return () => {
      cancelled = true;
      if (pollTimer) clearInterval(pollTimer);
      if (tickTimer) clearInterval(tickTimer);
      if (hideTimer) clearTimeout(hideTimer);
    };
  }, [cycle]);

  if (phase === "hidden") return null;
  return (
    <div className={`server-wake ${phase}`} role={phase === "offline" ? "alert" : "status"}>
      <div className="server-wake-track">
        <div
          className="server-wake-fill"
          style={{ width: `${phase === "offline" ? 100 : progress}%` }}
        />
      </div>
      <div className="server-wake-body">
        {phase === "offline" ? (
          <>
            <span>
              Máy chủ chưa phản hồi sau 2 phút — có thể máy chủ đang gặp sự cố, không còn là
              đang khởi động nữa.
            </span>
            <button
              type="button"
              className="server-wake-retry"
              onClick={() => setCycle((value) => value + 1)}
            >
              Thử lại
            </button>
          </>
        ) : phase === "done" ? (
          <span>Máy chủ đã sẵn sàng.</span>
        ) : (
          <>
            <span className="wake-dot" />
            <span>Máy chủ đang khởi động, thường mất 30–90 giây…</span>
          </>
        )}
      </div>
    </div>
  );
}
