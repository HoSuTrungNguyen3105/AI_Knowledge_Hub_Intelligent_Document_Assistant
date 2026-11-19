"use client";

import { Bot, LoaderCircle, Plus } from "lucide-react";
import { formatDate, initials } from "../../utils/format";

export function AgentList({ controller }) {
  const { agents, activeId, busy, selectAgent, newAgent, reloadList } = controller;
  return <nav className="conversation-list agent-list" aria-label="Agent của bạn">
    <button type="button" className="button primary new-conversation" onClick={newAgent} disabled={Boolean(busy)}><Plus size={16} />Agent mới</button>
    {agents.loading && !agents.items.length ? <div className="conversation-loading" role="status" aria-label="Đang tải Agent"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>
      : agents.error ? <div className="conversation-error" role="alert"><p>{agents.error}</p><button className="button secondary" onClick={reloadList}>Thử lại Agent</button></div>
        : !agents.items.length ? <div className="conversation-empty"><Bot size={22} /><p>Chưa có Agent nào.</p><small>Tạo Agent đầu tiên với model và công cụ của bạn.</small></div>
          : <ul>{agents.items.map((agent) => <li key={agent.id}><button type="button" className={`conversation-item ${agent.id === activeId ? "active" : ""}`} aria-current={agent.id === activeId ? "true" : undefined} onClick={() => selectAgent(agent.id)} disabled={Boolean(busy)}><span className="agent-list-row"><span className="avatar agent-avatar" aria-hidden="true">{initials(agent.name)}</span><span className="agent-list-copy"><strong>{agent.name}</strong><small>{agent.provider} · {agent.model}</small><small>{agent.tools.length} công cụ</small><time dateTime={agent.updated_at}>{formatDate(agent.updated_at)}</time></span></span></button></li>)}</ul>}
    {agents.loading && agents.items.length > 0 && <p className="conversation-refreshing"><LoaderCircle size={13} className="spin" />Đang cập nhật…</p>}
  </nav>;
}
