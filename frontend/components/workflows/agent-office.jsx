"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AgentAvatar } from "./agent-avatar";
import {
  CalendarDays, Check, CircleCheck, Clock, Code2, Crown, FlaskConical, LoaderCircle,
  Pencil, Search, Sparkles, Star, X,
} from "lucide-react";
import {
  OFFICE_WAYPOINTS, WORKFLOW_STATUS, agentStatus, officeLayout, progressOf, roleMeta, taskPercent, timeLabel,
} from "../../utils/workflows";

const ROLE_ICONS = {
  coordinator: Crown, planner: CalendarDays, architect: CircleCheck, developer: Code2,
  tester: FlaskConical, reviewer: Star, researcher: Search, member: Sparkles,
};

const TASK_ICON = {
  completed: <Check size={13} />,
  in_progress: <LoaderCircle size={13} className="spin" />,
  review: <Clock size={13} />,
  pending: <Clock size={13} />,
  failed: <X size={13} />,
};

function truncate(text, max) {
  const value = String(text || "");
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

// Simulation view of a workflow: the team's Agents in a virtual office,
// styled after the user's reference mock. This is a *visualisation mode*
// only — desks, movement and wandering are decorative client-side motion,
// while every name, status, task and chat line comes from the real
// workflow data passed in by the detail page (which keeps polling/SSE).
export function AgentOffice({ workflow, team, tasks, messages, onRenameAgent }) {
  const members = useMemo(() => team?.members || [], [team]);
  const layout = useMemo(() => officeLayout(members), [members]);
  const deskById = useMemo(() => new Map(layout.map((s) => [s.agent_id, s])), [layout]);
  const progress = useMemo(() => progressOf(tasks), [tasks]);
  const status = WORKFLOW_STATUS[workflow?.status] || WORKFLOW_STATUS.queued;

  const statusById = useMemo(() => {
    const map = new Map();
    for (const m of members) map.set(m.agent_id, agentStatus(m.agent_id, tasks, workflow));
    return map;
  }, [members, tasks, workflow]);

  const bubbleById = useMemo(() => {
    const map = new Map();
    for (const m of members) {
      const mine = tasks.filter((t) => t.assigned_agent_id === m.agent_id);
      const active = mine.find((t) => t.status === "in_progress" || t.status === "review");
      if (active) { map.set(m.agent_id, { text: active.title, working: true }); continue; }
      const lastMsg = [...messages].reverse().find((msg) => msg.from_agent_id === m.agent_id);
      if (lastMsg) { map.set(m.agent_id, { text: truncate(lastMsg.content, 72), working: false }); continue; }
      map.set(m.agent_id, { text: statusById.get(m.agent_id)?.note || "Đang chờ việc…", working: false });
    }
    return map;
  }, [members, tasks, messages, statusById]);

  // Wander engine: working agents stay at their desk; idle agents sometimes
  // stroll to a floor waypoint and later walk back. Pure decoration.
  const [spots, setSpots] = useState({});
  const [movingIds, setMovingIds] = useState(() => new Set());
  const prevSpots = useRef({});
  const moveTimers = useRef({});
  useEffect(() => () => { Object.values(moveTimers.current).forEach(clearTimeout); }, []);
  // An agent is "walking" (leg animation on) from the moment its target
  // spot changes until the CSS transition (2.6s) has had time to finish.
  useEffect(() => {
    for (const [agentId, spot] of Object.entries(spots)) {
      const prev = prevSpots.current[agentId];
      if (prev && (prev.x !== spot.x || prev.y !== spot.y)) {
        setMovingIds((current) => new Set(current).add(agentId));
        clearTimeout(moveTimers.current[agentId]);
        moveTimers.current[agentId] = setTimeout(() => {
          setMovingIds((current) => { const next = new Set(current); next.delete(agentId); return next; });
        }, 2650);
      }
    }
    prevSpots.current = spots;
  }, [spots]);
  useEffect(() => {
    setSpots((prev) => {
      const next = {};
      for (const s of layout) next[s.agent_id] = prev[s.agent_id] || { x: s.x, y: s.y };
      return next;
    });
  }, [layout]);
  useEffect(() => {
    if (members.length < 2) return undefined;
    const timer = setInterval(() => {
      setSpots((prev) => {
        const next = { ...prev };
        for (const m of members) {
          const desk = deskById.get(m.agent_id);
          if (!desk) continue;
          const current = prev[m.agent_id] || desk;
          const working = statusById.get(m.agent_id)?.label === "Working"
            || statusById.get(m.agent_id)?.label === "Reviewing";
          const atDesk = Math.abs(current.x - desk.x) < 0.5 && Math.abs(current.y - desk.y) < 0.5;
          if (working) {
            if (!atDesk) next[m.agent_id] = { x: desk.x, y: desk.y };
          } else if (!atDesk) {
            if (Math.random() < 0.45) next[m.agent_id] = { x: desk.x, y: desk.y };
          } else if (Math.random() < 0.28) {
            const wp = OFFICE_WAYPOINTS[Math.floor(Math.random() * OFFICE_WAYPOINTS.length)];
            next[m.agent_id] = { x: wp.x, y: wp.y };
          }
        }
        return next;
      });
    }, 3200);
    return () => clearInterval(timer);
  }, [members, deskById, statusById]);

  const recentMessages = useMemo(() => messages.slice(-6).reverse(), [messages]);
  const nameOf = (agentId) => members.find((m) => m.agent_id === agentId)?.agent_name || "Agent";

  return <div className="wf-office-wrap">
    <div className="wf-office-main">
      <div className="wf-office-topbar">
        <div className="wf-office-goal">
          <span className="wf-office-goal-label">Mục tiêu hiện tại</span>
          <strong title={workflow.goal}>{truncate(workflow.goal, 90)}</strong>
        </div>
        <div className="wf-office-progress">
          <span>Tiến độ tổng thể</span>
          <div className="wf-office-progress-track"><div style={{ width: `${progress.percent}%` }} /></div>
          <strong>{progress.percent}%</strong>
        </div>
        <span className="wf-status-badge"><span className="wf-dot" style={{ background: status.color }} />{status.label}</span>
      </div>

      <div className="wf-office-room" role="img" aria-label="Văn phòng AI mô phỏng: các Agent đang làm việc tại bàn của mình">
        <div className="wf-office-board"><span>Multi-Agent Office</span><small>Chế độ mô phỏng — dữ liệu thật, chuyển động minh họa</small></div>
        {layout.map((slot) => {
          const member = members.find((m) => m.agent_id === slot.agent_id);
          if (!member) return null;
          const meta = roleMeta(member.role);
          return <div className="wf-desk" key={`desk-${slot.agent_id}`} style={{ left: `${slot.x}%`, top: `${slot.y}%` }}>
            <div className="wf-desk-table"><div className="wf-desk-screen" style={{ borderColor: meta.color }} /></div>
          </div>;
        })}
        {layout.map((slot) => <div className="wf-desk-front" key={`front-${slot.agent_id}`}
          style={{ left: `${slot.x}%`, top: `${slot.y}%` }} />)}
        {members.map((m) => {
          const meta = roleMeta(m.role);
          const Icon = ROLE_ICONS[m.role] || Sparkles;
          const desk = deskById.get(m.agent_id);
          const spot = (desk && spots[m.agent_id]) || desk || { x: 50, y: 50 };
          const away = desk ? Math.abs(spot.x - desk.x) > 0.5 || Math.abs(spot.y - desk.y) > 0.5 : false;
          const walking = movingIds.has(m.agent_id);
          const working = Boolean(bubbleById.get(m.agent_id)?.working);
          const st = statusById.get(m.agent_id) || { label: "Waiting", color: "#2563eb" };
          const bubble = bubbleById.get(m.agent_id);
          // 2.5D depth: agents lower in the room stand closer to the viewer
          // and render slightly larger.
          const depthScale = 0.8 + (spot.y / 100) * 0.38;
          return <div className={`wf-office-agent${away ? " away" : ""}`} key={m.agent_id}
            style={{ left: `${spot.x}%`, top: `${spot.y}%`, transform: `translate(-50%, -50%) scale(${depthScale.toFixed(2)})` }}>
            {bubble && <div className={`wf-office-bubble${bubble.working ? " working" : ""}`} title={bubble.text}>
              {truncate(bubble.text, 46)}{bubble.working && <span className="wf-typing"><i /><i /><i /></span>}
            </div>}
            <span className="wf-office-shadow" />
            <span className="wf-office-avatar"><AgentAvatar color={meta.color} role={m.role} walking={walking} working={!away && working} /></span>
            <button type="button" className="wf-office-nameplate" onClick={() => onRenameAgent?.(m)}
              title="Bấm để đổi tên Agent" aria-label={`Đổi tên ${m.agent_name || "Agent"}`}>
              <Icon size={12} /> {m.agent_name || "Agent"} <Pencil size={11} />
            </button>
            <span className="wf-office-status"><span className="wf-dot" style={{ background: st.color }} />{st.label}</span>
          </div>;
        })}
        {!members.length && <p className="wf-empty" style={{ position: "absolute", inset: "auto 0 12px" }}>Không tải được thành viên nhóm.</p>}
      </div>

      <div className="wf-office-strip" aria-label="Đội ngũ AI của bạn">
        {members.map((m) => {
          const meta = roleMeta(m.role);
          const Icon = ROLE_ICONS[m.role] || Sparkles;
          const st = statusById.get(m.agent_id) || { label: "Waiting", color: "#2563eb" };
          return <span className="wf-office-chip" key={m.agent_id}>
            <span className="wf-office-chip-icon" style={{ background: meta.color }}><Icon size={14} /></span>
            <span className="wf-office-chip-name">{m.agent_name || "Agent"}</span>
            <span className="wf-office-chip-status"><span className="wf-dot" style={{ background: st.color }} />{st.label}</span>
          </span>;
        })}
      </div>
    </div>

    <aside className="wf-office-rail">
      <section className="wf-card" aria-label="Danh sách nhiệm vụ (mô phỏng)">
        <h2>Danh sách nhiệm vụ</h2>
        <ul className="wf-office-tasks">
          {tasks.map((t) => <li key={t.id}>
            <span className={`wf-office-task-icon ${t.status}`}>{TASK_ICON[t.status] || TASK_ICON.pending}</span>
            <div className="wf-office-task-body">
              <p>{t.title}</p>
              <small>{nameOf(t.assigned_agent_id)}</small>
              <div className="wf-office-task-track"><div className={t.status} style={{ width: `${taskPercent(t.status)}%` }} /></div>
            </div>
            <b>{taskPercent(t.status)}%</b>
          </li>)}
          {!tasks.length && <li className="wf-empty">Chưa có nhiệm vụ nào.</li>}
        </ul>
      </section>
      <section className="wf-card" aria-label="Trò chuyện đội ngũ AI (mô phỏng)">
        <h2>Trò chuyện đội ngũ AI</h2>
        <ul className="wf-office-chat">
          {recentMessages.map((msg) => {
            const from = members.find((m) => m.agent_id === msg.from_agent_id);
            const meta = roleMeta(from?.role || "coordinator");
            const Icon = ROLE_ICONS[from?.role || "coordinator"] || Sparkles;
            return <li key={msg.id}>
              <span className="wf-msg-avatar" style={{ background: meta.color, width: 30, height: 30 }}><Icon size={14} /></span>
              <div><p className="wf-office-chat-meta"><b>{msg.from_agent_id === "user" ? "Bạn" : (from?.agent_name || "Coordinator")}</b><time>{timeLabel(msg.created_at)}</time></p>
                <p className="wf-office-chat-text">{truncate(msg.content, 110)}</p></div>
            </li>;
          })}
          {!recentMessages.length && <li className="wf-empty">Chưa có trò chuyện nào.</li>}
        </ul>
        <p className="muted" style={{ fontSize: 12 }}>Khung chat đầy đủ ở chế độ Workspace (Communication Center).</p>
      </section>
    </aside>
  </div>;
}
