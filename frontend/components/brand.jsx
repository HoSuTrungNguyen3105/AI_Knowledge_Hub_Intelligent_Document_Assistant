import { Layers3 } from "lucide-react";

export function Brand({ compact = false }) {
  return <span className="brand"><span className="brand-mark"><Layers3 size={22} strokeWidth={1.7} aria-hidden="true" /></span>{!compact && <span>Knowledge Hub<span className="brand-caption">Không gian tri thức của bạn</span></span>}</span>;
}
