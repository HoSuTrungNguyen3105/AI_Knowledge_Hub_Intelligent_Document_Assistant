"use client";

import { useEffect, useRef } from "react";
import { CircleAlert, LoaderCircle, MessagesSquare } from "lucide-react";
import { MessageItem } from "./message-item";
import { Markdown } from "./markdown";

export function MessageList({ messages, streaming, canRegenerate, onRegenerate, loading, error, onRetry }) {
  const bottom = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: "end" }); }, [messages, streaming]);

  if (loading) return <div className="thread-state" role="status"><LoaderCircle size={22} className="spin" /><p>Đang tải hội thoại…</p></div>;
  if (error) return <div className="thread-state"><div className="error-panel" role="alert"><CircleAlert size={22} /><div><h2>Chưa tải được hội thoại</h2><p>{error}</p></div><button type="button" className="button secondary" onClick={onRetry}>Thử lại</button></div></div>;

  const empty = messages.length === 0 && !streaming;
  return (
    <div className="message-list">
      {empty ? (
        <div className="thread-empty"><span className="soft-icon"><MessagesSquare size={24} /></span><h2>Bắt đầu trò chuyện</h2><p>Gửi tin nhắn đầu tiên cho model đã chọn. Nội dung được lưu riêng cho tài khoản của bạn.</p></div>
      ) : (
        <>
          {messages.map((message, index) => (
            <MessageItem key={message.id} message={message} canRegenerate={canRegenerate && index === messages.length - 1 && message.role === "assistant"} onRegenerate={onRegenerate} />
          ))}
          {streaming && (
            <article className="message assistant streaming">
              <div className="message-role">AI</div>
              <div className="message-body">
                {streaming.text ? <Markdown content={streaming.text} /> : <p className="message-thinking"><LoaderCircle size={14} className="spin" />Đang soạn câu trả lời…</p>}
              </div>
            </article>
          )}
        </>
      )}
      <div ref={bottom} />
    </div>
  );
}