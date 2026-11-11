"use client";

export default function ErrorPage({ reset }) {
  return <div className="session-state" role="alert"><h1>Không thể hiển thị trang</h1><p className="muted">Có lỗi khi tải nội dung. Vui lòng thử lại.</p><button className="button primary" onClick={reset}>Tải lại nội dung</button></div>;
}
