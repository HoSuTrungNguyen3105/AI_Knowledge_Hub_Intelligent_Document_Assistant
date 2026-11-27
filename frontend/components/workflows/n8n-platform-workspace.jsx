"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  FileJson,
  History,
  Loader2,
  Network,
  Plus,
  Power,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  getN8nPlatformError,
  getN8nStatusText,
  getN8nValidateErrorText,
  n8nPlatformService,
} from "../../services/n8n-platform";
import TemplateSources from "./template-sources";
import "./workflow-management.css";

const SAMPLE_WORKFLOW_JSON = `{
  "name": "Workflow mẫu từ MindFlow",
  "nodes": [
    {
      "parameters": { "path": "xin-chao", "httpMethod": "POST" },
      "id": "11111111-1111-4111-8111-111111111111",
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "22222222-2222-4222-8222-222222222222"
    },
    {
      "parameters": { "jsCode": "return [{ json: { message: 'Xin chào từ MindFlow' } }];" },
      "id": "33333333-3333-4333-8333-333333333333",
      "name": "Trả lời",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [260, 0]
    }
  ],
  "connections": {
    "Webhook": { "main": [[{ "node": "Trả lời", "type": "main", "index": 0 }]] }
  },
  "settings": {}
}`;

const TRIGGER_LABELS = {
  webhook: "Webhook",
  schedule: "Theo lịch",
  form: "Form",
  manual: "Thủ công",
  "sub-workflow": "Workflow con",
};

const EXEC_STATUS_TEXT = {
  success: "Thành công",
  error: "Lỗi",
  running: "Đang chạy",
  waiting: "Đang chờ",
  stopped: "Đã dừng",
};

const PAGE_SIZE = 10;

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN");
}

