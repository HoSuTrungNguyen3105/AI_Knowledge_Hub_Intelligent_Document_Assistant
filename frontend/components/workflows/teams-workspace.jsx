"use client";

import { useCallback, useEffect, useState } from "react";
import { Plus, Sparkles, Trash2, Users } from "lucide-react";
import { agentsService } from "../../services/agents";
import { teamsService } from "../../services/workflows";
import { getWorkflowError, roleMeta } from "../../utils/workflows";
import { ConfirmDialog } from "../confirm-dialog";

const ROLES = ["coordinator", "planner", "architect", "developer", "tester", "reviewer", "researcher", "member"];

export function TeamsWorkspace() {
  const [agents, setAgents] = useState([]);
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deletion, setDeletion] = useState(null);
  const [form, setForm] = useState({ name: "", description: "", coordinator: "", picks: {} });

  const load = useCallback(async (signal) => {
    try {
      const [agentList, teamList] = await Promise.all([agentsService.list(signal), teamsService.list(signal)]);
      setAgents(agentList);
      setTeams(teamList);
      setForm((f) => ({ ...f, coordinator: f.coordinator || agentList[0]?.id || "" }));
    } catch (e) {
      if (e?.name !== "AbortError") setError(getWorkflowError(e, "Không tải được dữ liệu nhóm Agent."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => { await load(controller.signal); })();
    return () => controller.abort();
  }, [load]);

  async function create(event) {
    event.preventDefault();
    const members = agents
      .filter((a) => form.picks[a.id])
      .map((a) => ({ agent_id: a.id, role: form.picks[a.id], enabled: true }));
    if (!form.name.trim() || !members.length) { setError("Nhập tên nhóm và chọn ít nhất một Agent."); return; }
    if (!members.some((m) => m.agent_id === form.coordinator)) {
      members.push({ agent_id: form.coordinator, role: "coordinator", enabled: true });
    }
    setBusy(true); setError("");
    try {
      await teamsService.create({ name: form.name.trim(), description: form.description || null, coordinator_agent_id: form.coordinator, members });
      setForm({ name: "", description: "", coordinator: form.coordinator, picks: {} });
      await load();
    } catch (e) { setError(getWorkflowError(e, "Không tạo được nhóm.")); } finally { setBusy(false); }
  }

  async function confirmDeletion() {
    if (!deletion) return;
    setBusy(true);
    try { await teamsService.remove(deletion.id); setDeletion(null); await load(); }
    catch (e) { setError(getWorkflowError(e, "Không xóa được nhóm.")); } finally { setBusy(false); }
  }

  return <div className="wf-page">
    <div className="wf-header"><div><h1><Sparkles size={26} /> AI Agent Studio</h1>
      <p className="muted">Agent Teams — nhóm các Agent đã có để chạy workflow phối hợp (Phase 6).</p></div></div>
    {error && <p className="wf-error" role="alert">{error}</p>}
    <div className="wf-card">
      <h2><Plus size={17} /> Tạo nhóm Agent</h2>
      {loading ? <p className="wf-empty">Đang tải…</p> : !agents.length ? <p className="wf-empty">Chưa có Agent nào. Hãy tạo Agent ở trang Agent Studio trước.</p> : (
        <form className="wf-form" onSubmit={create} style={{ marginTop: 14 }}>
          <label>Tên nhóm<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ví dụ: Nhóm phân tích sản phẩm" /></label>
          <label>Mô tả<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <label>Coordinator (Leader)
            <select value={form.coordinator} onChange={(e) => setForm({ ...form, coordinator: e.target.value })}>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name} — {a.provider}/{a.model}</option>)}
            </select></label>
          <div className="wf-form">
            {agents.map((a) => <div className="wf-member-row" key={a.id}>
              <input type="checkbox" aria-label={`Chọn ${a.name}`} checked={Boolean(form.picks[a.id])}
                onChange={(e) => setForm({ ...form, picks: { ...form.picks, [a.id]: e.target.checked ? (a.id === form.coordinator ? "coordinator" : "member") : undefined } })} />
              <span><b>{a.name}</b><br /><small className="muted">{a.provider} / {a.model}</small></span>
              {form.picks[a.id] && <select aria-label={`Vai trò của ${a.name}`} value={form.picks[a.id]}
                onChange={(e) => setForm({ ...form, picks: { ...form.picks, [a.id]: e.target.value } })}>
                {ROLES.map((r) => <option key={r} value={r}>{roleMeta(r).label}</option>)}
              </select>}
            </div>)}
          </div>
          <div><button className="wf-btn primary" type="submit" disabled={busy}><Users size={16} /> Tạo nhóm</button></div>
        </form>)}
    </div>
    <div className="wf-list">
      {teams.map((team) => <article className="wf-card wf-list-card" key={team.id}>
        <h3>{team.name}</h3>
        {team.description && <p className="muted" style={{ fontSize: 12.5 }}>{team.description}</p>}
        <div>{team.members.map((m) => <div className="row" key={m.agent_id}>
          <span className="wf-dot" style={{ background: roleMeta(m.role).color }} />
          <span>{m.agent_name || m.agent_id} · {roleMeta(m.role).label}{m.agent_id === team.coordinator_agent_id ? " · Coordinator" : ""}</span>
          <span>{m.provider}/{m.model}</span></div>)}
        </div>
        <div className="row"><button className="wf-btn" type="button" onClick={() => setDeletion(team)}><Trash2 size={15} /> Xóa nhóm</button></div>
      </article>)}
      {!loading && !teams.length && <p className="wf-empty">Chưa có nhóm nào. Tạo nhóm đầu tiên ở biểu mẫu phía trên.</p>}
    </div>
    <ConfirmDialog open={Boolean(deletion)} title="Xóa nhóm Agent này?" busy={busy} onClose={() => setDeletion(null)} onConfirm={confirmDeletion} confirmLabel="Xóa nhóm">
      <p>Nhóm sẽ bị xóa; các Agent gốc và lịch sử chạy của chúng không bị xóa.</p>
    </ConfirmDialog>
  </div>;
}
