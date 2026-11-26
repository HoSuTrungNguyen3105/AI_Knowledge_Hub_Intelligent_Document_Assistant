import { useSyncExternalStore } from "react";

// Shared "is the backend awake yet" state for the whole shell.
// ServerWakeBanner owns the polling loop and publishes here; the
// dashboard error panel and the topbar status dot subscribe, so
// every surface tells the same story instead of one saying
// "offline" while another says "starting":
//   checking -> waking -> online   (normal cold start)
//   checking -> waking -> offline  (no answer after the wake window)
let status = "checking";
const listeners = new Set();

export function setServerStatus(next) {
  if (status === next) return;
  status = next;
  for (const listener of listeners) listener();
}

export function getServerStatus() {
  return status;
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useServerStatus() {
  return useSyncExternalStore(subscribe, getServerStatus, () => "checking");
}
