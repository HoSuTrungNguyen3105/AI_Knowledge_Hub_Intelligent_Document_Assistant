"use client";

import { CircleAlert, LoaderCircle, MessagesSquare, Plus } from "lucide-react";
import { formatDate } from "../../utils/format";

export function ConversationList({ conversations, activeId, onSelect, onNew, onReload, busy }) {
  const { items, loading, error } = conversations;
  return (
    <nav className="conversation-list" aria-label="Danh sách hội thoại">
      <button type="button" className="button primary new-conversation" onClick={onNew} disabled={Boolean(busy)}>
        <Plus size={16} />Hội thoại mới
      </button>
      {loading && items.length === 0 ? (
        <div className="conversation-loading" role="status" aria-label="Đang tải hội thoại"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>
      ) : error ? (
        <div className="conversation-error" role="alert"><CircleAlert size={18} /><p>{error}</p><button type="button" className="button secondary" onClick={onReload}>Thử lại</button></div>
      ) : items.length === 0 ? (
        <div className="conversation-empty"><MessagesSquare size={20} /><p>Chưa có hội thoại nào.</p></div>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className={`conversation-item ${item.id === activeId ? "active" : ""}`} aria-current={item.id === activeId ? "true" : undefined} onClick={() => onSelect(item.id)} disabled={Boolean(busy)}>
                <strong>{item.title}</strong>
                <small>{item.provider} · {item.model}</small>
                <time>{formatDate(item.updated_at)}</time>
              </button>
            </li>
          ))}
        </ul>
      )}
      {loading && items.length > 0 && <p className="conversation-refreshing"><LoaderCircle size={13} className="spin" />Đang cập nhật…</p>}
    </nav>
  );
}