function formatDuration(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} m ${Math.round(seconds % 60)} s`;
}

function downloadJson(filename, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Workflow Management (rebuild of the n8n Platform tab): MindFlow is the
// control center — status, statistics, import/update/export and execution
// monitoring — while node editing stays in n8n itself. Everything goes
// through the MindFlow backend; the n8n API key never reaches the browser.
export function N8nPlatformWorkspace() {
  const [status, setStatus] = useState(null);
  const [listing, setListing] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [toggling, setToggling] = useState("");
  const [exporting, setExporting] = useState("");

  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  const [modal, setModal] = useState(null); // { mode: import|create|update, target }
  const [modalText, setModalText] = useState("");
  const [modalName, setModalName] = useState("");
  const [validation, setValidation] = useState(null);
  const [validatedText, setValidatedText] = useState("");
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState("");

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const [executions, setExecutions] = useState(null);
  const [execLoading, setExecLoading] = useState(false);
  const [execWorkflow, setExecWorkflow] = useState("");
  const [execStatus, setExecStatus] = useState("");
  const [overview, setOverview] = useState([]);
  const [openExecId, setOpenExecId] = useState(null);
  const [execDetails, setExecDetails] = useState({});
  const [execDetailLoading, setExecDetailLoading] = useState("");
  const historyRef = useRef(null);
  const abortRef = useRef(null);

  const healthy = Boolean(status?.configured && status?.reachable && status?.authenticated);
  const statusError = status?.error || listing?.sync_error;

  const loadStats = useCallback(async () => {
    try {
      setStats(await n8nPlatformService.getStats());
    } catch {
      // Statistics are best-effort; the cards show an em dash on failure.
    }
  }, []);

  const loadOverview = useCallback(async () => {
    try {
      const data = await n8nPlatformService.listExecutions({ limit: 100 });
      setOverview(data.items || []);
    } catch {
      // The last-execution column is secondary; keep the old values.
    }
  }, []);

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
      if (controller.signal.aborted) return;
      setStatus(statusData);
      setListing(listData);
      loadStats();
      loadOverview();
    } catch (err) {
      if (err?.name !== "CanceledError" && err?.name !== "AbortError") {
        setError(getN8nPlatformError(err, "Không tải được thông tin n8n. Hãy thử lại."));
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [loadStats, loadOverview]);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  const loadExecutions = useCallback(async () => {
    setExecLoading(true);
    try {
      const data = await n8nPlatformService.listExecutions({
        workflowId: execWorkflow || undefined,
        status: execStatus || undefined,
        limit: 50,
      });
      setExecutions(data);
    } catch (err) {
      setExecutions({
        items: [],
        total: 0,
        error: null,
        loadError: getN8nPlatformError(err, "Không tải được lịch sử chạy."),
      });
    } finally {
      setExecLoading(false);
    }
  }, [execWorkflow, execStatus]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  const hasLiveExec = (executions?.items || []).some(
    (item) => item.status === "running" || item.status === "waiting",
  );
  useEffect(() => {
    if (!hasLiveExec) return undefined;
    const timer = setInterval(() => {
      loadExecutions();
      loadOverview();
    }, 5000);
    return () => clearInterval(timer);
  }, [hasLiveExec, loadExecutions, loadOverview]);

  const lastExecByWorkflow = useMemo(() => {
    const map = {};
    for (const item of overview) {
      if (!map[item.workflow_id]) map[item.workflow_id] = item;
    }
    return map;
  }, [overview]);

  const filtered = useMemo(() => {
    const items = listing?.items || [];
    const needle = search.trim().toLowerCase();
    return items.filter((workflow) => {
      if (activeFilter === "active" && !workflow.active) return false;
      if (activeFilter === "inactive" && workflow.active) return false;
      if (needle && !workflow.name.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [listing, search, activeFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

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
      loadStats();
    } catch (err) {
      setError(getN8nPlatformError(err, "Không đổi được trạng thái workflow. Hãy thử lại."));
    } finally {
      setToggling("");
    }
  }

  async function openDetail(workflow) {
    setDetailLoading(true);
    setError("");
    setShowRaw(false);
    try {
      const [detailData, exportData] = await Promise.all([
        n8nPlatformService.getWorkflow(workflow.id),
        n8nPlatformService.exportWorkflow(workflow.id),
      ]);
      setDetail({ summary: workflow, detail: detailData, raw: exportData.workflow });
    } catch (err) {
      setError(getN8nPlatformError(err, "Không tải được chi tiết workflow. Hãy thử lại."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function exportWorkflowFile(workflow) {
    setExporting(workflow.id);
    setError("");
    try {
      const data = await n8nPlatformService.exportWorkflow(workflow.id);
      const safeName = (data.name || workflow.name || workflow.id).replace(/[\\/:*?"<>|]/g, "_");
      downloadJson(`${safeName}.json`, data.workflow);
      setNotice(`Đã xuất JSON của "${data.name || workflow.name}" (bản mới nhất từ n8n).`);
    } catch (err) {
      setError(getN8nPlatformError(err, "Không xuất được JSON. Hãy thử lại."));
    } finally {
      setExporting("");
    }
  }

  async function doDelete() {
    if (!confirmDelete) return;
    setDeleting(true);
    setError("");
    try {
      await n8nPlatformService.deleteWorkflow(confirmDelete.id);
      setNotice(`Đã xóa workflow "${confirmDelete.name}" khỏi n8n.`);
      if (detail?.summary.id === confirmDelete.id) setDetail(null);
      setConfirmDelete(null);
      load();
      loadExecutions();
    } catch (err) {
      setError(getN8nPlatformError(err, "Không xóa được workflow. Hãy thử lại."));
      setConfirmDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  function openModal(mode, target = null) {
    setModal({ mode, target });
    setModalText(mode === "create" ? SAMPLE_WORKFLOW_JSON : "");
    setModalName("");
    setValidation(null);
    setValidatedText("");
    setModalError("");
  }

  function closeModal() {
    if (validating || submitting) return;
    setModal(null);
  }

  function onModalTextChange(value) {
    setModalText(value);
    setValidation(null);
    setModalError("");
  }

  function onModalFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onModalTextChange(String(reader.result || ""));
    reader.onerror = () => setModalError("Không đọc được file. Hãy thử dán JSON trực tiếp.");
    reader.readAsText(file);
  }

  function parseModalJson() {
    let parsed;
    try {
      parsed = JSON.parse(modalText);
    } catch (err) {
      setModalError(`JSON không hợp lệ: ${err.message}. Nội dung bạn nhập vẫn được giữ nguyên.`);
      return null;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setModalError("JSON phải là một object workflow của n8n.");
      return null;
    }
    return parsed;
  }

  async function validateModal() {
    const parsed = parseModalJson();
    if (!parsed) return;
    setValidating(true);
    setModalError("");
    try {
      const result = await n8nPlatformService.validateWorkflow(parsed);
      setValidation(result);
      setValidatedText(modalText);
    } catch (err) {
      setModalError(getN8nPlatformError(err, "Không kiểm tra được JSON. Hãy thử lại."));
    } finally {
      setValidating(false);
    }
  }

  async function submitModal() {
    if (!modal || !validation?.valid || modalText !== validatedText) return;
    const parsed = parseModalJson();
    if (!parsed) return;
    const payload = {
      name: (modal.mode === "import" && modalName.trim()) || parsed.name,
      nodes: parsed.nodes,
      connections: parsed.connections || {},
      settings: parsed.settings || {},
    };
    setSubmitting(true);
    setModalError("");
    try {
      if (modal.mode === "update") {
        const updated = await n8nPlatformService.updateWorkflow(modal.target.id, payload);
        setNotice(`Đã cập nhật workflow "${updated.name}" từ JSON mới.`);
      } else {
        const created = await n8nPlatformService.createWorkflow(payload);
        setNotice(
          `Đã tạo workflow "${created.name}" trong n8n (đang tắt — gắn credential và Publish trong n8n khi sẵn sàng).`,
        );
      }
      setModal(null);
      load();
    } catch (err) {
      setModalError(getN8nPlatformError(err, "Thao tác chưa xong. JSON của bạn vẫn được giữ nguyên — hãy kiểm tra rồi thử lại."));
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleExecDetail(item) {
    if (openExecId === item.id) {
      setOpenExecId(null);
      return;
    }
    setOpenExecId(item.id);
    if (execDetails[item.id]) return;
    setExecDetailLoading(item.id);
    try {
      const data = await n8nPlatformService.getExecution(item.id);
      setExecDetails((current) => ({ ...current, [item.id]: data }));
    } catch (err) {
      setExecDetails((current) => ({
        ...current,
        [item.id]: { loadError: getN8nPlatformError(err, "Không tải được chi tiết execution.") },
      }));
    } finally {
      setExecDetailLoading("");
    }
  }

  function viewExecutionsOf(workflow) {
    setExecWorkflow(workflow.id);
    setExecStatus("");
    setOpenExecId(null);
    historyRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const connectionText = !status
    ? "Đang kiểm tra…"
    : healthy
      ? "Connected"
      : !status.configured
        ? "Disconnected — chưa cấu hình"
        : !status.reachable
          ? "Disconnected"
          : "Connection Error";

  return (
    <div className="fx-page">
      <section className="fx-card">
        <h2>
          <Network size={17} /> Workflow Management
          <span className={`n8n-dot${healthy ? " ok" : status ? " bad" : ""}`} aria-hidden="true" />
          <span className="fx-run-meta">{loading ? "Đang kiểm tra…" : connectionText}</span>
          <span style={{ marginLeft: "auto" }} className="fx-actions">
            <button type="button" className="fx-btn" onClick={load} disabled={loading}>
              {loading ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Refresh
              Connection
            </button>
            <button
              type="button"
              className="fx-btn"
              onClick={() => openModal("import")}
              disabled={!healthy}
              title={healthy ? "" : "Cần kết nối được n8n trước"}
            >
              <Upload size={15} /> Import Workflow
            </button>
            <button
              type="button"
              className="fx-btn primary"
              onClick={() => openModal("create")}
              disabled={!healthy}
              title={healthy ? "" : "Cần kết nối được n8n trước"}
            >
              <Plus size={15} /> Create Workflow
            </button>
          </span>
        </h2>
        <p className="fx-run-meta">
          Quản lý, đồng bộ và giám sát các quy trình tự động hóa thông qua n8n. MindFlow là trung
          tâm quản lý; thiết kế node, nối dây và credential làm trực tiếp trong n8n. Mọi thao tác đi
          qua backend — API key của n8n không bao giờ xuống trình duyệt.
        </p>
        {status ? (
          <div className="fx-chip-row">
            <span className="fx-chip">Địa chỉ: {status.api_base_url}</span>
            <span className="fx-chip">
              Số workflow đã đồng bộ: {listing ? listing.total : status.workflow_count}
            </span>
            <span className="fx-chip">Kiểm tra lúc: {formatTime(status.checked_at)}</span>
            {listing?.synced_at ? (
              <span className="fx-chip">Đồng bộ lúc: {formatTime(listing.synced_at)}</span>
            ) : null}
            {status.editor_url ? (
              <a className="fx-chip" href={status.editor_url} target="_blank" rel="noreferrer">
                Mở n8n <ExternalLink size={12} />
              </a>
            ) : null}
          </div>
        ) : null}
        {statusError ? <div className="fx-error">{getN8nStatusText(statusError)}</div> : null}
        {error ? <div className="fx-error">{error}</div> : null}
        {notice ? (
          <p className="fx-run-meta">
            <CheckCircle2 size={14} /> {notice}
          </p>
        ) : null}
      </section>

      <section className="wm-stats" aria-label="Thống kê workflow">
        <div className="wm-stat">
          <span className="wm-stat-value">{stats ? stats.total_workflows : "—"}</span>
          <span className="wm-stat-label">Total Workflows</span>
        </div>
        <div className="wm-stat">
          <span className="wm-stat-value">{stats ? stats.active_workflows : "—"}</span>
          <span className="wm-stat-label">Active Workflows</span>
        </div>
        <div className="wm-stat">
          <span className="wm-stat-value">{stats ? stats.inactive_workflows : "—"}</span>
          <span className="wm-stat-label">Inactive Workflows</span>
        </div>
        <div className="wm-stat">
          <span className="wm-stat-value">
            {stats?.executions_today != null ? stats.executions_today : "—"}
          </span>
          <span className="wm-stat-label">Executions Today</span>
        </div>
        <div className="wm-stat">
          <span className="wm-stat-value">
            {stats?.failed_executions_today != null ? stats.failed_executions_today : "—"}
          </span>
          <span className="wm-stat-label">Failed Executions</span>
        </div>
      </section>
      {stats?.executions_error ? (
        <p className="fx-run-meta">
          <AlertTriangle size={14} /> Chưa đọc được số lần chạy từ n8n:{" "}
          {getN8nStatusText(stats.executions_error)} Số workflow ở trên vẫn là số thật từ bản đồng
          bộ.
        </p>
      ) : stats?.executions_truncated ? (
        <p className="fx-run-meta">
          Số lần chạy hôm nay rất nhiều — số hiển thị là mức tối thiểu đã đếm được.
        </p>
      ) : null}

      <section className="fx-card">
        <h2>
          <FileJson size={17} /> Danh sách workflow
          {listing ? <span className="fx-run-meta">{filtered.length} workflow</span> : null}
        </h2>
        <div className="wm-filters">
          <label className="wm-search">
            <Search size={15} />
            <input
              className="fx-input"
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Tìm theo tên workflow…"
            />
          </label>
          <select
            className="fx-input"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value);
              setPage(1);
            }}
            aria-label="Lọc theo trạng thái"
          >
            <option value="all">Tất cả trạng thái</option>
            <option value="active">Đang bật</option>
            <option value="inactive">Đang tắt</option>
          </select>
        </div>
        {loading && !listing ? (
          <p className="fx-run-meta">
            <Loader2 size={14} className="spin" /> Đang tải danh sách…
          </p>
        ) : listing && filtered.length === 0 ? (
          <p className="fx-run-meta">
            {listing.items.length === 0
              ? "Chưa có workflow nào trong n8n. Hãy Import Workflow hoặc Create Workflow để bắt đầu."
              : "Không có workflow nào khớp bộ lọc. Hãy đổi từ khóa hoặc trạng thái."}
          </p>
        ) : listing ? (
          <>
            <div className="n8n-rows">
              {pageItems.map((workflow) => {
                const lastExec = lastExecByWorkflow[workflow.id];
                return (
                  <div key={workflow.id} className="n8n-row">
                    <div className="n8n-row-main">
                      <div className="fx-run-req">{workflow.name}</div>
                      <div className="fx-run-meta">
                        ID: {workflow.id} · {workflow.node_count} node · Cập nhật:{" "}
                        {formatTime(workflow.n8n_updated_at)}
                        {workflow.webhook_paths.length
                          ? ` · Webhook: ${workflow.webhook_paths.map((p) => `/webhook/${p}`).join(", ")}`
                          : ""}
                      </div>
                      <div className="fx-run-meta">
                        Lần chạy gần nhất:{" "}
                        {lastExec
                          ? `${EXEC_STATUS_TEXT[lastExec.status] || lastExec.status} · ${formatTime(lastExec.started_at)}`
                          : "chưa có dữ liệu"}
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
                    <span className="fx-actions wm-row-actions">
                      <button
                        type="button"
                        className="fx-btn"
                        onClick={() => openDetail(workflow)}
                        disabled={!healthy || detailLoading}
                      >
                        <Eye size={15} /> Chi tiết
                      </button>
                      <a
                        className="fx-btn"
                        href={workflow.editor_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={15} /> Open in n8n
                      </a>
                      <button
                        type="button"
                        className="fx-btn"
                        onClick={() => openModal("update", workflow)}
                        disabled={!healthy}
                        title={healthy ? "" : "Cần kết nối được n8n trước"}
                      >
                        <Upload size={15} /> Update JSON
                      </button>
                      <button
                        type="button"
                        className="fx-btn"
                        onClick={() => exportWorkflowFile(workflow)}
                        disabled={!healthy || exporting === workflow.id}
                      >
                        {exporting === workflow.id ? (
                          <Loader2 size={15} className="spin" />
                        ) : (
                          <Download size={15} />
                        )}{" "}
                        Export
                      </button>
                      <button
                        type="button"
                        className="fx-btn"
                        onClick={() => viewExecutionsOf(workflow)}
                      >
                        <History size={15} /> Executions
                      </button>
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
                      <button
                        type="button"
                        className="fx-btn danger"
                        onClick={() => setConfirmDelete(workflow)}
                        disabled={!healthy}
                        title={healthy ? "" : "Cần kết nối được n8n trước"}
                      >
                        <Trash2 size={15} /> Xóa
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
            {pageCount > 1 ? (
              <div className="wm-pager">
                <button
                  type="button"
                  className="fx-btn"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft size={15} /> Trước
                </button>
                <span className="fx-run-meta">
                  Trang {page}/{pageCount}
                </span>
                <button
                  type="button"
                  className="fx-btn"
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  disabled={page >= pageCount}
                >
                  Sau <ChevronRight size={15} />
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      {detail ? (
        <section className="fx-card">
          <h2>
            <Eye size={17} /> Chi tiết — {detail.detail.name}
            <span style={{ marginLeft: "auto" }} className="fx-actions">
              <a
                className="fx-btn"
                href={detail.detail.editor_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={15} /> Open in n8n
              </a>
              <button
                type="button"
                className="fx-btn"
                onClick={() =>
                  downloadJson(
                    `${(detail.detail.name || detail.summary.id).replace(/[\\/:*?"<>|]/g, "_")}.json`,
                    detail.raw,
                  )
                }
              >
                <Download size={15} /> Tải JSON
              </button>
              <button type="button" className="fx-btn" onClick={() => setDetail(null)}>
                <X size={15} /> Đóng
              </button>
            </span>
          </h2>
          <p className="fx-run-meta">
            ID: {detail.summary.id} · {detail.detail.active ? "Đang bật" : "Đang tắt"} ·{" "}
            {detail.detail.nodes.length} node. Chi tiết chỉ để xem — sửa node, nối dây và credential
            làm trong n8n.
          </p>
          <div className="n8n-rows">
            {detail.detail.nodes.map((node) => (
              <div key={node.name} className="n8n-row">
                <div className="n8n-row-main">
                  <div className="fx-run-req">{node.name || "(node chưa đặt tên)"}</div>
                  <div className="fx-run-meta">{node.type}</div>
                </div>
                <span className="fx-run-meta">{node.parameters.length} tham số</span>
              </div>
            ))}
          </div>
          <div className="fx-actions" style={{ marginTop: 10 }}>
            <button type="button" className="fx-btn" onClick={() => setShowRaw((v) => !v)}>
              <FileJson size={15} /> {showRaw ? "Ẩn JSON" : "Xem JSON đầy đủ"}
            </button>
          </div>
          {showRaw ? (
            <pre className="tpl-json wm-json">{JSON.stringify(detail.raw, null, 2)}</pre>
          ) : null}
        </section>
      ) : null}

      <section className="fx-card" ref={historyRef}>
        <h2>
          <History size={17} /> Lịch sử chạy (Execution History)
          <span style={{ marginLeft: "auto" }}>
            <button type="button" className="fx-btn" onClick={loadExecutions} disabled={execLoading}>
              {execLoading ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Làm
              mới
            </button>
          </span>
        </h2>
        <div className="wm-filters">
          <select
            className="fx-input"
            value={execWorkflow}
            onChange={(event) => setExecWorkflow(event.target.value)}
            aria-label="Lọc theo workflow"
          >
            <option value="">Tất cả workflow</option>
            {(listing?.items || []).map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
          <select
            className="fx-input"
            value={execStatus}
            onChange={(event) => setExecStatus(event.target.value)}
            aria-label="Lọc theo trạng thái chạy"
          >
            <option value="">Tất cả trạng thái</option>
            <option value="success">Thành công</option>
            <option value="error">Lỗi</option>
            <option value="running">Đang chạy</option>
            <option value="waiting">Đang chờ</option>
            <option value="stopped">Đã dừng</option>
          </select>
        </div>
        {executions?.loadError ? (
          <div className="fx-error">{executions.loadError}</div>
        ) : executions?.error ? (
          <div className="fx-error">{getN8nStatusText(executions.error)}</div>
        ) : null}
        {execLoading && !executions ? (
          <p className="fx-run-meta">
            <Loader2 size={14} className="spin" /> Đang tải lịch sử chạy…
          </p>
        ) : executions && executions.items.length === 0 ? (
          <p className="fx-run-meta">
            Chưa có execution nào khớp bộ lọc. Lịch sử lấy trực tiếp từ n8n — khi n8n chưa kết nối
            được, khu vực này để trống thay vì hiện số liệu giả.
          </p>
        ) : executions ? (
          <div className="n8n-rows">
            {executions.items.map((item) => {
              const detailData = execDetails[item.id];
              return (
                <div key={item.id} className="n8n-row">
                  <div className="n8n-row-main">
                    <div className="fx-run-req">
                      <span className={`n8n-run-status ${item.status}`}>
                        {EXEC_STATUS_TEXT[item.status] || item.status}
                      </span>{" "}
                      {item.workflow_name}
                    </div>
                    <div className="fx-run-meta">
                      Execution #{item.id}
                      {item.mode ? ` · ${item.mode}` : ""} · Bắt đầu {formatTime(item.started_at)}{" "}
                      · Thời lượng {formatDuration(item.duration_ms)}
                      {item.error ? ` · Lỗi: ${item.error}` : ""}
                    </div>
                    {openExecId === item.id ? (
                      execDetailLoading === item.id ? (
                        <p className="fx-run-meta">
                          <Loader2 size={14} className="spin" /> Đang tải chi tiết…
                        </p>
                      ) : detailData?.loadError ? (
                        <div className="fx-error">{detailData.loadError}</div>
                      ) : detailData ? (
                        <>
                          {detailData.error ? (
                            <div className="fx-error">Lỗi: {detailData.error}</div>
                          ) : null}
                          {detailData.node_statuses?.length ? (
                            <ul className="n8n-node-list">
                              {detailData.node_statuses.map((node) => (
                                <li key={node.name}>
                                  <span className={`n8n-run-status ${node.status}`}>
                                    {node.status === "success"
                                      ? "Xong"
                                      : node.status === "error"
                                        ? "Lỗi"
                                        : "Chờ"}
                                  </span>{" "}
                                  <strong>{node.name}</strong>
                                  {node.duration_ms != null ? ` · ${node.duration_ms} ms` : ""}
                                  {node.error ? ` · ${node.error}` : ""}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="fx-run-meta">
                              Execution này không có dữ liệu theo node.
                            </p>
                          )}
                        </>
                      ) : null
                    ) : null}
                  </div>
                  <span className="fx-actions">
                    <button
                      type="button"
                      className="fx-btn"
                      onClick={() => toggleExecDetail(item)}
                    >
                      {openExecId === item.id ? "Thu gọn" : "Chi tiết"}
                    </button>
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}
      </section>

      <TemplateSources />

      {modal ? (
        <div className="wm-modal-backdrop" role="presentation" onClick={closeModal}>
          <div
            className="wm-modal"
            role="dialog"
            aria-modal="true"
            aria-label={
              modal.mode === "update"
                ? "Cập nhật workflow từ JSON"
                : modal.mode === "create"
                  ? "Tạo workflow mới"
                  : "Import workflow"
            }
            onClick={(event) => event.stopPropagation()}
          >
            <h2>
              {modal.mode === "update" ? (
                <>
                  <Upload size={17} /> Update JSON — {modal.target.name}
                </>
              ) : modal.mode === "create" ? (
                <>
                  <Plus size={17} /> Create Workflow
                </>
              ) : (
                <>
                  <Upload size={17} /> Import Workflow
                </>
              )}
              <span style={{ marginLeft: "auto" }}>
                <button type="button" className="fx-btn" onClick={closeModal}>
                  <X size={15} /> Đóng
                </button>
              </span>
            </h2>
            {modal.mode === "update" ? (
              <p className="fx-run-meta">
                JSON mới sẽ thay toàn bộ định nghĩa của workflow <strong>{modal.target.name}</strong>{" "}
                (ID: {modal.target.id}, hiện có {modal.target.node_count} node). Cập nhật ghi đúng
                workflow này — không tạo workflow mới, và nếu n8n báo lỗi thì workflow cũ vẫn nguyên
                vẹn.
              </p>
            ) : (
              <p className="fx-run-meta">
                Dán JSON export từ n8n hoặc tải file .json lên. Hệ thống kiểm tra cấu trúc và cho xem
                trước — chỉ khi bạn xác nhận mới tạo workflow trong n8n (ở trạng thái tắt). Đừng dán
                key thật vào JSON; credential trong n8n được tham chiếu bằng id.
              </p>
            )}
            {modal.mode === "import" ? (
              <label className="fx-field">
                Tên workflow (tùy chọn — để trống sẽ lấy tên trong JSON)
                <input
                  className="fx-input"
                  type="text"
                  value={modalName}
                  onChange={(event) => setModalName(event.target.value)}
                  maxLength={200}
                />
              </label>
            ) : null}
            <div className="fx-actions">
              <label className="fx-btn wm-file-btn">
                <Upload size={15} /> Tải file .json
                <input type="file" accept=".json,application/json" onChange={onModalFile} hidden />
              </label>
            </div>
            <textarea
              className="fx-textarea n8n-json"
              rows={12}
              value={modalText}
              onChange={(event) => onModalTextChange(event.target.value)}
              placeholder="Dán JSON workflow tại đây…"
              spellCheck={false}
            />
            {modalError ? <div className="fx-error">{modalError}</div> : null}
            {validation ? (
              validation.valid ? (
                <div className="wm-preview">
                  <p className="fx-run-meta">
                    <CheckCircle2 size={14} /> JSON hợp lệ — xem trước trước khi xác nhận:
                  </p>
                  <div className="fx-chip-row">
                    <span className="fx-chip">Tên: {validation.name || "—"}</span>
                    <span className="fx-chip">{validation.node_count} node</span>
                    {validation.triggers.map((trigger) => (
                      <span key={trigger} className="fx-chip">
                        {TRIGGER_LABELS[trigger] || trigger}
                      </span>
                    ))}
                    {validation.webhook_paths.map((path) => (
                      <span key={path} className="fx-chip">
                        /webhook/{path}
                      </span>
                    ))}
                  </div>
                  <p className="fx-run-meta">
                    Loại node: {validation.node_types.join(", ") || "—"}
                  </p>
                </div>
              ) : (
                <div className="fx-error">
                  JSON chưa hợp lệ:
                  <ul>
                    {validation.errors.map((code) => (
                      <li key={code}>{getN8nValidateErrorText(code)}</li>
                    ))}
                  </ul>
                </div>
              )
            ) : null}
            <div className="fx-actions">
              <button type="button" className="fx-btn" onClick={closeModal} disabled={submitting}>
                Cancel
              </button>
              <button
                type="button"
                className="fx-btn"
                onClick={validateModal}
                disabled={validating || submitting || !modalText.trim()}
              >
                {validating ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />}{" "}
                Validate JSON
              </button>
              <button
                type="button"
                className="fx-btn primary"
                onClick={submitModal}
                disabled={
                  submitting || !validation?.valid || modalText !== validatedText
                }
                title={
                  validation?.valid && modalText !== validatedText
                    ? "JSON đã thay đổi sau khi kiểm tra — hãy Validate lại"
                    : ""
                }
              >
                {submitting ? <Loader2 size={15} className="spin" /> : <Upload size={15} />}{" "}
                {modal.mode === "update" ? "Xác nhận cập nhật" : "Xác nhận Import"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {confirmDelete ? (
        <div className="wm-modal-backdrop" role="presentation" onClick={() => !deleting && setConfirmDelete(null)}>
          <div
            className="wm-modal wm-modal-sm"
            role="alertdialog"
            aria-modal="true"
            aria-label="Xác nhận xóa workflow"
            onClick={(event) => event.stopPropagation()}
          >
            <h2>
              <AlertTriangle size={17} /> Xóa workflow?
            </h2>
            <p className="fx-run-meta">
              Workflow <strong>{confirmDelete.name}</strong> (ID: {confirmDelete.id}) sẽ bị xóa khỏi
              n8n cùng toàn bộ lịch sử cấu hình của nó trong MindFlow. Thao tác này không hoàn tác
              được — hãy Export JSON trước nếu cần sao lưu.
            </p>
            <div className="fx-actions">
              <button
                type="button"
                className="fx-btn"
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
              >
                Hủy
              </button>
              <button
                type="button"
                className="fx-btn danger"
                onClick={doDelete}
                disabled={deleting}
              >
                {deleting ? <Loader2 size={15} className="spin" /> : <Trash2 size={15} />} Xóa hẳn
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
