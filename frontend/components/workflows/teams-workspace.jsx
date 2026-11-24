"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Database, Plus, RotateCcw, Sparkles, Trash2, Users, Wand2 } from "lucide-react";
import { agentsService } from "../../services/agents";
import { getSeedError, seedService } from "../../services/seed";
import { teamsService } from "../../services/workflows";
import { useChatProviders } from "../../hooks/use-chat-providers";
import {
  STARTER_AGENTS, createStarterSet, getWorkflowError, inferRoleFromName, missingStarterAgents, roleMeta,
} from "../../utils/workflows";
import { ConfirmDialog } from "../confirm-dialog";

const ROLES = ["coordinator", "planner", "architect", "developer", "tester", "reviewer", "researcher", "evaluator", "member"];

export function TeamsWorkspace() {
  const [agents, setAgents] = useState([]);
  const [teams, setTeams] = useState([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [teamsLoading, setTeamsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState("");
  const [teamsError, setTeamsError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [starterBusy, setStarterBusy] = useState(false);
  const [starterMsg, setStarterMsg] = useState("");
  const [seedStatus, setSeedStatus] = useState(null);
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedMsg, setSeedMsg] = useState("");
  const [deletion, setDeletion] = useState(null);
  const [form, setForm] = useState({ name: "", description: "", coordinator: "", picks: {} });
  const providers = useChatProviders();
  const { available, providerId, models, modelsLoading, catalog } = providers;
  const selectedProvider = available.find((item) => item.id === providerId) || null;
  const starterModel = selectedProvider
    ? (models.find((m) => m.id === selectedProvider.default_model) || models[0])?.id || ""
    : "";
  const providerReady = Boolean(selectedProvider && starterModel && !modelsLoading && !catalog.loading);

  // Agents and teams load independently: a failing teams request (e.g. the
  // local backend was not restarted after Phase 6, so the route 404s) must
  // not hide the agents list or block the create form.
  const loadAgents = useCallback(async (signal) => {
    try {
      const agentList = await agentsService.list(signal);
      setAgents(agentList);
      setAgentsError("");
      setForm((f) => ({ ...f, coordinator: f.coordinator || agentList[0]?.id || "" }));
    } catch (e) {
      if (e?.name !== "AbortError") setAgentsError(getWorkflowError(e, "Không tải được danh sách Agent."));
    } finally { setAgentsLoading(false); }
  }, []);

  const loadTeams = useCallback(async (signal) => {
    try {
      setTeams(await teamsService.list(signal));
      setTeamsError("");
    } catch (e) {
      if (e?.name !== "AbortError") setTeamsError(getWorkflowError(e, "Không tải được dữ liệu nhóm Agent."));
    } finally { setTeamsLoading(false); }
  }, []);

  const loadSeedStatus = useCallback(async (signal) => {
    try { setSeedStatus(await seedService.status(signal)); } catch { /* card hides itself */ }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    (async () => { await Promise.allSettled([loadAgents(controller.signal), loadTeams(controller.signal), loadSeedStatus(controller.signal)]); })();
    return () => controller.abort();
  }, [loadAgents, loadTeams, loadSeedStatus]);

  async function applySeed() {
    setSeedBusy(true); setSeedMsg(""); setError("");
    try {
      const result = await seedService.apply();
      setSeedMsg(`Đã nạp dữ liệu demo: tạo ${result.created_agents.length} Agent + ${result.created_teams.length} nhóm`
        + (result.reused_agents.length ? `, dùng lại ${result.reused_agents.length} Agent đã có` : "")
        + (result.skipped_teams.length ? `, bỏ qua ${result.skipped_teams.length} nhóm đã tồn tại` : "") + ".");
      await Promise.allSettled([reloadAll(), loadSeedStatus()]);
    } catch (e) { setSeedMsg(getSeedError(e, "Không nạp được dữ liệu demo.")); }
    finally { setSeedBusy(false); }
  }

  async function removeSeed() {
    setSeedBusy(true); setSeedMsg(""); setError("");
    try {
      const result = await seedService.remove();
      setSeedMsg(`Đã xoá dữ liệu demo: ${result.removed_agents} Agent + ${result.removed_teams} nhóm`
        + (result.kept_agents.length ? `. Giữ lại ${result.kept_agents.join(", ")} vì nhóm thật của bạn đang dùng.` : "."));
      await Promise.allSettled([reloadAll(), loadSeedStatus()]);
    } catch (e) { setSeedMsg(getSeedError(e, "Không xoá được dữ liệu demo.")); }
    finally { setSeedBusy(false); }
  }

  async function reloadAll() { await Promise.allSettled([loadAgents(), loadTeams()]); }

  async function createStarter() {
    if (!providerReady) return;
    setStarterBusy(true); setStarterMsg(""); setError("");
    try {
      let availableToolNames = null;
      try {
        const toolList = await agentsService.tools();
        availableToolNames = toolList.filter((t) => t.available).map((t) => t.name);
      } catch { /* catalog unavailable: fall back to the spec's tool names */ }
      const result = await createStarterSet({
        existingAgents: agents, existingTeams: teams,
        provider: providerId, model: starterModel, availableToolNames,
        createAgent: (payload) => agentsService.create(payload),
        createTeam: (payload) => teamsService.create(payload),
      });
      if (result.failed) {
        setStarterMsg(`Đã tạo ${result.created.length} Agent (${result.created.map((a) => a.name).join(", ") || "chưa có"}), `
          + `dừng tại "${result.failed.name}": ${getWorkflowError(result.failed.error, "tạo thất bại.")} Bấm lại để tiếp tục, Agent đã có sẽ không bị tạo trùng.`);
      } else if (result.team) {
        setStarterMsg(`Đã sẵn sàng: ${result.created.length} Agent mới + ${result.reused.length} Agent đã có, và đã tạo nhóm "${result.team.name}" với AI Leader làm Coordinator.`);
      } else {
        setStarterMsg(`Bộ 7 Agent đã đầy đủ (${result.reused.length} Agent đã có từ trước)${result.teamSkipped ? " và nhóm mẫu đã tồn tại." : "."}`);
      }
      await reloadAll();
    } catch (e) {
      setStarterMsg(getWorkflowError(e, "Không tạo được bộ Agent mẫu."));
    } finally { setStarterBusy(false); }
  }

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
      await loadTeams();
    } catch (e) { setError(getWorkflowError(e, "Không tạo được nhóm.")); } finally { setBusy(false); }
  }

  async function confirmDeletion() {
    if (!deletion) return;
    setBusy(true);
    try { await teamsService.remove(deletion.id); setDeletion(null); await loadTeams(); }
    catch (e) { setError(getWorkflowError(e, "Không xóa được nhóm.")); } finally { setBusy(false); }
  }

  const missingStarters = missingStarterAgents(agents);
  const showStarter = !agentsLoading && !agentsError && missingStarters.length > 0;

  return <div className="wf-page">
    <div className="wf-header"><div><h1><Sparkles size={26} /> AI Agent Studio</h1>
      <p className="muted">Agent Teams — nhóm các Agent đã có để chạy workflow phối hợp (Phase 6).</p></div></div>
    {error && <p className="wf-error" role="alert">{error}</p>}
    <div className="wf-card">
      <h2><Plus size={17} /> Tạo nhóm Agent</h2>
      {agentsLoading ? <p className="wf-empty">Đang tải…</p> : agentsError ? (
        <div>
          <p className="wf-error" role="alert">{agentsError}</p>
          <button className="wf-btn" type="button" onClick={() => { setAgentsLoading(true); loadAgents(); }}>
            <RotateCcw size={15} /> Thử lại danh sách Agent</button>
        </div>
      ) : (
        <>
          {!agents.length && <p className="wf-empty">Chưa có Agent nào. Tạo nhanh bộ 7 Agent mẫu bên dưới, hoặc tạo Agent ở trang Agent Studio trước.</p>}
          {showStarter && <div style={{ marginTop: 14 }}>
            <h3 style={{ margin: "0 0 6px" }}><Wand2 size={16} /> Bộ 7 Agent mẫu (Phase 6)</h3>
            <p className="muted" style={{ fontSize: 12.5 }}>
              Còn thiếu {missingStarters.length}/{STARTER_AGENTS.length} Agent: {missingStarters.map((s) => s.name).join(", ")}.
              Tạo xong sẽ tự tạo nhóm mẫu với AI Leader làm Coordinator. Agent đã có (trùng tên) sẽ không bị tạo lại.
            </p>
            {catalog.loading || modelsLoading ? <p className="wf-empty">Đang kiểm tra provider/model sẵn sàng…</p>
              : !providerReady ? <p className="wf-error" role="alert">
                  Chưa có provider/model sẵn sàng. Hãy vào <Link className="text-link" href="/settings">Cài đặt AI</Link> cấu hình
                  API key, bật provider và đồng bộ model trước — không tạo Agent giả khi chưa có model thật.</p>
              : <button className="wf-btn primary" type="button" disabled={starterBusy} onClick={createStarter}>
                  <Wand2 size={16} /> {starterBusy ? "Đang tạo…" : "Tạo bộ 7 Agent mẫu"}</button>}
            {starterMsg && <p className="muted" role="status" style={{ marginTop: 8 }}>{starterMsg}</p>}
          </div>}
          {agents.length > 0 && (
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
                    onChange={(e) => setForm({ ...form, picks: { ...form.picks, [a.id]: e.target.checked ? (a.id === form.coordinator ? "coordinator" : (inferRoleFromName(a.name) || "member")) : undefined } })} />
                  <span><b>{a.name}</b><br /><small className="muted">{a.provider} / {a.model}</small></span>
                  {form.picks[a.id] && <select aria-label={`Vai trò của ${a.name}`} value={form.picks[a.id]}
                    onChange={(e) => setForm({ ...form, picks: { ...form.picks, [a.id]: e.target.value } })}>
                    {ROLES.map((r) => <option key={r} value={r}>{roleMeta(r).label}</option>)}
                  </select>}
                </div>)}
              </div>
              <div><button className="wf-btn primary" type="submit" disabled={busy}><Users size={16} /> Tạo nhóm</button></div>
            </form>)}
        </>
      )}
    </div>
    {seedStatus && <div className="wf-card" style={{ marginBottom: 16 }}>
      <h2><Database size={17} /> Dữ liệu demo NEXORA</h2>
      {!seedStatus.enabled ? <p className="muted" style={{ fontSize: 12.5 }}>
        Môi trường hiện tại là <b>{seedStatus.app_env}</b> — nạp dữ liệu demo đã bị khoá (chỉ mở ở development/demo).</p>
      : <>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Nạp sẵn 7 Agent mẫu + 3 nhóm mẫu (Kỹ thuật / Nghiên cứu / Vận hành) vào tài khoản của bạn để thử ngay.
          Mọi bản ghi demo đều được gắn nhãn <b>Demo</b> trong dữ liệu, không trộn với dữ liệu thật, nạp lại không tạo trùng,
          và xoá demo không bao giờ chạm vào Agent/nhóm thật của bạn. Agent mẫu dùng provider đang bật + model mặc định của bạn.</p>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Hiện có: <b>{seedStatus.demo_agents}</b> Agent demo · <b>{seedStatus.demo_teams}</b> nhóm demo.</p>
        <div className="row">
          <button className="wf-btn primary" type="button" disabled={seedBusy} onClick={applySeed}>
            <Database size={15} /> {seedBusy ? "Đang xử lý…" : "Nạp dữ liệu demo"}</button>
          {seedStatus.seeded && <button className="wf-btn" type="button" disabled={seedBusy} onClick={removeSeed}>
            <Trash2 size={15} /> Xoá dữ liệu demo</button>}
        </div>
        {seedMsg && <p className="muted" role="status" style={{ marginTop: 8 }}>{seedMsg}</p>}
      </>}
    </div>}
    <div className="wf-list">
      {teamsError ? (
        <div className="wf-card">
          <p className="wf-error" role="alert">{teamsError}</p>
          <button className="wf-btn" type="button" onClick={() => { setTeamsLoading(true); loadTeams(); }}>
            <RotateCcw size={15} /> Thử lại danh sách nhóm</button>
        </div>
      ) : teams.map((team) => <article className="wf-card wf-list-card" key={team.id}>
        <h3>{team.name}</h3>
        {team.description && <p className="muted" style={{ fontSize: 12.5 }}>{team.description}</p>}
        <div>{team.members.map((m) => <div className="row" key={m.agent_id}>
          <span className="wf-dot" style={{ background: roleMeta(m.role).color }} />
          <span>{m.agent_name || m.agent_id} · {roleMeta(m.role).label}{m.agent_id === team.coordinator_agent_id ? " · Coordinator" : ""}</span>
          <span>{m.provider}/{m.model}</span></div>)}
        </div>
        <div className="row"><button className="wf-btn" type="button" onClick={() => setDeletion(team)}><Trash2 size={15} /> Xóa nhóm</button></div>
      </article>)}
      {!teamsLoading && !teamsError && !teams.length && <p className="wf-empty">Chưa có nhóm nào. Tạo nhóm đầu tiên ở biểu mẫu phía trên.</p>}
    </div>
    <ConfirmDialog open={Boolean(deletion)} title="Xóa nhóm Agent này?" busy={busy} onClose={() => setDeletion(null)} onConfirm={confirmDeletion} confirmLabel="Xóa nhóm">
      <p>Nhóm sẽ bị xóa; các Agent gốc và lịch sử chạy của chúng không bị xóa.</p>
    </ConfirmDialog>
  </div>;
}
