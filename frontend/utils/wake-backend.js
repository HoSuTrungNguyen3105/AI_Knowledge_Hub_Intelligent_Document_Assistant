// Shared backend wake-up helper for every server-side wake layer,
// plus the one ping path every layer (server and browser) uses.
//
// Both Render services sleep when idle. Three signals now race to
// start the backend's wake-up as early as possible:
//   1. instrumentation register() — when this server process boots;
//   2. proxy nudge — when a page is requested while this process
//      is warm but the backend has fallen asleep again;
//   3. the inline script in the root layout — as soon as the HTML
//      reaches the browser (that one only needs WAKE_PING_PATH).
// This module is server-runtime code (instrumentation + proxy);
// it must stay free of React/browser-only APIs. The browser banner
// imports only the WAKE_PING_PATH constant from here.

export const WAKE_PING_PATH = "/api/v1/health/ping";

const FALLBACK_BACKEND_URL = "http://127.0.0.1:8000";
const WAKE_ATTEMPTS = 8;
const WAKE_INTERVAL_MS = 15_000;
const WAKE_TIMEOUT_MS = 30_000;
const NUDGE_THROTTLE_MS = 60_000;

export function getBackendUrl() {
  return process.env.BACKEND_URL || FALLBACK_BACKEND_URL;
}

export function backendPingUrl() {
  return `${getBackendUrl()}${WAKE_PING_PATH}`;
}

// A missing or localhost BACKEND_URL in production means every wake
// ping goes nowhere and the backend only wakes when the browser's
// own API calls trickle through the rewrite — the exact failure this
// helper exists to prevent. Say so loudly once at boot instead of
// failing silently; never throw, the frontend must still boot.
export function warnIfBackendUrlMisconfigured() {
  if (process.env.NODE_ENV !== "production") return;
  const configured = process.env.BACKEND_URL;
  if (!configured || /^(https?:\/\/)?(localhost|127\.0\.0\.1)([:/]|$)/.test(configured)) {
    console.warn(
      "[wake-backend] BACKEND_URL is missing or points at localhost in production; " +
        "server-side wake pings cannot reach the backend. " +
        "Set BACKEND_URL to the backend service URL.",
    );
  }
}

// Ping the backend until it answers OK, giving up after a bounded
// number of attempts. Never throws: a still-sleeping or unreachable
// backend is an expected state here, not an error.
export async function wakeBackend({
  attempts = WAKE_ATTEMPTS,
  intervalMs = WAKE_INTERVAL_MS,
  timeoutMs = WAKE_TIMEOUT_MS,
} = {}) {
  const url = backendPingUrl();
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        signal: AbortSignal.timeout(timeoutMs),
        cache: "no-store",
      });
      if (response.ok) return true;
    } catch {
      // Backend still asleep or unreachable — keep trying for a while.
    }
    if (attempt < attempts) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  return false;
}

// Throttled fire-and-forget wake for per-request nudges: at most one
// wake sequence per throttle window per process, no matter how many
// page requests arrive. Returns the wake promise when a sequence was
// started (so callers with a waitUntil hook can keep it alive), or
// null when this call was throttled.
let lastNudgeAt = 0;

export function nudgeBackend() {
  const now = Date.now();
  if (now - lastNudgeAt < NUDGE_THROTTLE_MS) return null;
  lastNudgeAt = now;
  return wakeBackend();
}
