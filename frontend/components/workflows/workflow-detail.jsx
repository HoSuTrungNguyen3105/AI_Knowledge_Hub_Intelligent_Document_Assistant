"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, Ban, CalendarDays, Check, CircleCheck, Code2, Crown, FlaskConical,
  ListTodo, MessagesSquare, Pause, Play, Plus, Search, Settings2, Sparkles, Star,
} from "lucide-react";
import { streamWorkflow, teamsService, workflowsService } from "../../services/workflows";
import {
  TASK_COLUMNS, WORKFLOW_STATUS, agentStatus, elapsedLabel, getWorkflowError,
  progressOf, roleMeta, stepperOf, timeLabel,
} from "../../utils/workflows";

const ROLE_ICONS = {
  coordinator: Crown, planner: CalendarDays, architect: CircleCheck, developer: Code2,
  tester: FlaskConical, reviewer: Star, researcher: Search, member: Sparkles,
};

function Ring({ percent, size = 92, stroke = 9, color = "#7c3aed" }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  return <div className="wf-ring-wrap" style={{ width: size, height: size }}>
    <svg className="wf-ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle className="track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
      <circle className="value" cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color}
        strokeWidth={stroke} strokeDasharray={circumference}
        strokeDashoffset={circumference - (percent / 100) * circumference} />
    </svg><strong>{percent}%</strong></div>;
}

