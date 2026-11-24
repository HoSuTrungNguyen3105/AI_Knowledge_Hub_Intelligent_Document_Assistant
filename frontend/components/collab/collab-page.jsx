"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Handshake, Plus, RefreshCw, Send, Square, Trash2, Users } from "lucide-react";
import { agentsService } from "../../services/agents";
import { collabService, getCollabError } from "../../services/collab";
import { getErrorMessage } from "../../services/api";
import { ConfirmDialog } from "../confirm-dialog";

const timeLabel = (iso) => new Date(iso).toLocaleString("vi-VN", {
  hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
});

// Collaboration rooms (NEXORA Module 03): pick member Agents, post
// messages, @mention members to have them answer in the room. Sending
// is non-streamed in v1 — the reply lands when the Agent finishes.
export function CollabPage() {
  const [agents, setAgents] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [roomId, setRoomId] = useState(null);
  const [room, setRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newMembers, setNewMembers] = useState([]);
  const [memberDraft, setMemberDraft] = useState([]);
  const [draft, setDraft] = useState("");
  const [mentions, setMentions] = useState([]);
  const [sending, setSending] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const abortRef = useRef(null);
  const threadRef = useRef(null);

  const loadRooms = useCallback(async (signal) => {
    try {
      const [roomList, agentList] = await Promise.all([
        collabService.listRooms(signal),
        agentsService.list(signal),
      ]);
      setRooms(roomList);
      setAgents(agentList);
      setRoomId((current) => current && roomList.some((r) => r.id === current)
        ? current
        : (roomList[0]?.id ?? null));
      setError("");
    } catch (e) {
      if (e?.name !== "AbortError") setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadRooms(controller.signal);
    return () => controller.abort();
  }, [loadRooms]);

  const loadRoom = useCallback(async (signal) => {
    if (!roomId) { setRoom(null); setMessages([]); return; }
    try {
      const [detail, msgs] = await Promise.all([
        collabService.getRoom(roomId, signal),
        collabService.listMessages(roomId, signal),
      ]);
      setRoom(detail);
      setMemberDraft(detail.agent_ids);
      setMessages(msgs);
    } catch (e) {
      if (e?.name !== "AbortError") setError(getCollabError(e));
    }
  }, [roomId]);

  useEffect(() => {
    const controller = new AbortController();
    loadRoom(controller.signal);
    return () => controller.abort();
  }, [loadRoom]);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  const toggleId = (list, setList, id) =>
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const createRoom = async () => {
    if (!newTitle.trim()) return;
    try {
      const created = await collabService.createRoom({ title: newTitle.trim(), agent_ids: newMembers });
      setNewTitle("");
      setNewMembers([]);
      await loadRooms();
      setRoomId(created.id);
    } catch (e) { setError(getCollabError(e)); }
  };

  const saveMembers = async () => {
    if (!room) return;
    try {
      const updated = await collabService.patchRoom(room.id, { agent_ids: memberDraft });
      setRoom(updated);
      setMentions((list) => list.filter((id) => memberDraft.includes(id)));
      await loadRooms();
    } catch (e) { setError(getCollabError(e)); }
  };

  const removeRoom = async () => {
    if (!room) return;
    try {
      await collabService.deleteRoom(room.id);
      setConfirmDelete(false);
      setRoomId(null);
      await loadRooms();
    } catch (e) { setError(getCollabError(e)); }
  };

  const send = async () => {
    if (!room || !draft.trim() || sending) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setSending(true);
    try {
      const created = await collabService.postMessage(
        room.id,
        { content: draft.trim(), mention_agent_ids: mentions },
        controller.signal
      );
      setMessages((list) => [...list, ...created]);
      setDraft("");
      setMentions([]);
      const detail = await collabService.getRoom(room.id);
      setRoom(detail);
    } catch (e) {
      if (e?.name === "AbortError" || e?.code === "ERR_CANCELED") {
        setDraft("");
        setMentions([]);
        await loadRoom(); // a started Agent may still have replied
      } else {
        setError(getCollabError(e));
      }
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  };

  return <div className="wf-page">
    <div className="wf-header">
      <div>
        <h1><Handshake size={22} /> Phòng hợp tác</h1>
        <p className="muted">Phòng làm việc chung với các Agent của bạn: đăng tin, nhắc @Agent thành viên để Agent trả lời ngay trong phòng với ngữ cảnh cuộc trò chuyện.</p>
      </div>
      <button className="wf-btn" type="button" onClick={() => { loadRooms(); loadRoom(); }}>
        <RefreshCw size={15} /> Làm mới</button>
    </div>

    {error && <p className="wf-error" role="alert">{error}</p>}
    {loading ? <p className="wf-empty">Đang tải phòng…</p> : <div style={{ display: "grid", gridTemplateColumns: "minmax(250px, 320px) minmax(0, 1fr)", gap: 14, alignItems: "start" }}>
      <div>
        <div className="wf-card">
          <h3 style={{ marginTop: 0 }}>Tạo phòng mới</h3>
          <label style={{ display: "block", marginBottom: 8 }}>Tên phòng
            <input value={newTitle} maxLength={200} onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Ví dụ: Phòng nội dung" style={{ display: "block", width: "100%", marginTop: 4 }} /></label>
          <p className="muted" style={{ fontSize: 12.5, margin: "6px 0" }}><Users size={13} /> Agent thành viên:</p>
          {agents.length ? agents.map((a) => <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
            <input type="checkbox" checked={newMembers.includes(a.id)}
              onChange={() => toggleId(newMembers, setNewMembers, a.id)} /> {a.name}
            <small className="muted">{a.provider} · {a.model}</small></label>)
            : <p className="muted" style={{ fontSize: 12.5 }}>Chưa có Agent nào — tạo Agent ở Agent Studio trước.</p>}
          <button className="wf-btn primary" type="button" disabled={!newTitle.trim()} onClick={createRoom} style={{ marginTop: 10 }}>
            <Plus size={15} /> Tạo phòng</button>
        </div>
        <div className="wf-list" style={{ marginTop: 12 }}>
          {rooms.map((r) => <button key={r.id} type="button" onClick={() => setRoomId(r.id)}
            className={`wf-btn ${roomId === r.id ? "primary" : ""}`}
            style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6 }}>
            {r.title} <small>· {r.message_count} tin</small></button>)}
          {!rooms.length && <p className="wf-empty">Chưa có phòng nào.</p>}
        </div>
      </div>

      {!room ? <p className="wf-empty">Chọn hoặc tạo một phòng để bắt đầu.</p> : <div>
        <div className="wf-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>{room.title}</h3>
            <button className="wf-btn danger" type="button" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={14} /> Xoá phòng</button>
          </div>
          <p className="muted" style={{ fontSize: 12.5 }}>
            {room.message_count} tin nhắn · Token đã dùng: {(room.total_input_tokens + room.total_output_tokens).toLocaleString("vi-VN")}
            {" "}(vào {room.total_input_tokens.toLocaleString("vi-VN")} / ra {room.total_output_tokens.toLocaleString("vi-VN")})
          </p>
          <div ref={threadRef} style={{ maxHeight: 430, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10, padding: "6px 2px" }}>
            {messages.length ? messages.map((m) => <div key={m.id} className="wf-msg">
              <span className="wf-msg-avatar" style={{ background: m.sender_type === "agent" ? "#7c3aed" : "#0ea5e9" }}>
                <Bot size={17} /></span>
              <div className="wf-msg-body">
                <div className="wf-msg-meta"><b>{m.sender_type === "agent" ? (m.agent_name || "Agent") : "Bạn"}</b>
                  <time>{timeLabel(m.created_at)}</time>
                  {m.status === "error" && <span className="wf-msg-type">Lỗi: {m.error_code || "không rõ"}</span>}</div>
                <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 13.5 }}>
                  {m.status === "error" ? "(Agent không trả lời được lần này)" : m.content}</div>
              </div>
            </div>) : <p className="wf-empty">Phòng chưa có tin nhắn nào.</p>}
            {sending && <p className="muted" role="status">Agent đang trả lời… (có thể mất vài chục giây)</p>}
          </div>
          <div className="wf-chip-row" style={{ margin: "8px 0" }}>
            <span className="muted" style={{ fontSize: 12.5, alignSelf: "center" }}>Nhắc tới:</span>
            {room.agents.map((a) => <button key={a.id} type="button" aria-pressed={mentions.includes(a.id)}
              className={`wf-chip${mentions.includes(a.id) ? " selected" : ""}`}
              onClick={() => toggleId(mentions, setMentions, a.id)}>@{a.name}</button>)}
            {!room.agents.length && <span className="muted" style={{ fontSize: 12.5 }}>Phòng chưa có Agent thành viên — thêm ở panel dưới.</span>}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <textarea rows={3} value={draft} maxLength={8000} onChange={(e) => setDraft(e.target.value)}
              placeholder="Viết tin nhắn… chọn @Agent ở trên nếu muốn Agent trả lời"
              style={{ flex: 1 }} />
            {sending
              ? <button className="wf-btn" type="button" onClick={() => abortRef.current?.abort()}>
                  <Square size={15} /> Dừng chờ</button>
              : <button className="wf-btn primary" type="button" disabled={!draft.trim()} onClick={send}>
                  <Send size={15} /> Gửi</button>}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
            &quot;Dừng chờ&quot; chỉ ngắt việc chờ phía bạn — Agent đã bắt đầu chạy vẫn hoàn tất và câu trả lời sẽ có trong phòng khi tải lại.
          </p>
        </div>

        <div className="wf-card" style={{ marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}><Users size={15} /> Thành viên của phòng</h3>
          {agents.map((a) => <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
            <input type="checkbox" checked={memberDraft.includes(a.id)}
              onChange={() => toggleId(memberDraft, setMemberDraft, a.id)} /> {a.name}
            <small className="muted">{a.provider} · {a.model}</small></label>)}
          <button className="wf-btn" type="button" onClick={saveMembers} style={{ marginTop: 8 }}>Lưu thành viên</button>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
            Chỉ Agent thành viên mới được @nhắc trong phòng này. Đang có: {room.agents.map((a) => a.name).join(", ") || "chưa ai"}.
          </p>
        </div>
      </div>}
    </div>}

    {room && <ConfirmDialog
      open={confirmDelete}
      title="Xoá phòng hợp tác"
      confirmLabel="Xoá phòng"
      onConfirm={removeRoom}
      onClose={() => setConfirmDelete(false)}>
      Xoá phòng &quot;{room.title}&quot; cùng toàn bộ tin nhắn trong phòng? Không thể hoàn tác.
    </ConfirmDialog>}
  </div>;
}
