"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy, PenLine, Pencil, Play, Square, Trash2 } from "lucide-react";
import { useChatProviders } from "../../hooks/use-chat-providers";
import { initials } from "../../utils/format";
import { toolCapability } from "../../utils/agents";
import { AgentEditor } from "./agent-editor";
import { RenameAgentDialog } from "./rename-agent";
import { ExecutionHistory } from "./execution-history";
import { ExecutionDetail } from "./execution-detail";

export function AgentView({ controller }) {
  const { agent, tools, busy, editing, setEditing, saveAgent, duplicateAgent, setDeletion, run, stop, isStreaming, streamError, reloadTools, reloadList, reloadDetail } = controller;
  const providers = useChatProviders(agent.provider);
  const [prompt, setPrompt] = useState("");
  const [renaming, setRenaming] = useState(false);
  const provider = providers.available.find((item) => item.id === agent.provider);
  const model = providers.providerId === agent.provider ? providers.models.find((item) => item.id === agent.model) : null;
  const capability = toolCapability(provider, model);
  const selectedUnavailable = agent.tools.some((name) => !tools.items.some((tool) => tool.name === name && tool.available));
  const providersLoading = providers.catalog.loading || providers.modelsLoading;
  const blocked = Boolean(busy) || providersLoading || providers.catalog.error || providers.modelsError || !provider || !model || tools.loading || tools.error || selectedUnavailable || (agent.tools.length > 0 && capability === false);
  if (editing) return <AgentEditor key={`${agent.id}:${agent.updated_at}`} agent={agent} tools={tools} busy={Boolean(busy)} onSave={saveAgent} onCancel={() => setEditing(false)} reloadTools={reloadTools} />;

  function submit(event) { event.preventDefault(); if (!blocked && !isStreaming && prompt.trim()) run(prompt.trim()); }
  return <section className="conversation-view agent-view">
    <header className="conversation-header"><div className="agent-list-row"><span className="avatar agent-avatar" aria-hidden="true">{initials(agent.name)}</span><div className="conversation-title"><h2>{agent.name}</h2><span className="conversation-model">{agent.provider} · {agent.model}</span></div></div><div className="conversation-tools"><button type="button" className="icon-button" onClick={() => setRenaming(true)} aria-label="Đổi tên Agent" disabled={Boolean(busy) || isStreaming}><PenLine size={17} /></button><button type="button" className="icon-button" onClick={() => setEditing(true)} aria-label="Chỉnh sửa Agent" disabled={Boolean(busy) || isStreaming}><Pencil size={17} /></button><button type="button" className="icon-button" onClick={duplicateAgent} aria-label="Nhân bản Agent" disabled={Boolean(busy) || isStreaming}><Copy size={17} /></button><button type="button" className="icon-button danger" onClick={() => setDeletion({ agentId: agent.id })} aria-label="Xóa Agent" disabled={Boolean(busy) || isStreaming}><Trash2 size={17} /></button></div></header>
    <div className="agent-body">
      <div className="agent-overview"><p className="message-text">{agent.description || "Agent chưa có mô tả."}</p><p className="setup-note">Công cụ: {agent.tools.length ? agent.tools.join(", ") : "Không chọn · chỉ văn bản"}</p><p className="setup-note">Knowledge Base (KB) và Memory chưa khả dụng. Các lượt chạy độc lập.</p><p className="setup-note">Giới hạn mỗi lượt: 6 bước · 120 giây · 8000 đơn vị ước lượng bảo thủ (không phải token tính phí). Tối đa 4 tool mỗi bước; timeout tool 10 giây.</p></div>
      <form className="agent-run-form setup-panel" onSubmit={submit}>
        <label className="field-label" htmlFor="agent-run-prompt">Yêu cầu thực thi</label><textarea id="agent-run-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} maxLength={32000} required disabled={isStreaming || Boolean(busy)} placeholder="Giao việc cho Agent. Không dùng lịch sử làm bộ nhớ cho lượt này." />
        {providersLoading && <p className="setup-note" role="status">Đang tải provider và model…</p>}
        {(providers.catalog.error || providers.modelsError) && <p className="composer-error" role="alert">{providers.catalog.error || providers.modelsError}</p>}
        {!providersLoading && (!provider || !model) && <p className="setup-note error" role="alert">Provider hoặc model đã lưu chưa sẵn sàng. Chỉnh sửa Agent hoặc kiểm tra <Link href="/settings">Cài đặt AI</Link>.</p>}
        {tools.loading && <p className="setup-note" role="status">Đang tải công cụ…</p>}
        {tools.error && <p className="composer-error" role="alert">{tools.error}</p>}
        {selectedUnavailable && !tools.loading && !tools.error && <p className="composer-error" role="alert">Agent có công cụ chưa khả dụng. Chỉnh sửa để bỏ chọn công cụ.</p>}
        {agent.tools.length > 0 && (capability === false ? <p className="composer-error" role="alert">Function calling không được hỗ trợ. Chạy với công cụ bị chặn; chỉnh sửa Agent để bỏ chọn hoặc đổi model.</p> : <p className="setup-note">{capability === null ? "Khả năng function calling chưa xác định; chỉ được kiểm chứng bằng lượt chạy thực tế." : "Function calling được báo hỗ trợ; chỉ được kiểm chứng bằng lượt chạy thực tế."}</p>)}
        {streamError && <p className="composer-error" role="alert">{streamError}</p>}
        <div className="agent-actions">{isStreaming ? <button type="button" className="button secondary" onClick={stop}><Square size={16} />Dừng thực thi</button> : <button type="submit" className="button primary" disabled={Boolean(blocked) || !prompt.trim()}><Play size={16} />Chạy Agent</button>}<button type="button" className="button secondary" onClick={() => { providers.reload(); reloadTools(); }} disabled={isStreaming || providersLoading || Boolean(busy)}>Tải lại khả năng</button></div>
      </form>
      <div className="agent-results"><ExecutionHistory controller={controller} /><ExecutionDetail controller={controller} /></div>
    </div>
    {renaming && <RenameAgentDialog agent={agent} onClose={() => setRenaming(false)} onRenamed={() => { reloadList?.(); reloadDetail?.(); }} />}
  </section>;
}
