import "./globals.css";
import { Providers } from "../components/providers";
import { APP_NAME } from "../utils/app-config";

export const metadata = {
  title: { default: APP_NAME, template: `%s | ${APP_NAME}` },
  description: "Không gian AI cá nhân để kết nối provider, model và tri thức của bạn.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }) {
  // suppressHydrationWarning on <html> and <body>: browser extensions inject
  // attributes (bis_skin_checked, bis_register, data-cc-prev-cursor, cursor
  // styles) into the DOM before React hydrates, which otherwise surfaces as a
  // dev-overlay hydration mismatch that is not caused by app code.
  return <html lang="vi" suppressHydrationWarning><body suppressHydrationWarning><Providers>{children}</Providers></body></html>;
}
