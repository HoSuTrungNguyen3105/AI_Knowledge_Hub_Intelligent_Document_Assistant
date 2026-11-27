import { NextResponse } from "next/server";
import { nudgeBackend } from "./utils/wake-backend";

// Wake layer 2: a page request nudges the backend awake.
//
// instrumentation's register() only fires when this process boots,
// so when the frontend process stays warm while the backend falls
// asleep again (the common case on Render free), nothing server-side
// used to start the backend waking until the browser's own calls
// arrived. This middleware closes that gap: every page request kicks
// a throttled, fire-and-forget ping sequence (see wake-backend.js),
// so the backend starts waking the moment a visitor shows up.
//
// The matcher limits this to page/document requests: API calls (they
// wake the backend by themselves through the rewrite), Next static
// assets and any file with an extension never reach here.
export function middleware(request, event) {
  if (request.method === "GET") {
    const pending = nudgeBackend();
    if (pending && event && typeof event.waitUntil === "function") {
      event.waitUntil(pending);
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\..*).*)"],
};
