"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot, Copy, CornerUpLeft, Download, FileDown, Handshake, Plus, RefreshCw,
  RotateCcw, Send, Sparkles, Square, Trash2, Users, X,
} from "lucide-react";
import { agentsService } from "../../services/agents";
import { collabService, getCollabError } from "../../services/collab";
import { getErrorMessage } from "../../services/api";
import { ConfirmDialog } from "../confirm-dialog";

const timeLabel = (iso) => new Date(iso).toLocaleString("vi-VN", {
  hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
});

const STOP_REASONS = {
  turn_limit: "Đạt giới hạn lượt",
  agent_concluded: "Agent đã kết luận",
  loop_detected: "Dừng vì phát hiện lặp nội dung",
  cancelled_by_user: "Người dùng đã dừng",
  no_eligible_agent: "Không còn Agent phù hợp",
  moderator_summarized: "Moderator đã tổng hợp",
  all_agents_failed: "Mọi Agent đều lỗi",
};

const RUN_STATUS = {
  running: "Đang chạy",
  completed: "Hoàn thành",
  failed: "Thất bại",
  cancelled: "Đã dừng",
};

const TASK_STATUS = {
  queued: "Đang chờ",
  running: "Đang xử lý",
  completed: "Hoàn thành",
  failed: "Thất bại",
  cancelled: "Đã hủy",
};

const sizeLabel = (bytes) => (bytes < 1024
  ? `${bytes} B`
  : `${(bytes / 1024).toFixed(1)} KB`);

