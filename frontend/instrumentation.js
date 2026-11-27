// Wake the backend in parallel with the frontend — layer 1 of 3.
//
// Both Render services sleep when idle. register() runs once when
// this server process boots — which is exactly when Render wakes the
// frontend for the first visitor — so the wake sequence starts the
// backend's wake-up at the same moment, not after the first page has
// loaded. The other layers (proxy nudge on page requests, the
// inline script in the root layout) cover the cases this one cannot:
// a warm frontend process with a re-slept backend, and the earliest
// possible browser-side signal. All layers share utils/wake-backend.

import { wakeBackend, warnIfBackendUrlMisconfigured } from "./utils/wake-backend";

export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  warnIfBackendUrlMisconfigured();
  // Fire and forget: never block or fail the frontend's own boot.
  void wakeBackend();
}
