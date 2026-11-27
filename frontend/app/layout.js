import "./globals.css";
import Script from "next/script";
import { Providers } from "../components/providers";
import { APP_NAME } from "../utils/app-config";
import { WAKE_PING_PATH } from "../utils/wake-backend";

export const metadata = {
  title: { default: APP_NAME, template: `%s | ${APP_NAME}` },
  description: "Không gian AI cá nhân để kết nối provider, model và tri thức của bạn.",
  robots: { index: false, follow: false },
  // Favicon: the PNG Nguyên added at images/ in the repo root. It is
  // referenced by URL because the file is binary; to self-host it
  // later, drop the same PNG at frontend/app/icon.png and remove this.
  icons: {
    icon: "https://raw.githubusercontent.com/HoSuTrungNguyen3105/AI_Knowledge_Hub_Intelligent_Document_Assistant/main/images/f1d82c88-81e8-4bfc-8f4d-8194e3ca78f6.png",
  },
};

// Wake layer 3: the earliest browser-side signal. next/script with
// strategy="beforeInteractive" in the root layout is injected into
// the document <head>, so this runs as soon as the HTML reaches the
// browser — before the JS bundle has even downloaded, a full step
// ahead of the wake banner's post-hydration polling. It pings the
// health endpoint through the /api/v1 rewrite (which is what wakes
// the backend), retries every ~5s up to ~24 times, and stops at the
// first OK. Fully self-contained: no React, no bundle, no rendering
// blocked, network errors swallowed.
const EARLY_WAKE_SCRIPT = `(function(){var attempts=0;var MAX=24;var DELAY=5000;function again(){if(attempts<MAX){setTimeout(ping,DELAY);}}function ping(){attempts+=1;try{fetch(${JSON.stringify(WAKE_PING_PATH)},{cache:"no-store"}).then(function(res){if(!res||!res.ok){again();}}).catch(again);}catch(e){again();}}ping();})();`;

export default function RootLayout({ children }) {
  // suppressHydrationWarning on <html> and <body>: browser extensions inject
  // attributes (bis_skin_checked, bis_register, data-cc-prev-cursor, cursor
  // styles) into the DOM before React hydrates, which otherwise surfaces as a
  // dev-overlay hydration mismatch that is not caused by app code.
  return (
    <html lang="vi" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Script
          id="early-backend-wake"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: EARLY_WAKE_SCRIPT }}
        />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