export function WorkflowDetail({ workflowId }) {
  const [workflow, setWorkflow] = useState(null);
  const [team, setTeam] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [messages, setMessages] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [, setTick] = useState(0);
  const messagesRef = useRef(null);
  const reloadTimer = useRef(null);

  const load = useCallback(async (signal) => {
    try {
      const wf = await workflowsService.get(workflowId, signal);
      const [taskList, messageList, eventList, teamData] = await Promise.all([
        workflowsService.tasks(workflowId, signal), workflowsService.messages(workflowId, signal),
        workflowsService.events(workflowId, signal), teamsService.get(wf.team_id, signal).catch(() => null),
      ]);
      setWorkflow(wf); setTasks(taskList); setMessages(messageList); setEvents(eventList); setTeam(teamData);
    } catch (e) {
      if (e?.name !== "AbortError") setError(getWorkflowError(e, "Không tải được workflow."));
    } finally { setLoading(false); }
  }, [workflowId]);

  useEffect(() => {
    const controller = new AbortController();
    (async () => { await load(controller.signal); })();
    return () => controller.abort();
  }, [load]);

  // Live updates: SSE is observation-only; any event schedules a data reload.
  useEffect(() => {
    if (!workflow || workflow.status !== "running") return undefined;
    const controller = new AbortController();
    streamWorkflow(workflowId, {
      signal: controller.signal,
      onEvent: () => {
        clearTimeout(reloadTimer.current);
        reloadTimer.current = setTimeout(() => load(), 150);
      },
    }).catch(() => { /* stream ended; polling fallback below covers state */ });
    const poll = setInterval(() => load(), 4000);
    return () => { controller.abort(); clearInterval(poll); };
  }, [workflow?.status, workflowId, load]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (autoScroll && messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [messages, autoScroll]);

  const members = useMemo(() => team?.members || [], [team]);
  const agentById = useMemo(() => {
    const map = new Map();
    for (const m of members) map.set(m.agent_id, { name: m.agent_name || "Agent", role: m.role });
    return map;
  }, [members]);
  const progress = useMemo(() => progressOf(tasks), [tasks]);
  const stepper = useMemo(() => stepperOf(tasks, workflow), [tasks, workflow]);
  const currentTask = tasks.find((t) => t.status === "in_progress") || null;

  async function act(action) {
    setBusy(action); setError("");
    try {
      const updated = await workflowsService[action](workflowId);
      setWorkflow(updated);
      await load();
    } catch (e) { setError(getWorkflowError(e, "Thao tác thất bại.")); } finally { setBusy(""); }
  }

  if (loading) return <div className="wf-page"><p className="wf-empty">Đang tải workspace…</p></div>;
  if (!workflow) return <div className="wf-page"><p className="wf-error" role="alert">{error || "Không tìm thấy workflow."}</p>
    <Link className="wf-btn" href="/agents/workflows"><ArrowLeft size={15} /> Quay lại danh sách</Link></div>;

  const status = WORKFLOW_STATUS[workflow.status] || WORKFLOW_STATUS.queued;
  const terminal = ["completed", "failed", "cancelled"].includes(workflow.status);

  return <div className="wf-page">
    <div className="wf-header">
      <div><h1><Sparkles size={26} /> AI Agent Studio</h1>
        <p className="muted">Multi-Agent Collaboration Workspace</p>
        <p style={{ marginTop: 8 }}><b>{workflow.title}</b> — {workflow.goal}</p>
        {workflow.error_code && <p className="wf-error" role="alert">Lỗi: {workflow.error_code}</p>}
        {error && <p className="wf-error" role="alert">{error}</p>}
      </div>
      <div className="wf-actions">
        <Link className="wf-btn" href="/agents/workflows"><Plus size={16} /> New Task</Link>
        {workflow.status === "queued" && <button className="wf-btn primary" type="button" disabled={Boolean(busy)} onClick={() => act("start")}><Play size={16} /> Run Workflow</button>}
        {workflow.status === "waiting" && <button className="wf-btn primary" type="button" disabled={Boolean(busy)} onClick={() => act("resume")}><Play size={16} /> Resume</button>}
        {workflow.status === "running" && <button className="wf-btn" type="button" disabled={Boolean(busy)} onClick={() => act("pause")}><Pause size={16} /> Pause</button>}
        {!terminal && <button className="wf-btn" type="button" disabled={Boolean(busy)} onClick={() => act("cancel")}><Ban size={16} /> Cancel</button>}
        <Link className="wf-btn" href="/agents/teams"><Settings2 size={16} /> Settings</Link>
      </div>
    </div>

    <div className="wf-agent-strip" aria-label="Agent tham gia">
      {members.map((m) => {
        const meta = roleMeta(m.role); const Icon = ROLE_ICONS[m.role] || Sparkles;
        const st = agentStatus(m.agent_id, tasks, workflow);
        return <article className="wf-agent-card" key={m.agent_id}>
          <div className="wf-agent-top"><span className="wf-role-icon" style={{ background: meta.color }}><Icon size={19} /></span>
            <span><span className="wf-agent-name">AI {meta.short === "Agent" ? (m.agent_name || "Agent") : meta.short}</span>
              <span className="wf-agent-role" style={{ display: "block" }}>{m.agent_name} · {meta.label}</span></span></div>
          <p className="wf-agent-status"><span className="wf-dot" style={{ background: st.color }} />{st.label}</p>
          <p className="wf-agent-note" title={st.note}>{st.note}</p>
        </article>;
      })}
      {!members.length && <p className="wf-empty">Không tải được thành viên nhóm.</p>}
    </div>

    <div className="wf-grid">
      <div className="wf-col">
        <section className="wf-card" aria-label="Task Board">
          <h2><ListTodo size={17} /> Task Board</h2>
          <div className="wf-task-columns">
            {TASK_COLUMNS.slice(0, 4).map((col) => <div className="wf-task-col" key={col.key}>
              <h3>{col.label} ({tasks.filter((t) => t.status === col.key).length})</h3>
              {tasks.filter((t) => t.status === col.key).map((t) => <div className="wf-task" key={t.id}>
                <p>{t.title}</p>
                <small>{agentById.get(t.assigned_agent_id)?.name || "—"}{t.revision_count ? ` · sửa ${t.revision_count} lần` : ""}</small>
                <span className={`wf-badge ${t.priority || "normal"}`}>{t.priority || "normal"}</span>
              </div>)}
              {!tasks.some((t) => t.status === col.key) && <p className="wf-empty" style={{ padding: 8 }}>Trống</p>}
            </div>)}
          </div>
          {tasks.some((t) => t.status === "failed") && <p className="wf-error">Có task thất bại — xem Communication Center.</p>}
        </section>
        <section className="wf-card" aria-label="Project Progress">
          <h2>Project Progress</h2>
          <div className="wf-progress-ring"><Ring percent={progress.percent} />
            <ul className="wf-progress-counts">
              <li><span className="wf-dot" style={{ background: "#16a34a" }} />Completed<b>{progress.completed}</b></li>
              <li><span className="wf-dot" style={{ background: "#2563eb" }} />In Progress<b>{progress.inProgress}</b></li>
              <li><span className="wf-dot" style={{ background: "#dc2626" }} />Pending<b>{progress.pending}</b></li>
            </ul></div>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>Overall Progress — tính từ {progress.total} task thật của workflow.</p>
        </section>
      </div>

      <section className="wf-card wf-comm" aria-label="Communication Center">
        <div className="wf-comm-head"><h2><MessagesSquare size={17} /> Communication Center</h2>
          <span className="wf-live"><span className="wf-dot" style={{ background: workflow.status === "running" ? "#16a34a" : "#94a3b8" }} />{workflow.status === "running" ? "Live" : status.label}</span>
          <label className="wf-switch">Auto Scroll <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} /></label>
        </div>
        <div className="wf-messages" ref={messagesRef}>
          {messages.map((msg) => {
            const from = agentById.get(msg.from_agent_id);
            const role = msg.from_agent_id === "user" ? "member" : (from?.role || "coordinator");
            const meta = roleMeta(role); const Icon = ROLE_ICONS[role] || Sparkles;
            const name = msg.from_agent_id === "user" ? "Bạn" : (from?.name || "Coordinator");
            const to = agentById.get(msg.to_agent_id)?.name || (msg.to_agent_id === "user" ? "Bạn" : msg.to_agent_id);
            return <div className="wf-msg" key={msg.id}>
              <span className="wf-msg-avatar" style={{ background: meta.color }}><Icon size={17} /></span>
              <div className="wf-msg-body">
                <p className="wf-msg-meta"><b>{name}</b>
                  <span>→ {to}</span><time>{timeLabel(msg.created_at)}</time>
                  <span className="wf-msg-type">{msg.message_type} · {msg.status}</span></p>
                <div className="wf-bubble" style={{ background: meta.soft }}>{msg.content}</div>
              </div></div>;
          })}
          {!messages.length && <p className="wf-empty">Chưa có tin nhắn nào. Bấm Run Workflow để các Agent bắt đầu trao đổi thật.</p>}
        </div>
        <p className="muted" style={{ fontSize: 12 }}>Tin nhắn hiển thị là dữ liệu thật từ Backend (MongoDB + SSE). Gửi yêu cầu mới bằng cách tạo workflow mới.</p>
      </section>

      <div className="wf-col right">
        <section className="wf-card" aria-label="Workflow Status">
          <h2>Workflow Status <span className="wf-status-badge"><span className="wf-dot" style={{ background: status.color }} />{status.label}</span></h2>
          <div className="wf-progress-ring"><Ring percent={progress.percent} color="#16a34a" />
            <div>
              <p className="wf-kv"><span>Elapsed Time</span><b>{elapsedLabel(workflow) || "—"}</b></p>
              <p className="wf-kv"><span>Agent turns</span><b>{workflow.usage?.agent_turns ?? 0}/{workflow.max_steps}</b></p>
              <p className="wf-kv"><span>Tokens (provider)</span><b>{(workflow.usage?.input_tokens ?? 0) + (workflow.usage?.output_tokens ?? 0) || "—"}</b></p>
            </div></div>
          <div className="wf-stepper">{stepper.map((step, i) => <span className={`wf-step ${step.state}`} key={step.key}>
            <span className="wf-step-dot">{step.state === "done" ? <Check size={13} /> : i + 1}</span>{step.label}</span>)}
          </div>
        </section>
        <section className="wf-card" aria-label="Current Task">
          <h2>Current Task</h2>
          {currentTask ? <><p style={{ fontWeight: 600, marginTop: 10 }}>{currentTask.title}</p>
            <p className="muted" style={{ fontSize: 12.5 }}>Assigned to: {agentById.get(currentTask.assigned_agent_id)?.name || "—"}</p></>
            : <p className="wf-empty">Không có task đang chạy.</p>}
        </section>
        {workflow.final_result && <section className="wf-card" aria-label="Final Result">
          <h2>Kết quả cuối cùng</h2><div className="wf-final" style={{ marginTop: 10 }}>{workflow.final_result}</div>
        </section>}
        <section className="wf-card" aria-label="Recent Activity">
          <h2>Recent Activity</h2>
          <ul className="wf-activity">
            {events.slice(-8).reverse().map((e) => <li key={e.id}><span className="wf-dot" style={{ background: "#7c3aed", marginTop: 6 }} />
              <span style={{ flex: 1 }}>{e.event_type.replaceAll("_", " ")}</span><time>{timeLabel(e.created_at)}</time></li>)}
            {!events.length && <li>Chưa có hoạt động.</li>}
          </ul>
        </section>
      </div>
    </div>
  </div>;
}
