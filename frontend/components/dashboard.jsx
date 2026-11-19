"use client";

import Link from "next/link";
import { Columns2, ArrowRight, FileText, LibraryBig, MessagesSquare, Activity, Check, Clock3, RefreshCw, CircleAlert, ShieldCheck, Layers3 } from "lucide-react";
import { useDashboard } from "../hooks/use-dashboard";
import { useSession } from "../stores/session";
import { getErrorMessage } from "../services/api";
import { formatActivity, formatCount, formatDate } from "../utils/format";
import { APP_STAGE } from "../utils/app-config";

const metrics = [
  { label: "Tài liệu", key: "total_documents", icon: FileText, caption: "Trong không gian của bạn" },
  { label: "Kho kiến thức", key: "total_knowledge_bases", icon: LibraryBig, caption: "Các bộ sưu tập tài liệu" },
  { label: "Cuộc hội thoại", key: "total_conversations", icon: MessagesSquare, caption: "Lịch sử trò chuyện với AI" },
  { label: "Lượt gọi AI", key: "ai_requests_usage", icon: Activity, caption: "Tổng yêu cầu đã ghi nhận" },
];

export function Dashboard() {
  const user = useSession((state) => state.user);
  const { data, loading, error, retry } = useDashboard();
  const firstName = user?.name?.trim().split(/\s+/).at(-1) || "bạn";
  return <>
    <div className="page-heading"><div><p className="eyebrow">Không gian của riêng bạn</p><h1>Xin chào, {firstName}.</h1><p className="muted">Mọi tri thức quan trọng, cùng một nơi.</p></div><span className="phase-badge"><span className="status-dot" />{APP_STAGE}</span></div>
    {error ? <div className="error-panel" role="alert"><CircleAlert size={24} /><div><h2>Chưa tải được dữ liệu</h2><p>{getErrorMessage(error)}</p></div><button className="button secondary" onClick={retry}><RefreshCw size={16} />Thử lại</button></div> : <>
      <section className="metrics-grid" aria-label="Thống kê tài khoản" aria-busy={loading}>{metrics.map(({ label, key, icon: Icon, caption }) => <article className="metric" key={key}><div className="metric-top"><span>{label}</span><Icon size={20} strokeWidth={1.6} /></div>{loading ? <span className="skeleton metric-skeleton" /> : <strong>{formatCount(data[key])}</strong>}<p>{caption}</p></article>)}</section>
      <section className="welcome-panel"><div className="welcome-copy"><span className="soft-icon"><Layers3 size={23} strokeWidth={1.6} /></span><h2>Kết nối AI của bạn.<br className="desktop-break" /> Giữ mọi thứ trong một nơi.</h2><p>Cấu hình OpenAI hoặc Gemini bằng API key riêng, kiểm tra kết nối và chọn model mặc định trước khi bước vào Chat, Compare và Agent.</p><Link className="text-link" href="/settings">Quản lý kết nối AI<ArrowRight size={17} /></Link></div><div className="foundation-list"><h3>Nền tảng của bạn</h3><div><span className="check-icon"><Check size={15} /></span><p>Tài khoản cá nhân<small>Đã đăng nhập và xác thực</small></p></div><div><span className="check-icon"><Check size={15} /></span><p>Không gian riêng tư<small>Dữ liệu được phân quyền theo tài khoản</small></p></div><div><span className="check-icon"><Check size={15} /></span><p>Chat, Compare và Agent Studio<small>Đã sẵn sàng · Phase 3–5</small></p></div></div></section>
      <div className="dashboard-columns"><section className="activity-panel"><div className="section-heading"><h2>Hoạt động gần đây</h2><button className="icon-button" onClick={retry} disabled={loading} aria-label="Làm mới hoạt động"><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div>{loading ? <div className="activity-loading" role="status" aria-label="Đang tải hoạt động">{[1, 2, 3].map((index) => <div key={index} className="skeleton activity-skeleton" />)}</div> : data.recent_activity.length > 0 ? <ul className="activity-list">{data.recent_activity.map((item) => <li key={item.id}><span className="activity-symbol"><ShieldCheck size={17} /></span><div><p>{formatActivity(item)}</p><time dateTime={item.created_at}>{formatDate(item.created_at)}</time></div></li>)}</ul> : <div className="empty-state"><Clock3 size={28} /><p>Chưa có hoạt động nào.</p><small>Các hoạt động của bạn sẽ xuất hiện ở đây.</small></div>}</section>
        <section className="quick-panel"><div className="section-heading"><h2>Khám phá bước tiếp theo</h2></div><p className="muted section-description">Chat, Compare và Agent Studio đã sẵn sàng. Giao việc với công cụ và theo dõi lịch sử thực thi.</p><Link href="/chat" className="quick-link"><MessagesSquare size={19} /><span>Trò chuyện cùng nhiều model<small>Multi-model Chat · Phase 3</small></span><ArrowRight size={16} /></Link><Link href="/compare" className="quick-link"><Columns2 size={19} /><span>So sánh và tổng hợp kết quả<small>Compare AI · Phase 4</small></span><ArrowRight size={16} /></Link><Link href="/agents" className="quick-link"><Activity size={19} /><span>Để AI hỗ trợ công việc<small>AI Agents · Phase 5</small></span><ArrowRight size={16} /></Link></section></div>
      <p className="data-note"><ShieldCheck size={14} />Số liệu được lấy trực tiếp từ cơ sở dữ liệu của tài khoản, không sử dụng dữ liệu mẫu.</p>
    </>}
  </>;
}
