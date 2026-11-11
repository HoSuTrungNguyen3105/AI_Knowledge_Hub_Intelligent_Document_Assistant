import Link from "next/link";

export default function NotFound() {
  return <main className="session-state"><span className="eyebrow">404</span><h1>Không tìm thấy trang này</h1><p className="muted">Đường dẫn có thể không tồn tại.</p><Link className="button primary" href="/dashboard">Về trang tổng quan</Link></main>;
}
