import "./globals.css";
import { Providers } from "../components/providers";

export const metadata = {
  title: { default: "AI Knowledge Hub", template: "%s | Knowledge Hub" },
  description: "Không gian cá nhân để quản lý tài liệu và kết nối tri thức với AI.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }) {
  return <html lang="vi"><body><Providers>{children}</Providers></body></html>;
}
