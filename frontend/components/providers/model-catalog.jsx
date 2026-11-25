"use client";

import { useState } from "react";
import { Boxes, Search } from "lucide-react";
import { capabilityLabel, filterModels } from "../../utils/providers";
import { healthLabel, pricingLabel } from "../../utils/model-info";
import { formatCount, formatDate } from "../../utils/format";

export function ModelCatalog({ models, loading, error, syncedAt, onRetry, onCheck, checkingId }) {
  const [query, setQuery] = useState("");
  const filtered = filterModels(models, query);
  return <section className="model-catalog" aria-busy={loading}>
    <div className="provider-section-heading"><div><h3>Model được đồng bộ</h3><p>{syncedAt ? `Lần đồng bộ gần nhất: ${formatDate(syncedAt)}` : "Danh sách chỉ xuất hiện sau khi kiểm tra kết nối thành công."}</p></div><span className="model-count">{models.length} model</span></div>
    {loading ? <div className="model-loading" role="status" aria-label="Đang tải model"><div className="skeleton" /><div className="skeleton" /></div> : error ? <div className="provider-inline-error" role="alert"><p>{error}</p><button className="button secondary" onClick={onRetry}>Thử tải lại</button></div> : models.length === 0 ? <div className="models-empty"><Boxes size={25} /><p>{syncedAt ? "Provider trả về danh sách model rỗng." : "Chưa có model nào được đồng bộ."}</p><small>Không sử dụng model mẫu hoặc tự đoán quyền truy cập.</small></div> : <>
      <label className="model-search"><Search size={16} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm theo tên hoặc ID model" aria-label="Tìm model đã đồng bộ" /></label>
      <div className="model-table-scroll" role="region" aria-label="Danh sách model và capabilities" tabIndex={0}><table className="model-table"><thead><tr><th>Model</th><th>Chat</th><th>Streaming</th><th>Tools</th><th>Giá</th><th>Trạng thái chạy</th><th>Giới hạn token<br /><span>Input / Output</span></th><th></th></tr></thead><tbody>{filtered.map((model) => <tr key={model.id}><td><strong>{model.display_name || model.id}</strong><code>{model.id}</code></td><td>{capabilityLabel(model.capabilities?.chat)}</td><td>{capabilityLabel(model.capabilities?.streaming)}</td><td>{capabilityLabel(model.capabilities?.tools)}</td><td>{pricingLabel(model)}</td><td>{healthLabel(model)}</td><td>{model.input_token_limit == null ? "—" : formatCount(model.input_token_limit)} / {model.output_token_limit == null ? "—" : formatCount(model.output_token_limit)}</td><td>{onCheck && <button type="button" className="button secondary" disabled={Boolean(checkingId)} onClick={() => onCheck(model.id)}>{checkingId === model.id ? "Đang kiểm tra…" : "Kiểm tra"}</button>}</td></tr>)}</tbody></table>{filtered.length === 0 && <p className="model-no-match">Không tìm thấy model phù hợp.</p>}</div>
    </>}
    <p className="capability-disclaimer">“Chưa xác định” nghĩa là API danh sách model không cung cấp thông tin này. Có tên trong danh sách không bảo đảm model có quyền tạo nội dung, quota hoặc hỗ trợ mọi công cụ — bấm “Kiểm tra” để gọi thử một lượt tạo nội dung thật (tốn tối đa ~16 token). Giá là giá niêm yết công bố (provider công bố hoặc bảng tham chiếu); tài khoản free-tier có thể được miễn trong hạn mức của nhà cung cấp.</p>
  </section>;
}
