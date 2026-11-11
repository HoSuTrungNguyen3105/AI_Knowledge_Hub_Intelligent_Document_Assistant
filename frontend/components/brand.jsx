import { Layers3 } from "lucide-react";
import { APP_NAME } from "../utils/app-config";

export function Brand({ compact = false }) {
  return <span className="brand"><span className="brand-mark"><Layers3 size={22} strokeWidth={1.7} aria-hidden="true" /></span>{!compact && <span>{APP_NAME}<span className="brand-caption">Không gian AI của riêng bạn</span></span>}</span>;
}
