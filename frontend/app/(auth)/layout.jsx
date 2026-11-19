import Link from "next/link";
import { FileText, MessagesSquare, MoveUpRight, ShieldCheck } from "lucide-react";
import { Brand } from "../../components/brand";
import { APP_NAME, APP_STAGE } from "../../utils/app-config";

export default function AuthLayout({ children }) {
  return <main className="auth-layout"><section className="auth-story"><Link href="/" className="auth-brand"><Brand /></Link><div className="story-content"><span className="story-kicker">{APP_NAME}</span><h2>Biến tài liệu<br />thành tri thức.<br /><span>Biến tri thức<br />thành hành động.</span></h2><p>Một không gian để lưu giữ điều bạn biết, tìm lại điều bạn cần và khám phá những kết nối mới.</p><div className="story-workflow"><span><FileText size={22} />Tài liệu</span><MoveUpRight size={18} /><span><MessagesSquare size={22} />Hội thoại</span></div><small className="story-roadmap">Đã có Chat, Compare & Agents · Tài liệu/RAG triển khai sau</small></div><div className="story-footer"><ShieldCheck size={17} /><span>Tri thức của bạn. Không gian của bạn.</span></div></section><section className="auth-form-side"><Link href="/" className="mobile-auth-brand"><Brand /></Link>{children}<footer>{APP_NAME} · {APP_STAGE}</footer></section></main>;
}
