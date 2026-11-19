"use client";

import { RefreshCw, Trash2 } from "lucide-react";
import { executionStatusLabels } from "../../utils/agents";
import { formatDate } from "../../utils/format";

export function ExecutionHistory({ controller }) {
  const { history, activeId, activeExecutionId, selectExecution, reloadHistory, isStreaming, busy, setDeletion } = controller;
  return <section className="agent-history" aria-label="Lịch sử thực thi">
    <div className="section-heading"><h3>Lịch sử thực thi</h3><button type="button" className="icon-button" onClick={reloadHistory} disabled={history.loading} aria-label="Tải lại lịch sử"><RefreshCw size={16} className={history.loading ? "spin" : ""} /></button></div>
    {history.loading ? <div role="status" aria-label="Đang tải lịch sử"><div className="skeleton" /><div className="skeleton" /></div> : history.error ? <p className="composer-error" role="alert">{history.error}</p> : !history.items.length ? <p className="muted">Chưa có lượt thực thi nào. Nhập yêu cầu để bắt đầu.</p> : <ul className="agent-history-list">{history.items.map((execution) => <li key={execution.id} className={activeExecutionId === execution.id ? "active" : ""}><button type="button" className="agent-history-select" onClick={() => selectExecution(execution.id)} aria-current={activeExecutionId === execution.id ? "true" : undefined} disabled={isStreaming || Boolean(busy)}><strong>{execution.prompt}</strong><small>{executionStatusLabels[execution.status] ?? execution.status} · {execution.step_count} bước · {formatDate(execution.created_at)}</small></button><button type="button" className="icon-button danger" onClick={() => setDeletion({ agentId: activeId, executionId: execution.id })} aria-label={`Xóa lượt thực thi: ${execution.prompt}`} disabled={isStreaming || Boolean(busy)}><Trash2 size={16} /></button></li>)}</ul>}
  </section>;
}
