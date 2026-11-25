// Shared display helpers for synced provider models: billing class,
// chat support and the last real generation check. Every model picker
// uses these so all screens describe the same model the same way.
import { formatDate } from "./format";

export function pricingLabel(model) {
  const pricing = model?.pricing;
  if (!pricing) return "";
  if (pricing.tier === "priced") {
    const input = pricing.input_per_million;
    const output = pricing.output_per_million;
    if (input != null && output != null) {
      return `Có phí: $${input} vào / $${output} ra mỗi 1M token`;
    }
    return "Có phí theo token";
  }
  if (pricing.tier === "subscription") return "Theo gói thuê bao";
  return "Chưa rõ giá";
}

export function healthLabel(model) {
  if (!model?.health_status) return "Chưa kiểm tra";
  const when = model.health_checked_at
    ? ` (${formatDate(model.health_checked_at)})`
    : "";
  return model.health_status === "ok"
    ? `Hoạt động tốt${when}`
    : `Lỗi ${model.health_error_code || "không rõ"}${when}`;
}

// Compact suffix for <option> labels and checkbox rows, e.g.
// "GPT-4o mini — có phí · đã kiểm tra ✓".
export function modelSuffix(model) {
  const parts = [];
  if (model?.capabilities?.chat === false) parts.push("không hỗ trợ chat");
  if (model?.pricing?.tier === "priced") parts.push("có phí");
  if (model?.pricing?.tier === "subscription") parts.push("theo gói");
  if (model?.health_status === "error") {
    parts.push(`lỗi: ${model.health_error_code || "không rõ"}`);
  }
  if (model?.health_status === "ok") parts.push("đã kiểm tra ✓");
  return parts.length ? ` — ${parts.join(" · ")}` : "";
}

export function modelOptionLabel(model) {
  return `${model?.display_name || model?.id || ""}${modelSuffix(model)}`;
}
