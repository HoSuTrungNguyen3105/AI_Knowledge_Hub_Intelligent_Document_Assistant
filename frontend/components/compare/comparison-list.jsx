"use client";

import { CircleAlert, Columns2, LoaderCircle, Plus } from "lucide-react";
import { formatDate } from "../../utils/format";

export function ComparisonList({ comparisons, activeId, onSelect, onNew, onReload, busy }) {
  const { items, loading, error } = comparisons;
  return (
    <nav className="conversation-list" aria-label="Danh sách phép so sánh">
      <button type="button" className="button primary new-conversation" onClick={onNew} disabled={Boolean(busy)}>
        <Plus size={16} />So sánh mới
      </button>
      {loading && items.length === 0 ? (
        <div className="conversation-loading" role="status" aria-label="Đang tải phép so sánh"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>
      ) : error ? (
        <div className="conversation-error" role="alert"><CircleAlert size={18} /><p>{error}</p><button type="button" className="button secondary" onClick={onReload}>Thử lại</button></div>
      ) : items.length === 0 ? (
        <div className="conversation-empty"><Columns2 size={20} /><p>Chưa có phép so sánh nào.</p></div>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className={`conversation-item ${item.id === activeId ? "active" : ""}`} aria-current={item.id === activeId ? "true" : undefined} onClick={() => onSelect(item.id)} disabled={Boolean(busy)}>
                <strong>{item.title}</strong>
                <small>{item.targets.length} model · {item.targets.map((target) => target.provider).join(", ")}</small>
                <time>{formatDate(item.updated_at)}{item.has_synthesis ? " · đã tổng hợp" : ""}</time>
              </button>
            </li>
          ))}
        </ul>
      )}
      {loading && items.length > 0 && <p className="conversation-refreshing"><LoaderCircle size={13} className="spin" />Đang cập nhật…</p>}
    </nav>
  );
}