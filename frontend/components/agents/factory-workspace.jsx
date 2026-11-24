"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bot, Factory, History, Play, RotateCcw } from "lucide-react";
import { agentsService } from "../../services/agents";
import { getFactoryError, getRunErrorText, n8nFactoryService } from "../../services/n8n-factory";

// The seven roles of the n8n workflow 07 team. `hint` auto-matches the
// user's existing agents by name (e.g. an agent named "AI Leader" is
// preselected for the AI Leader role); the user can reassign any role to
// any of their agents, or leave a role unassigned (n8n then routes a model
// from its own registry).
const ROLES = [
  { role: "AI Leader", hint: "leader" },
  { role: "AI Planner", hint: "planner" },
  { role: "AI Architect", hint: "architect" },
  { role: "AI Developer", hint: "developer" },
  { role: "AI Tester", hint: "tester" },
  { role: "AI Reviewer", hint: "reviewer" },
  { role: "AI Researcher", hint: "researcher" },
];

const STATUS_LABEL = {
  queued: "Đang chờ",
  running: "Đang chạy",
  completed: "Hoàn thành",
  completed_with_issues: "Hoàn thành, còn vấn đề",
  needs_configuration: "Cần cấu hình thêm",
  failed: "Thất bại",
  needs_human_input: "Cần người xử lý",
};

const ACTIVE_STATUSES = ["queued", "running"];

function deliverableText(item) {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    if (typeof item.title === "string") return item.title;
    if (typeof item.name === "string") return item.name;
    if (typeof item.path === "string") return item.path;
    return JSON.stringify(item);
  }
  return String(item);
}

function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("vi-VN");
}

function RunResult({ run }) {
  const result = run.result;
  if (!result) return null;
  return <>
    {Array.isArray(result.agent_assignments) && result.agent_assignments.length > 0 && <>
      <h3>Agent MindFlow đã chạy</h3>
      <div className="fx-chip-row">{result.agent_assignments.map((a, i) => (
        <span key={i} className="fx-chip">{a.role}: <b>{a.agent_name}</b> · {a.provider} · {a.model}</span>
      ))}</div>
    </>}
    {Array.isArray(result.agent_assignments_ignored) && result.agent_assignments_ignored.length > 0 && <>
      <h3>Không áp dụng được</h3>
      <ul className="fx-list">{result.agent_assignments_ignored.map((a, i) => (
        <li key={i}>{a.role} ({a.agent_name}): {a.reason}</li>
      ))}</ul>
    </>}

    {result.plan?.project_summary && <>
      <h3>Kế hoạch của đội</h3>
      <p className="fx-final">{result.plan.project_summary}</p>
    </>}

    {result.final?.summary && <>
      <h3>Tổng hợp cuối</h3>
      <p className="fx-final">{result.final.summary}</p>
      {Array.isArray(result.final.deliverables) && result.final.deliverables.length > 0 && (
        <ul className="fx-list">{result.final.deliverables.map((d, i) => <li key={i}>{deliverableText(d)}</li>)}</ul>
      )}
    </>}

    {Array.isArray(result.task_results) && result.task_results.length > 0 && <>
      <h3>Từng nhiệm vụ</h3>
      <div className="fx-tasks">{result.task_results.map((t, i) => (
        <div key={i} className="fx-task">
          <div className="fx-task-head">
            <b>{t.role}</b>
            <span className="muted">{t.provider} · {t.model_id}</span>
            <span className={`fx-badge ${t.status}`}>{STATUS_LABEL[t.status] || t.status}</span>
          </div>
          {t.summary && <p>{t.summary}</p>}
          {Array.isArray(t.deliverables) && t.deliverables.length > 0 && (
            <ul className="fx-list">{t.deliverables.map((d, j) => <li key={j}>{deliverableText(d)}</li>)}</ul>
          )}
        </div>
      ))}</div>
    </>}

    {Array.isArray(result.skipped_roles) && result.skipped_roles.length > 0 && <>
      <h3>Vai trò không cần dùng</h3>
      <ul className="fx-list">{result.skipped_roles.map((s, i) => <li key={i}>{s.role}: {s.reason}</li>)}</ul>
    </>}

    {result.review && <>
      <h3>Đánh giá cuối (Reviewer)</h3>
      <p>Trạng thái: <b>{result.review.status}</b>{typeof result.review.score === "number" ? ` · Điểm: ${result.review.score}/100` : ""}</p>
      {Array.isArray(result.review.issues) && result.review.issues.length > 0 && (
        <ul className="fx-list">{result.review.issues.map((s, i) => <li key={i}>{deliverableText(s)}</li>)}</ul>
      )}
    </>}
  </>;
}

