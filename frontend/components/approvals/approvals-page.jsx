"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, ClipboardCheck, RefreshCw, XCircle } from "lucide-react";
import { approvalsService, getApprovalError } from "../../services/approvals";
import { getErrorMessage } from "../../services/api";

const FILTERS = [
  { value: "pending", label: "Chờ duyệt" },
  { value: "approved", label: "Đã duyệt" },
  { value: "rejected", label: "Đã từ chối" },
  { value: "changes_requested", label: "Yêu cầu sửa" },
  { value: "", label: "Tất cả" },
];

const STATUS_LABELS = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
  changes_requested: "Yêu cầu sửa",
};

const timeLabel = (iso) => new Date(iso).toLocaleString("vi-VN", {
  hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric",
});

// Approval inbox (NEXORA Module 10). A workflow that requires approval
// parks at its completion gate; deciding here completes it, fails it,
// or sends feedback back to the coordinator and relaunches the run.
export function ApprovalsPage() {
  const [filter, setFilter] = useState("pending");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async (signal) => {
    setLoading(true);
    try {
      const approvals = await approvalsService.list(filter || undefined, signal);
      setItems(approvals);
      setError("");
    } catch (e) {
      if (e?.name !== "AbortError") setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const selected = items.find((a) => a.id === selectedId) || null;

  const decide = async (decision) => {
    if (!selected || busy) return;
    setBusy(decision);
    setNotice("");
    try {
      const result = await approvalsService.decide(selected.id, decision, comment.trim());
      setNotice(
        decision === "approved"
          ? "Đã duyệt — workflow đã hoàn thành với kết quả đã lưu."
          : decision === "rejected"
            ? "Đã từ chối — workflow đã dừng với trạng thái thất bại."
            : `Đã gửi góp ý cho Điều phối và chạy lại workflow (trạng thái: ${result.workflow_status || "waiting"}).`
      );
      setComment("");
      await load();
    } catch (e) {
      setNotice(getApprovalError(e));
    } finally {
      setBusy("");
    }
  };

  return <div className="wf-page">
    <div className="wf-header">
      <div>
        <h1><ClipboardCheck size={22} /> Phê duyệt</h1>
        <p className="muted">Workflow bật &quot;Cần duyệt trước khi hoàn thành&quot; sẽ dừng ở cổng duyệt kèm kết quả — quyết định của bạn ở đây sẽ chốt workflow đó.</p>
      </div>
      <button className="wf-btn" type="button" onClick={() => load()}><RefreshCw size={15} /> Làm mới</button>
    </div>

    <div className="wf-chip-row" role="group" aria-label="Lọc theo trạng thái" style={{ marginBottom: 14 }}>
      {FILTERS.map((f) => <button key={f.value || "all"} type="button" aria-pressed={filter === f.value}
        className={`wf-chip${filter === f.value ? " selected" : ""}`} onClick={() => setFilter(f.value)}>{f.label}</button>)}
    </div>

    {error && <p className="wf-error" role="alert">{error}</p>}
    {loading ? <p className="wf-empty">Đang tải yêu cầu duyệt…</p>
      : !items.length ? <p className="wf-empty">Không có yêu cầu nào ở mục này.</p>
      : <>
        <div className="wf-grid">
          {items.map((a) => <article className="wf-card" key={a.id}>
            <strong>{a.workflow_title || "Workflow"}</strong>
            <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "6px 0", flexWrap: "wrap" }}>
              <span className={`wf-badge ${a.status === "pending" ? "zip" : ""}`}>{STATUS_LABELS[a.status] || a.status} · Vòng {a.round}</span>
              <small className="muted">{timeLabel(a.created_at)}</small>
            </div>
            <p className="muted" style={{ fontSize: 12.5, maxHeight: 60, overflow: "hidden" }}>
              {(a.summary || "").slice(0, 220)}{a.summary && a.summary.length > 220 ? "…" : ""}
            </p>
            <button className="wf-btn" type="button" onClick={() => { setSelectedId(a.id); setNotice(""); }}>
              {a.status === "pending" ? "Xem & quyết định" : "Xem chi tiết"}</button>
          </article>)}
        </div>

        {selected && <div className="wf-card" style={{ marginTop: 16 }}>
          <h2 style={{ marginTop: 0 }}>{selected.workflow_title}</h2>
          <p className="muted" style={{ fontSize: 12.5 }}>
            Trạng thái: <b>{STATUS_LABELS[selected.status] || selected.status}</b> · Vòng duyệt {selected.round} ·
            Gửi lúc {timeLabel(selected.created_at)}
            {selected.decided_at && <> · Quyết định lúc {timeLabel(selected.decided_at)}</>}
          </p>
          <h3>Kết quả chờ duyệt</h3>
          <div style={{ whiteSpace: "pre-wrap", maxHeight: 420, overflowY: "auto", overflowWrap: "anywhere" }}>
            {selected.summary || "(Không có nội dung kết quả)"}
          </div>
          {selected.status === "pending" ? <>
            <label style={{ display: "block", marginTop: 14 }}>
              <span>Góp ý / lý do (nên ghi khi yêu cầu sửa hoặc từ chối)</span>
              <textarea rows={3} value={comment} maxLength={4000} onChange={(e) => setComment(e.target.value)}
                style={{ display: "block", width: "100%", marginTop: 6 }}
                placeholder="Ví dụ: Thêm bảng giá ở trang chủ, sửa màu nút mua hàng…" />
            </label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
              <button className="wf-btn primary" type="button" disabled={!!busy} onClick={() => decide("approved")}>
                <CheckCircle2 size={15} /> {busy === "approved" ? "Đang duyệt…" : "Duyệt — hoàn thành workflow"}</button>
              <button className="wf-btn" type="button" disabled={!!busy} onClick={() => decide("changes_requested")}>
                <RefreshCw size={15} /> {busy === "changes_requested" ? "Đang gửi…" : "Yêu cầu sửa — chạy lại"}</button>
              <button className="wf-btn danger" type="button" disabled={!!busy} onClick={() => decide("rejected")}>
                <XCircle size={15} /> {busy === "rejected" ? "Đang từ chối…" : "Từ chối — dừng workflow"}</button>
            </div>
          </> : selected.comment && <p style={{ marginTop: 12 }}><b>Góp ý đã ghi:</b> {selected.comment}</p>}
          {notice && <p className="muted" role="status" style={{ marginTop: 10 }}>{notice}</p>}
          <p className="muted" style={{ fontSize: 12.5, marginTop: 12 }}>
            Xem tiến trình đầy đủ ở <Link className="text-link" href="/agents/workflows">Workflows</Link>.
          </p>
        </div>}
      </>}
  </div>;
}
