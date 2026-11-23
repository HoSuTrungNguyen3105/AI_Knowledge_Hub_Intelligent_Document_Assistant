import { Brain } from "lucide-react";
import { APP_NAME } from "../utils/app-config";

export function Brand({ compact = false }) {
  return <span className="brand"><span className="brand-mark"><Brain size={22} strokeWidth={1.7} aria-hidden="true" /></span>{!compact && <span>{APP_NAME}<span className="brand-caption">AI Knowledge Hub</span></span>}</span>;
}
