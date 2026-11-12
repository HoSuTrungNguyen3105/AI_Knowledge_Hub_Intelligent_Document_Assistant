"use client";

import { useState } from "react";
import { Check, LoaderCircle, Pencil, SlidersHorizontal, Trash2, X } from "lucide-react";
import { ConfigEditor } from "./config-editor";
import { MessageList } from "./message-list";
import { Composer } from "./composer";
import { ConfirmDialog } from "../confirm-dialog";

export function ConversationView({ controller }) {
  const {
    thread, messages, streaming, isStreaming, streamError, canRegenerate, busy,
    confirmDelete, setConfirmDelete, sendMessage, stop, regenerate,
    renameConversation, updateConfig, deleteConversation, reloadThread,
  } = controller;
  const [showConfig, setShowConfig] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const conversation = thread.data;

  function startRename() { setTitleDraft(conversation?.title ?? ""); setRenaming(true); }
  function saveRename(event) {
    event.preventDefault();
    const title = titleDraft.trim();
    if (!title || busy) return;
    renameConversation(title);
    setRenaming(false);
  }

  return (
    <section className="conversation-view">
      {conversation && (
        <header className="conversation-header">
          <div className="conversation-title">
            {renaming ? (
              <form className="rename-form" onSubmit={saveRename}>
                <input value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} maxLength={200} aria-label="Tên hội thoại" autoFocus disabled={busy === "rename"} />
                <button type="submit" className="icon-button" aria-label="Lưu tên" disabled={busy === "rename"}>{busy === "rename" ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}</button>
                <button type="button" className="icon-button" aria-label="Hủy đổi tên" onClick={() => setRenaming(false)} disabled={busy === "rename"}><X size={16} /></button>
              </form>
            ) : (
              <h2>{conversation.title}</h2>
            )}
            <span className="conversation-model">{conversation.provider} · {conversation.model}</span>
          </div>
          <div className="conversation-tools">
            <button type="button" className={`icon-button ${showConfig ? "active" : ""}`} onClick={() => setShowConfig((value) => !value)} aria-label="Cấu hình hội thoại" aria-expanded={showConfig} title="Cấu hình"><SlidersHorizontal size={17} /></button>
            <button type="button" className="icon-button" onClick={startRename} aria-label="Đổi tên hội thoại" title="Đổi tên" disabled={Boolean(busy)}><Pencil size={17} /></button>
            <button type="button" className="icon-button danger" onClick={() => setConfirmDelete(true)} aria-label="Xóa hội thoại" title="Xóa" disabled={Boolean(busy)}><Trash2 size={17} /></button>
          </div>
        </header>
      )}
      {showConfig && conversation && <ConfigEditor key={conversation.id} conversation={conversation} busy={busy === "config"} onSave={updateConfig} />}
      <MessageList messages={messages} streaming={streaming} canRegenerate={canRegenerate} onRegenerate={regenerate} loading={thread.loading} error={thread.error} onRetry={reloadThread} />
      <Composer disabled={!conversation || thread.loading || Boolean(busy)} isStreaming={isStreaming} onSend={sendMessage} onStop={stop} error={streamError} />
      <ConfirmDialog open={confirmDelete} title="Xóa hội thoại này?" busy={busy === "delete"} onClose={() => setConfirmDelete(false)} onConfirm={deleteConversation} confirmLabel="Xóa hội thoại">
        <p>Toàn bộ tin nhắn của hội thoại sẽ bị xóa khỏi tài khoản của bạn.</p>
        <p>Hội thoại và dữ liệu của tài khoản khác không bị ảnh hưởng. Thao tác này không thể hoàn tác.</p>
      </ConfirmDialog>
    </section>
  );
}