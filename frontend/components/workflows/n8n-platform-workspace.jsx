"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ExternalLink,
  Loader2,
  Network,
  Power,
  RefreshCw,
  Workflow as WorkflowIcon,
} from "lucide-react";
import {
  getN8nPlatformError,
  getN8nStatusText,
  n8nPlatformService,
} from "../../services/n8n-platform";

const TRIGGER_LABELS = {
  webhook: "Webhook",
  schedule: "Theo lịch",
  form: "Form",
  manual: "Thủ công",
  "sub-workflow": "Workflow con",
};

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN");
}

// Phase 1 of the n8n Platform: connection status + the instance's workflow
// list, mirrored from the n8n REST API by the backend. Editing a workflow
// still happens in n8n itself (the editor is not embedded) — every row and
// the status card link out to it.
export function N8nPlatformWorkspace() {
  const [status, setStatus] = useState(null);
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toggling, setToggling] = useState("");
  const abortRef = useRef(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const [statusData, listData] = await Promise.all([
        n8nPlatformService.getStatus(controller.signal),
        n8nPlatformService.listWorkflows(controller.signal),
      ]);
      setStatus(statusData);
      setListing(listData);
    } catch (err) {
      if (err?.name !== "CanceledError" && err?.name !== "AbortError") {
        setError(getN8nPlatformError(err, "Không tải được thông tin n8n. Hãy thử lại."));
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  async function toggle(workflow) {
    setToggling(workflow.id);
    setError("");
    try {
      const updated = await n8nPlatformService.setActive(workflow.id, !workflow.active);
      setListing((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => (item.id === updated.id ? updated : item)),
            }
          : current,
      );
    } catch (err) {
      setError(getN8nPlatformError(err, "Không đổi được trạng thái workflow. Hãy thử lại."));
    } finally {
      setToggling("");
    }
  }

  const healthy = status?.configured && status?.reachable && status?.authenticated;
  const statusError = status?.error || listing?.sync_error;

  return (
    <div className="fx-page">
      <section className="fx-card">
        <h2>
          <Network size={17} /> Kết nối n8n
          <span className={`n8n-dot${healthy ? " ok" : status ? " bad" : ""}`} aria-hidden="true" />
          <span className="fx-run-meta">
            {loading
              ? "Đang kiểm tra…"
              : healthy
                ? "Đã kết nối"
                : status
                  ? "Chưa kết nối được"
                  : ""}
          </span>
          <span style={{ marginLeft: "auto" }} className="fx-actions">
            <button type="button" className="fx-btn" onClick={load} disabled={loading}>
              {loading ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Làm mới
            </button>
            {status?.editor_url ? (
              <a className="fx-btn" href={status.editor_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> Mở n8n
              </a>
            ) : null}
          </span>
        </h2>
        {status ? (
          <div className="fx-chip-row">
            <span className="fx-chip">Địa chỉ: {status.api_base_url}</span>
            <span className="fx-chip">Số workflow đã đồng bộ: {listing ? listing.total : status.workflow_count}</span>
            <span className="fx-chip">Kiểm tra lúc: {formatTime(status.checked_at)}</span>
            {listing?.synced_at ? (
              <span className="fx-chip">Đồng bộ lúc: {formatTime(listing.synced_at)}</span>
            ) : null}
          </div>
        ) : null}
        {statusError ? (
          <div className="fx-error">{getN8nStatusText(statusError)}</div>
        ) : null}
        {error ? <div className="fx-error">{error}</div> : null}
        <p className="fx-run-meta">
          MindFlow quản lý n8n qua REST API bằng key đặt ở server — key không đi qua trình duyệt.
          Sửa nội dung workflow vẫn làm trong n8n (nút Mở ở từng dòng); tại đây bạn xem trạng thái và bật/tắt workflow.
        </p>
      </section>

      <section className="fx-card">
        <h2>
          <WorkflowIcon size={17} /> Workflow trong n8n
          {listing ? <span className="fx-run-meta">{listing.total} workflow</span> : null}
        </h2>
        {loading && !listing ? (
          <p className="fx-run-meta">
            <Loader2 size={14} className="spin" /> Đang tải danh sách…
          </p>
        ) : listing && listing.items.length === 0 ? (
          <p className="fx-run-meta">
            Chưa có workflow nào. Hãy import các workflow trong thư mục n8n-ai-factory/workflows vào n8n rồi bấm Làm mới.
          </p>
        ) : listing ? (
          <div className="n8n-rows">
            {listing.items.map((workflow) => (
              <div key={workflow.id} className="n8n-row">
                <div className="n8n-row-main">
                  <div className="fx-run-req">{workflow.name}</div>
                  <div className="fx-run-meta">
                    {workflow.node_count} node · Cập nhật: {formatTime(workflow.n8n_updated_at)}
                    {workflow.webhook_paths.length
                      ? ` · Webhook: ${workflow.webhook_paths.map((p) => `/webhook/${p}`).join(", ")}`
                      : ""}
                  </div>
                  <div className="fx-chip-row">
                    {workflow.triggers.map((trigger) => (
                      <span key={trigger} className="fx-chip">
                        {TRIGGER_LABELS[trigger] || trigger}
                      </span>
                    ))}
                    {workflow.tags.map((tag) => (
                      <span key={tag} className="fx-chip">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
                <span className={`fx-status ${workflow.active ? "completed" : "cancelled"}`}>
                  {workflow.active ? "Đang bật" : "Đang tắt"}
                </span>
                <span className="fx-actions">
                  <button
                    type="button"
                    className="fx-btn"
                    onClick={() => toggle(workflow)}
                    disabled={toggling === workflow.id || !healthy}
                    title={healthy ? "" : "Cần kết nối được n8n trước"}
                  >
                    {toggling === workflow.id ? (
                      <Loader2 size={15} className="spin" />
                    ) : (
                      <Power size={15} />
                    )}
                    {workflow.active ? "Tắt" : "Bật"}
                  </button>
                  <a
                    className="fx-btn"
                    href={workflow.editor_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={15} /> Mở
                  </a>
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
