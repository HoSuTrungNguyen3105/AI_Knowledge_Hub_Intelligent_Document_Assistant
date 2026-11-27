// Wake the backend in parallel with the frontend.
//
// Both Render services sleep when idle. The browser-side wake banner
// only starts polling after the page has loaded, so the backend used
// to start waking a full step behind the frontend. register() runs
// once when this server process boots — which is exactly when Render
// wakes the frontend for the first visitor — so the pings below start
// the backend's wake-up at the same moment, not after it.

const WAKE_ATTEMPTS = 8;
const WAKE_INTERVAL_MS = 15_000;
const WAKE_TIMEOUT_MS = 30_000;

async function wakeBackend(backendUrl) {
  for (let attempt = 1; attempt <= WAKE_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(`${backendUrl}/api/v1/health/ping`, {
        signal: AbortSignal.timeout(WAKE_TIMEOUT_MS),
        cache: "no-store",
      });
      if (response.ok) return;
    } catch {
      // Backend still asleep or unreachable — keep trying for a while.
    }
    if (attempt < WAKE_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, WAKE_INTERVAL_MS));
    }
  }
}

export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  // Fire and forget: never block or fail the frontend's own boot.
  void wakeBackend(backendUrl);
}
