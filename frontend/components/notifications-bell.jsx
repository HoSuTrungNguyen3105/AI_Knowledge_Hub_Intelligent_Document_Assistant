"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";
import { notificationsService } from "../services/notifications";

const timeLabel = (iso) => {
  const date = new Date(iso);
  return date.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
};

// Notification bell (NEXORA Module 15): unread badge + dropdown inbox.
// Polls quietly every 30s; opening the panel refreshes the list.
export function NotificationsBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const wrapRef = useRef(null);

  const load = useCallback(async (signal) => {
    try {
      const data = await notificationsService.list(signal);
      setItems(data.notifications);
      setUnread(data.unread_count);
    } catch { /* the bell stays quiet when the API is unreachable */ }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const timer = setInterval(() => load(), 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (event) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open ]);

  const toggle = () => {
    setOpen((value) => !value);
    if (!open) load();
  };

  const openItem = async (item) => {
    if (!item.read_at) {
      try {
        await notificationsService.markRead(item.id);
        setItems((list) => list.map((n) => (n.id === item.id ? { ...n, read_at: new Date().toISOString() } : n)));
        setUnread((count) => Math.max(0, count - 1));
      } catch { /* navigation still proceeds */ }
    }
    setOpen(false);
    if (item.link) router.push(item.link);
  };

  const readAll = async () => {
    try {
      const data = await notificationsService.markAllRead();
      setItems(data.notifications);
      setUnread(data.unread_count);
    } catch { /* keep current state */ }
  };

  return <div className="notif-wrap" ref={wrapRef}>
    <button className="icon-button" onClick={toggle} aria-label={unread ? `Thông báo (${unread} chưa đọc)` : "Thông báo"} title="Thông báo" aria-expanded={open}>
      <Bell size={18} />
      {unread > 0 && <span className="notif-badge">{unread > 99 ? "99+" : unread}</span>}
    </button>
    {open && <div className="notif-panel" role="menu" aria-label="Danh sách thông báo">
      <div className="notif-head">
        <strong>Thông báo</strong>
        <button className="notif-close" onClick={toggle} aria-label="Đóng thông báo">×</button>
        {unread > 0 && <button className="notif-readall" onClick={readAll}><CheckCheck size={14} /> Đánh dấu đã đọc hết</button>}
      </div>
      {items.length ? <ul className="notif-list">
        {items.map((item) => <li key={item.id}>
          <button className={`notif-item ${item.read_at ? "" : "unread"}`} onClick={() => openItem(item)}>
            <strong>{item.title}</strong>
            {item.body && <p>{item.body}</p>}
            <small>{timeLabel(item.created_at)}</small>
          </button>
        </li>)}
      </ul> : <p className="notif-empty">Chưa có thông báo nào.</p>}
    </div>}
  </div>;
}