// Collaboration rooms: member Agents discuss in one room with a shared,
// database-backed context — an Agent mentioned later reads what the
// earlier Agents answered, replies link to the message they answer,
// auto mode runs a moderated discussion, and results export to files.
export function CollabPage() {
  const [agents, setAgents] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [roomId, setRoomId] = useState(null);
  const [room, setRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [runs, setRuns] = useState([]);
  const [runDetail, setRunDetail] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newMembers, setNewMembers] = useState([]);
  const [newMode, setNewMode] = useState("directed");
  const [newModerator, setNewModerator] = useState("");
  const [newMaxTurns, setNewMaxTurns] = useState(4);
  const [memberDraft, setMemberDraft] = useState([]);
  const [modeDraft, setModeDraft] = useState("directed");
  const [moderatorDraft, setModeratorDraft] = useState("");
  const [maxTurnsDraft, setMaxTurnsDraft] = useState(4);
  const [handoffDraft, setHandoffDraft] = useState(true);
  const [draft, setDraft] = useState("");
  const [mentions, setMentions] = useState([]);
  const [replyTo, setReplyTo] = useState(null);
  const [sending, setSending] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const abortRef = useRef(null);
  const threadRef = useRef(null);
  const inputRef = useRef(null);

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
    if (!roomId) {
      setRoom(null); setMessages([]); setRuns([]); setArtifacts([]); setRunDetail(null);
      return;
    }
    try {
      const [detail, msgs] = await Promise.all([
        collabService.getRoom(roomId, signal),
        collabService.listMessages(roomId, signal),
      ]);
      setRoom(detail);
      setMemberDraft(detail.agent_ids);
      setModeDraft(detail.mode || "directed");
      setModeratorDraft(detail.moderator_agent_id || "");
      setMaxTurnsDraft(detail.max_turns || 4);
      setHandoffDraft(detail.allow_handoff !== false);
      setMessages(msgs);
      setReplyTo(null);
      const [runList, artifactList] = await Promise.all([
        collabService.listRuns(roomId, signal).catch(() => []),
        collabService.listArtifacts(roomId, signal).catch(() => []),
      ]);
      setRuns(runList);
      setArtifacts(artifactList);
      if (runList.length) {
        const detailRun = await collabService.getRun(runList[0].id, signal).catch(() => null);
        setRunDetail(detailRun);
      } else {
        setRunDetail(null);
      }
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

  const byId = Object.fromEntries(messages.map((m) => [m.id, m]));
  const authorOf = (m) => (m.sender_type === "agent" ? (m.agent_name || "Agent") : "Bạn");

  const createRoom = async () => {
    if (!newTitle.trim()) return;
    try {
      const created = await collabService.createRoom({
        title: newTitle.trim(),
        agent_ids: newMembers,
        mode: newMode,
        moderator_agent_id: newModerator || null,
        max_turns: Math.min(10, Math.max(1, Number(newMaxTurns) || 4)),
      });
      setNewTitle("");
      setNewMembers([]);
      setNewModerator("");
      await loadRooms();
      setRoomId(created.id);
    } catch (e) { setError(getCollabError(e)); }
  };

  const saveSettings = async () => {
    if (!room) return;
    try {
      const updated = await collabService.patchRoom(room.id, {
        agent_ids: memberDraft,
        mode: modeDraft,
        moderator_agent_id: moderatorDraft || null,
        max_turns: Math.min(10, Math.max(1, Number(maxTurnsDraft) || 4)),
        allow_handoff: handoffDraft,
      });
      setRoom(updated);
      setMentions((list) => list.filter((id) => memberDraft.includes(id)));
      setNotice("Đã lưu cài đặt phòng.");
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
    setNotice("");
    try {
      const result = await collabService.postMessageFull(
        room.id,
        {
          content: draft.trim(),
          mention_agent_ids: mentions,
          reply_to_message_id: replyTo?.id || null,
        },
        controller.signal
      );
      setMessages((list) => [...list, ...result.messages]);
      setDraft("");
      setMentions([]);
      setReplyTo(null);
      const [detail, runList] = await Promise.all([
        collabService.getRoom(room.id),
        collabService.listRuns(room.id).catch(() => runs),
      ]);
      setRoom(detail);
      setRuns(runList);
      if (result.run) {
        const detailRun = await collabService.getRun(result.run.id).catch(() => null);
        setRunDetail(detailRun);
      }
    } catch (e) {
      if (e?.name === "AbortError" || e?.code === "ERR_CANCELED") {
        setDraft("");
        setMentions([]);
        setReplyTo(null);
        await loadRoom(); // a started Agent may still have replied
      } else {
        setError(getCollabError(e));
      }
    } finally {
      setSending(false);
      abortRef.current = null;
    }
  };

  const startReply = (message, rebuttal) => {
    setReplyTo(message);
    if (rebuttal && !draft.trim()) setDraft("Hãy phản biện nội dung này: ");
    inputRef.current?.focus();
  };

  const copyMessage = async (message) => {
    try {
      await navigator.clipboard.writeText(message.content || "");
      setNotice("Đã sao chép nội dung tin nhắn.");
    } catch {
      setError("Trình duyệt không cho sao chép tự động.");
    }
  };

  const summarize = async () => {
    if (!room || busyAction) return;
    setBusyAction("summarize");
    try {
      const message = await collabService.summarize(room.id, room.moderator_agent_id || null);
      setMessages((list) => [...list, message]);
      setNotice("Moderator đã tổng hợp và đăng kết luận vào phòng.");
    } catch (e) { setError(getCollabError(e)); } finally { setBusyAction(""); }
  };

  const retryRun = async () => {
    if (!runDetail || busyAction) return;
    setBusyAction("retry");
    try {
      const detail = await collabService.retryRun(runDetail.run.id);
      setRunDetail(detail);
      await loadRoom();
      setNotice("Đã chạy lại các tác vụ lỗi.");
    } catch (e) { setError(getCollabError(e)); } finally { setBusyAction(""); }
  };

  const cancelRun = async () => {
    if (!runDetail || busyAction) return;
    setBusyAction("cancel");
    try {
      await collabService.cancelRun(runDetail.run.id);
      const detail = await collabService.getRun(runDetail.run.id).catch(() => null);
      setRunDetail(detail);
    } catch (e) { setError(getCollabError(e)); } finally { setBusyAction(""); }
  };

  const exportRoom = async () => {
    if (!room || busyAction) return;
    setBusyAction("export");
    try {
      const created = await collabService.exportRoom(room.id, ["md", "json", "zip"]);
      setArtifacts((list) => [...created, ...list]);
      setNotice(`Đã tạo ${created.length} file kết quả — xem ở mục File kết quả bên dưới.`);
    } catch (e) { setError(getCollabError(e)); } finally { setBusyAction(""); }
  };

  const download = async (artifact) => {
    try {
      const blob = await collabService.downloadArtifact(artifact.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.name;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(getCollabError(e)); }
  };

  const removeArtifact = async (artifact) => {
    try {
      await collabService.deleteArtifact(artifact.id);
      setArtifacts((list) => list.filter((a) => a.id !== artifact.id));
    } catch (e) { setError(getCollabError(e)); }
  };

  const openRun = async (run) => {
    const detail = await collabService.getRun(run.id).catch(() => null);
    setRunDetail(detail);
  };

  const receivers = room?.mode === "auto" && !mentions.length
    ? "các Agent tự thảo luận theo chế độ Tự động"
    : mentions.length
      ? room.agents.filter((a) => mentions.includes(a.id)).map((a) => a.name).join(", ")
      : "không Agent nào (tin nhắn chung)";

  return <div className="wf-page">
    <div className="wf-header">
      <div>
        <h1><Handshake size={22} /> Phòng hợp tác</h1>
        <p className="muted">Phòng làm việc chung của các Agent: mọi Agent đều đọc được lịch sử phòng — Agent được nhắc sau sẽ thấy và phản biện được kết quả của Agent trước.</p>
      </div>
      <button className="wf-btn" type="button" onClick={() => { loadRooms(); loadRoom(); }}>
        <RefreshCw size={15} /> Làm mới</button>
    </div>

    {error && <p className="wf-error" role="alert">{error}</p>}
    {notice && <p className="wf-success" role="status">{notice}</p>}
    {loading ? <p className="wf-empty">Đang tải phòng…</p> : <div style={{ display: "grid", gridTemplateColumns: "minmax(250px, 320px) minmax(0, 1fr)", gap: 14, alignItems: "start" }}>
      <div>
        <div className="wf-card">
          <h3 style={{ marginTop: 0 }}>Tạo phòng mới</h3>
          <label style={{ display: "block", marginBottom: 8 }}>Tên phòng
            <input value={newTitle} maxLength={200} onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Ví dụ: Phòng nội dung" style={{ display: "block", width: "100%", marginTop: 4 }} /></label>
          <label style={{ display: "block", marginBottom: 8 }}>Chế độ
            <select value={newMode} onChange={(e) => setNewMode(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}>
              <option value="directed">Trao đổi theo chỉ định (@mention)</option>
              <option value="auto">Tự động thảo luận</option>
            </select></label>
          <p className="muted" style={{ fontSize: 12.5, margin: "6px 0" }}><Users size={13} /> Agent thành viên:</p>
          {agents.length ? agents.map((a) => <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
            <input type="checkbox" checked={newMembers.includes(a.id)}
              onChange={() => toggleId(newMembers, setNewMembers, a.id)} /> {a.name}
            <small className="muted">{a.provider} · {a.model}</small></label>)
            : <p className="muted" style={{ fontSize: 12.5 }}>Chưa có Agent nào — tạo Agent ở Agent Studio trước.</p>}
          <label style={{ display: "block", margin: "8px 0" }}>Moderator (điều phối &amp; tổng hợp)
            <select value={newModerator} onChange={(e) => setNewModerator(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}>
              <option value="">— Không chọn —</option>
              {agents.filter((a) => newMembers.includes(a.id)).map((a) =>
                <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></label>
          <label style={{ display: "block", marginBottom: 8 }}>Giới hạn lượt nói mỗi lần chạy (1–10)
            <input type="number" min={1} max={10} value={newMaxTurns}
              onChange={(e) => setNewMaxTurns(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }} /></label>
          <button className="wf-btn primary" type="button" disabled={!newTitle.trim()} onClick={createRoom} style={{ marginTop: 10 }}>
            <Plus size={15} /> Tạo phòng</button>
        </div>
        <div className="wf-list" style={{ marginTop: 12 }}>
          {rooms.map((r) => <button key={r.id} type="button" onClick={() => setRoomId(r.id)}
            className={`wf-btn ${roomId === r.id ? "primary" : ""}`}
            style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6 }}>
            {r.title} <small>· {r.message_count} tin · {r.mode === "auto" ? "Tự động" : "Chỉ định"}</small></button>)}
          {!rooms.length && <p className="wf-empty">Chưa có phòng nào.</p>}
        </div>
      </div>

      {!room ? <p className="wf-empty">Chọn hoặc tạo một phòng để bắt đầu.</p> : <div>
        <div className="wf-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>{room.title}
              <span className="wf-badge" style={{ marginLeft: 8 }}>
                {room.mode === "auto" ? "Tự động thảo luận" : "Theo chỉ định"}</span></h3>
            <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="wf-btn" type="button" disabled={busyAction === "summarize"} onClick={summarize}>
                <Sparkles size={14} /> Tổng hợp ngay</button>
              <button className="wf-btn" type="button" disabled={busyAction === "export"} onClick={exportRoom}>
                <FileDown size={14} /> Xuất kết quả</button>
              <button className="wf-btn danger" type="button" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={14} /> Xoá phòng</button>
            </span>
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
                <div className="wf-msg-meta"><b>{authorOf(m)}</b>
                  {m.sequence > 0 && <span className="muted">#{m.sequence}</span>}
                  {m.sender_type === "agent" && m.provider && <span className="muted">{m.provider} · {m.model}</span>}
                  {m.is_summary && <span className="wf-badge">Tổng hợp</span>}
                  <time>{timeLabel(m.created_at)}</time>
                  {m.status === "error" && <span className="wf-msg-type">Lỗi: {m.error_code || "không rõ"}</span>}</div>
                {m.reply_to_message_id && byId[m.reply_to_message_id] && (
                  <div className="wf-reply-quote">
                    <CornerUpLeft size={12} /> Trả lời #{byId[m.reply_to_message_id].sequence || "?"} của{" "}
                    {authorOf(byId[m.reply_to_message_id])}: {(byId[m.reply_to_message_id].content || "").slice(0, 120)}
                  </div>)}
                <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 13.5 }}>
                  {m.status === "error"
                    ? (m.content || "(Agent không trả lời được lần này — xem mã lỗi ở trên, hoặc chạy lại ở panel Lượt chạy)")
                    : m.content}</div>
                <div className="wf-msg-actions">
                  <button type="button" onClick={() => startReply(m, false)}>
                    <CornerUpLeft size={12} /> Trả lời</button>
                  {m.sender_type === "agent" && <button type="button" onClick={() => startReply(m, true)}>
                    Nhờ phản biện</button>}
                  <button type="button" onClick={() => copyMessage(m)}>
                    <Copy size={12} /> Sao chép</button>
                  {(m.input_tokens || m.output_tokens) ? <span className="muted">
                    {((m.input_tokens || 0) + (m.output_tokens || 0)).toLocaleString("vi-VN")} token</span> : null}
                </div>
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
          {replyTo && <div className="wf-reply-bar">
            <span>Đang trả lời #{replyTo.sequence || "?"} của {authorOf(replyTo)}: {(replyTo.content || "").slice(0, 100)}</span>
            <button type="button" onClick={() => setReplyTo(null)} aria-label="Huỷ trả lời"><X size={13} /></button>
          </div>}
          <p className="muted" style={{ fontSize: 12.5, margin: "4px 0" }}>
            Agent sẽ nhận tin này: <b>{receivers}</b></p>
          <div style={{ display: "flex", gap: 8 }}>
            <textarea ref={inputRef} rows={3} value={draft} maxLength={8000} onChange={(e) => setDraft(e.target.value)}
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
          <h3 style={{ marginTop: 0 }}>Lượt chạy gần nhất</h3>
          {!runs.length ? <p className="wf-empty">Chưa có lượt chạy nào — nhắc @Agent hoặc gửi tin ở phòng Tự động.</p> : <>
            <div className="wf-chip-row" style={{ marginBottom: 8 }}>
              {runs.slice(0, 6).map((r) => <button key={r.id} type="button"
                className={`wf-chip${runDetail?.run.id === r.id ? " selected" : ""}`}
                onClick={() => openRun(r)}>
                {r.mode === "auto" ? "Tự động" : "Chỉ định"} · {RUN_STATUS[r.status] || r.status} · {r.turn_count} lượt</button>)}
            </div>
            {runDetail && <div>
              <p className="muted" style={{ fontSize: 12.5, margin: "4px 0" }}>
                Trạng thái: <b>{RUN_STATUS[runDetail.run.status] || runDetail.run.status}</b>
                {runDetail.run.stop_reason && <> · Lý do dừng: {STOP_REASONS[runDetail.run.stop_reason] || runDetail.run.stop_reason}</>}
                {" "}· Token: {(runDetail.run.total_input_tokens + runDetail.run.total_output_tokens).toLocaleString("vi-VN")}
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {runDetail.tasks.map((t) => <div key={t.id} className="wf-run-task">
                  <span><b>{t.agent_name || "Agent"}</b> <span className="muted">
                    ({t.assigned_by === "user" ? "bạn giao" : t.assigned_by === "moderator" ? "Moderator" : "hệ thống giao"})</span></span>
                  <span className="muted">{TASK_STATUS[t.status] || t.status}
                    {t.attempt > 1 && ` · lần thử ${t.attempt}`}
                    {t.error_code && ` · ${t.error_code}`}</span>
                </div>)}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                {runDetail.tasks.some((t) => t.status === "failed") && (
                  <button className="wf-btn" type="button" disabled={busyAction === "retry"} onClick={retryRun}>
                    <RotateCcw size={14} /> Chạy lại phần lỗi</button>)}
                {runDetail.run.status === "running" && (
                  <button className="wf-btn" type="button" disabled={busyAction === "cancel"} onClick={cancelRun}>
                    <Square size={14} /> Dừng run</button>)}
              </div>
            </div>}
          </>}
        </div>

        <div className="wf-card" style={{ marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}><FileDown size={15} /> File kết quả</h3>
          {!artifacts.length ? <p className="wf-empty">Chưa có file nào — bấm &quot;Xuất kết quả&quot; ở đầu phòng để tạo báo cáo .md, results.json và gói ZIP bàn giao.</p>
            : <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {artifacts.map((a) => <div key={a.id} className="wf-run-task">
                <span><b>{a.name}</b> <span className="muted">· {sizeLabel(a.size)} · {timeLabel(a.created_at)}</span></span>
                <span style={{ display: "flex", gap: 6 }}>
                  <button className="wf-btn" type="button" onClick={() => download(a)}>
                    <Download size={13} /> Tải</button>
                  <button className="wf-btn" type="button" onClick={() => removeArtifact(a)}>
                    <Trash2 size={13} /></button>
                </span>
              </div>)}
            </div>}
        </div>

        <div className="wf-card" style={{ marginTop: 12 }}>
          <h3 style={{ marginTop: 0 }}><Users size={15} /> Thành viên &amp; cài đặt phòng</h3>
          {agents.map((a) => <label key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
            <input type="checkbox" checked={memberDraft.includes(a.id)}
              onChange={() => toggleId(memberDraft, setMemberDraft, a.id)} /> {a.name}
            <small className="muted">{a.provider} · {a.model}</small>
            {room.moderator_agent_id === a.id && <span className="wf-badge">Moderator</span>}</label>)}
          <label style={{ display: "block", margin: "10px 0 6px" }}>Chế độ
            <select value={modeDraft} onChange={(e) => setModeDraft(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}>
              <option value="directed">Trao đổi theo chỉ định (@mention)</option>
              <option value="auto">Tự động thảo luận</option>
            </select></label>
          <label style={{ display: "block", marginBottom: 6 }}>Moderator
            <select value={moderatorDraft} onChange={(e) => setModeratorDraft(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}>
              <option value="">— Không chọn —</option>
              {agents.filter((a) => memberDraft.includes(a.id)).map((a) =>
                <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></label>
          <label style={{ display: "block", marginBottom: 6 }}>Giới hạn lượt nói mỗi lần chạy (1–10)
            <input type="number" min={1} max={10} value={maxTurnsDraft}
              onChange={(e) => setMaxTurnsDraft(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }} /></label>
          <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0" }}>
            <input type="checkbox" checked={handoffDraft} onChange={() => setHandoffDraft(!handoffDraft)} />
            Cho phép Agent chuyển giao nhiệm vụ cho nhau</label>
          <button className="wf-btn" type="button" onClick={saveSettings} style={{ marginTop: 8 }}>Lưu cài đặt</button>
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
      Xoá phòng &quot;{room.title}&quot; cùng toàn bộ tin nhắn, lượt chạy và file kết quả trong phòng? Không thể hoàn tác.
    </ConfirmDialog>}
  </div>;
}