export function FactoryWorkspace() {
  const [agents, setAgents] = useState([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState("");
  const [assignments, setAssignments] = useState({});
  const [requirement, setRequirement] = useState("");
  const [domainText, setDomainText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [tick, setTick] = useState(0);

  const loadAgents = useCallback(async (signal) => {
    try {
      const list = await agentsService.list(signal);
      setAgents(list);
      setAgentsError("");
      setAssignments((prev) => {
        if (Object.keys(prev).length) return prev;
        const next = {};
        for (const { role, hint } of ROLES) {
          const match = list.find((a) => a.name.toLowerCase().includes(hint));
          if (match) next[role] = match.id;
        }
        return next;
      });
    } catch (e) {
      if (e?.name !== "AbortError") setAgentsError(getFactoryError(e, "Không tải được danh sách Agent."));
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  const loadRuns = useCallback(async (signal) => {
    try {
      const data = await n8nFactoryService.listRuns(signal);
      setRuns(data.items || []);
      setSelectedId((prev) => prev || (data.items?.[0]?.id ?? null));
    } catch (e) {
      if (e?.name !== "AbortError") setError(getFactoryError(e, "Không tải được danh sách lượt chạy."));
    } finally {
      setRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => { await Promise.all([loadAgents(controller.signal), loadRuns(controller.signal)]); })();
    return () => controller.abort();
  }, [loadAgents, loadRuns]);

  const selected = runs.find((r) => r.id === selectedId) || null;
  const selectedActive = selected ? ACTIVE_STATUSES.includes(selected.status) : false;

  // Poll the selected run while n8n is still working on it; the run
  // completes through the callback, so polling only reads our own backend.
  useEffect(() => {
    if (!selectedId || !selectedActive) return undefined;
    const poll = setInterval(async () => {
      try {
        const fresh = await n8nFactoryService.getRun(selectedId);
        setRuns((prev) => prev.map((r) => (r.id === fresh.id ? fresh : r)));
      } catch { /* transient: the next poll retries */ }
    }, 4000);
    const ticker = setInterval(() => setTick((t) => t + 1), 1000);
    return () => { clearInterval(poll); clearInterval(ticker); };
  }, [selectedId, selectedActive]);

  async function submit(event) {
    event.preventDefault();
    if (!requirement.trim()) { setError("Hãy nhập yêu cầu cho đội Agent."); return; }
    const chosen = {};
    for (const { role } of ROLES) {
      if (assignments[role]) chosen[role] = assignments[role];
    }
    const domain = domainText.split(",").map((s) => s.trim()).filter(Boolean);
    setSubmitting(true); setError("");
    try {
      const run = await n8nFactoryService.createRun({
        requirement: requirement.trim(),
        domain,
        assignments: chosen,
      });
      setRuns((prev) => [run, ...prev]);
      setSelectedId(run.id);
    } catch (e) {
      setError(getFactoryError(e, "Không gửi được lượt chạy sang n8n."));
      await loadRuns();
    } finally {
      setSubmitting(false);
    }
  }

  const agentById = (id) => agents.find((a) => a.id === id);
  const elapsedSeconds = selectedActive && selected
    ? Math.max(0, Math.floor((Date.now() - new Date(selected.created_at).getTime()) / 1000))
    : 0;
  void tick;

  return <div className="fx-page">
    <div className="fx-header"><div>
      <h1><Factory size={26} /> AI Factory</h1>
      <p className="muted">Chạy đội 7 Agent trên n8n (Docker, localhost:5678) bằng chính các Agent bạn đã tạo trong MindFlow — provider, model và system prompt của từng Agent được gửi kèm sang n8n, không tạo đội Agent riêng. Lượt chạy là bất đồng bộ: gửi xong bạn có thể rời trang, n8n chạy nền và báo kết quả về đây.</p>
    </div></div>

    {agentsError && <p className="fx-error" role="alert">{agentsError}</p>}
    {error && <p className="fx-error" role="alert">{error}</p>}

    <form className="fx-card" onSubmit={submit}>
      <h2><Bot size={18} /> Gán Agent của bạn cho từng vai trò</h2>
      {agentsLoading ? <p className="muted">Đang tải danh sách Agent…</p>
        : agents.length === 0 ? <p className="muted">Bạn chưa có Agent nào. Hãy <Link href="/agents">tạo Agent ở Agent Studio</Link> trước, rồi quay lại đây để gán vai trò.</p>
        : <div className="fx-roles">{ROLES.map(({ role }) => {
          const picked = agentById(assignments[role]);
          return <label key={role} className="fx-role-row">
            <span className="fx-role-name">{role}</span>
            <select
              className="fx-select"
              value={assignments[role] || ""}
              onChange={(e) => setAssignments((prev) => ({ ...prev, [role]: e.target.value }))}
              disabled={submitting}
            >
              <option value="">— Để n8n tự chọn model —</option>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <span className="fx-role-meta">{picked ? `${picked.provider} · ${picked.model}` : "registry của n8n"}</span>
          </label>;
        })}</div>}

      <label className="fx-field"><span>Yêu cầu cho đội Agent</span>
        <textarea
          className="fx-textarea"
          rows={5}
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
          placeholder="Ví dụ: Xây dựng website bán giày sneaker bằng React + Vite + Tailwind: trang chủ, danh sách 12 sản phẩm, giỏ hàng lưu localStorage…"
          disabled={submitting}
        />
      </label>
      <label className="fx-field"><span>Lĩnh vực (tuỳ chọn, cách nhau bằng dấu phẩy)</span>
        <input
          className="fx-input"
          value={domainText}
          onChange={(e) => setDomainText(e.target.value)}
          placeholder="software, education…"
          disabled={submitting}
        />
      </label>
      <div className="fx-actions">
        <button type="submit" className="fx-btn primary" disabled={submitting || agentsLoading}>
          <Play size={16} /> {submitting ? "Đang gửi…" : "Chạy đội Agent qua n8n"}
        </button>
        <span className="muted">Gửi xong là chạy nền trên n8n — không cần giữ trang mở.</span>
      </div>
    </form>

    <div className="fx-card">
      <h2><History size={18} /> Các lượt chạy</h2>
      {runsLoading ? <p className="muted">Đang tải…</p>
        : runs.length === 0 ? <p className="muted">Chưa có lượt chạy nào. Gửi yêu cầu đầu tiên ở biểu mẫu phía trên.</p>
        : <div className="fx-runs">{runs.map((run) => (
          <button
            key={run.id}
            type="button"
            className={`fx-run-row${run.id === selectedId ? " active" : ""}`}
            onClick={() => setSelectedId(run.id)}
          >
            <span className="fx-run-req">{run.requirement}</span>
            <span className="fx-run-meta">{formatTime(run.created_at)}</span>
            <span className={`fx-status ${run.status}`}>{STATUS_LABEL[run.status] || run.status}</span>
          </button>
        ))}</div>}
    </div>

    {selected && <div className="fx-card">
      <h2><RotateCcw size={18} /> Chi tiết lượt chạy
        <span className={`fx-status ${selected.status}`}>{STATUS_LABEL[selected.status] || selected.status}</span>
        {typeof selected.duration_ms === "number" && <span className="muted">{Math.round(selected.duration_ms / 1000)}s</span>}
      </h2>
      <p className="fx-run-detail-meta">{formatTime(selected.created_at)}{selectedActive ? ` · đã chạy ${elapsedSeconds}s` : ""}</p>
      <p className="fx-final">{selected.requirement}</p>

      {selected.assignments?.length > 0 && <>
        <h3>Agent được gán</h3>
        <div className="fx-chip-row">{selected.assignments.map((a, i) => (
          <span key={i} className="fx-chip">{a.role}: <b>{a.name}</b> · {a.provider} · {a.model}</span>
        ))}</div>
      </>}

      {selectedActive && <p className="muted">Đang chạy nền trên n8n. Trang này tự cập nhật mỗi vài giây; bạn cứ rời đi và quay lại sau — kết quả vẫn ở đây.</p>}
      {selected.status === "failed" && <p className="fx-error" role="alert">{getRunErrorText(selected)}</p>}
      {selected.status === "needs_configuration" && selected.result?.error && (
        <p className="fx-error" role="alert">{selected.result.error}</p>
      )}

      <RunResult run={selected} />
    </div>}
  </div>;
}
