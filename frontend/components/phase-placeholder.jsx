import Link from "next/link";
import { ArrowLeft, Clock3, ArrowRight } from "lucide-react";

export function PhasePlaceholder({ section }) {
  return <>
  {/* <div className="page-heading"><div><p className="eyebrow">Lộ trình phát triển</p><h1>{section.title}</h1><p className="muted">Xây dựng từng bước, kiểm thử từng giai đoạn.</p></div>
  <span className="phase-badge"><Clock3 size={14} />{section.phase}</span>
  </div> */}
  <section className="roadmap-panel"><span className="soft-icon">
    <Clock3 size={26} />
  </span><h2>Tính năng chưa được triển khai</h2><p>{section.description}</p><ul>{section.items.map((item) => <li key={item}><ArrowRight size={16} /><span>{item}</span></li>)}</ul><div className="roadmap-note">Phiên bản hiện tại có xác thực, dashboard và quản lý provider/model ở Cài đặt. Tính năng trên trang này chưa được triển khai; không có kết quả AI giả lập.</div><Link className="button secondary" href="/dashboard"><ArrowLeft size={16} />Về trang tổng quan</Link></section></>;
}
