import "./globals.css";
import { Providers } from "../components/providers";
import { APP_NAME } from "../utils/app-config";

export const metadata = {
  title: { default: APP_NAME, template: `%s | ${APP_NAME}` },
  description: "Không gian AI cá nhân để kết nối provider, model và tri thức của bạn.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }) {
  return <html lang="vi" suppressHydrationWarning><body><Providers>{children}</Providers></body></html>;
}
