"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { GitBranch, Play, Plus, RotateCcw, Sparkles } from "lucide-react";
import { teamsService, workflowsService } from "../../services/workflows";
import { OUTPUT_TYPES, WORKFLOW_STATUS, WORKFLOW_TITLE_MAX, getWorkflowError, validateWorkflowForm } from "../../utils/workflows";

export function WorkflowsList() {
  const router = useRouter();
  const [teams, setTeams] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [teamsLoading, setTeamsLoading] = useState(true);
  const [workflowsLoading, setWorkflowsLoading] = useState(true);
  const [teamsError, setTeamsError] = useState("");
  const [workflowsError, setWorkflowsError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ team_id: "", title: "", goal: "", output_type: "text" });
  // Teams and workflows load independently so one failing request cannot
  // blank out (or misreport) the other section.
  const loadTeams = useCallback(async (signal) => {
    try {
      const teamList = await teamsService.list(signal);
      setTeams(teamList); setTeamsError("");
      setForm((f) => ({ ...f, team_id: f.team_id || teamList[0]?.id || "" }));
    } catch (e) {
      if (e?.name !== "AbortError") setTeamsError(getWorkflowError(e, "Không tải được danh sách nhóm Agent."));
    } finally { setTeamsLoading(false); }
  }, []);

  const loadWorkflows = useCallback(async (signal) => {
    try {
      setWorkflows(await workflowsService.list(signal)); setWorkflowsError("");
    } catch (e) {
      if (e?.name !== "AbortError") setWorkflowsError(getWorkflowError(e, "Không tải được danh sách workflow."));
    } finally { setWorkflowsLoading(false); }
  }, []);

  const load = useCallback(async (signal) => {
    await Promise.allSettled([loadTeams(signal), loadWorkflows(signal)]);
  }, [loadTeams, loadWorkflows]);

  useEffect(() => {
    const controller = new AbortController();
    (async () => { await load(controller.signal); })();
    return () => controller.abort();
  }, [load]);

  async function create(event) {
    event.preventDefault();
    const validationError = validateWorkflowForm(form);
    if (validationError) { setError(validationError); return; }
    setBusy(true); setError("");
    try {
      const created = await workflowsService.create({ team_id: form.team_id, title: form.title.trim(), goal: form.goal.trim(), output_type: form.output_type });
      setForm({ ...form, title: "", goal: "" });
      await load();
      router.push(`/agents/workflows/${created.id}`);
    } catch (e) { setError(getWorkflowError(e, "Không tạo được workflow.")); } finally { setBusy(false); }
  }

  return <div className="wf-page">
    <div className="wf-header"><div><h1><Sparkles size={26} /> AI Agent Studio</h1>
      <p className="muted">Multi-Agent Collaboration Workspace — giao mục tiêu chung cho cả nhóm Agent.</p></div></div>
    {error && <p className="wf-error" role="alert">{error}</p>}
    <div className="wf-card">
      <h2><Plus size={17} /> Tạo workflow mới</h2>
      {teamsLoading ? <p className="wf-empty">Đang tải…</p> : teamsError ? (
        <div><p className="wf-error" role="alert">{teamsError}</p>
          <button className="wf-btn" type="button" onClick={() => { setTeamsLoading(true); loadTeams(); }}>
            <RotateCcw size={15} /> Thử lại danh sách nhóm</button></div>
      ) : !teams.length ? <p className="wf-empty">Chưa có nhóm Agent. <Link className="text-link" href="/agents/teams">Tạo nhóm trước</Link> để bắt đầu.</p> : (
        <form className="wf-form" onSubmit={create} style={{ marginTop: 14 }}>
          <label>Nhóm Agent<select value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}>
            {teams.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.members.length} Agent)</option>)}</select></label>
          <label>Tiêu đề<input value={form.title} maxLength={WORKFLOW_TITLE_MAX} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Ví dụ: Landing Page bán giày sneaker" />
            <small className="muted">Tiêu đề ngắn gọn ({form.title.length}/{WORKFLOW_TITLE_MAX} ký tự) — toàn bộ yêu cầu chi tiết hãy nhập ở ô Mục tiêu chung bên dưới.</small></label>
          <label>Mục tiêu chung<textarea rows={5} value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} placeholder={"Nhập TOÀN BỘ yêu cầu chi tiết ở đây. Ví dụ:\nHãy xây dựng một Landing Page bán giày sneaker bằng React và Tailwind CSS. Yêu cầu: header có logo/menu/giỏ hàng, banner nổi bật, 4 sản phẩm có hình/tên/giá, nút Mua ngay + Thêm vào giỏ, footer thông tin cửa hàng. Đầu ra: source code đầy đủ chạy được, có README hướng dẫn cài đặt, đóng gói ZIP."} />
            <small className="muted">Mọi yêu cầu dài, danh sách chức năng và yêu cầu đầu ra đều thuộc ô này — đừng dán vào ô Tiêu đề.</small></label>
          <label>Sản phẩm đầu ra<select value={form.output_type} onChange={(e) => setForm({ ...form, output_type: e.target.value })}>
            {OUTPUT_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
          <div><button className="wf-btn primary" type="submit" disabled={busy}><Play size={16} /> Tạo workflow</button></div>
        </form>)}
    </div>
    <div className="wf-list">
      {workflowsError && <div className="wf-card"><p className="wf-error" role="alert">{workflowsError}</p>
        <button className="wf-btn" type="button" onClick={() => { setWorkflowsLoading(true); loadWorkflows(); }}>
          <RotateCcw size={15} /> Thử lại danh sách workflow</button></div>}
      {workflows.map((wf) => { const status = WORKFLOW_STATUS[wf.status] || WORKFLOW_STATUS.queued; return (
        <article className="wf-card wf-list-card" key={wf.id}>
          <h3>{wf.title}</h3>
          <p className="muted" style={{ fontSize: 12.5 }}>{wf.goal}</p>
          <div className="row"><span className="wf-dot" style={{ background: status.color }} /><span>{status.label}</span>
            <span>· Bước {wf.current_step}/{wf.max_steps}</span>
            <span>· {new Date(wf.created_at).toLocaleString()}</span>
            {wf.output_type === "website_zip" && <span className="wf-badge zip">Website · ZIP{wf.artifact_status === "ready" ? " sẵn sàng" : wf.artifact_status === "failed" ? " lỗi" : ""}</span>}</div>
          <div className="row"><Link className="wf-btn" href={`/agents/workflows/${wf.id}`}><GitBranch size={15} /> Mở workspace</Link></div>
        </article>); })}
      {!workflowsLoading && !workflowsError && !workflows.length && <p className="wf-empty">Chưa có workflow nào.</p>}
    </div>
  </div>;
}
