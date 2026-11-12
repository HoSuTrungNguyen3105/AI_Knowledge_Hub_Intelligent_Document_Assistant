"use client";

import { useState } from "react";
import { Check, CircleAlert, Copy, RotateCw } from "lucide-react";
import { Markdown } from "./markdown";
import { formatLatency, formatTokens } from "../../utils/chat";

export function MessageItem({ message, canRegenerate, onRegenerate }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className={`message ${isUser ? "user" : "assistant"} status-${message.status}`}>
      <div className="message-role">{isUser ? "Bạn" : message.model || "AI"}</div>
      <div className="message-body">
        {isUser ? <p className="message-text">{message.content}</p> : <Markdown content={message.content} />}
        {message.status === "error" && (
          <p className="message-flag error"><CircleAlert size={14} />Không tạo được nội dung{message.error_code ? ` · ${message.error_code}` : ""}</p>
        )}
        {message.status === "stopped" && <p className="message-flag stopped">Đã dừng giữa chừng</p>}
        {!isUser && message.status === "success" && (
          <p className="message-meta">
            <span>{formatTokens(message.input_tokens)} token vào</span>
            <span>{formatTokens(message.output_tokens)} token ra</span>
            {message.latency_ms !== null && message.latency_ms !== undefined && <span>{formatLatency(message.latency_ms)}</span>}
          </p>
        )}
      </div>
      <div className="message-actions">
        <button type="button" className="icon-button" onClick={copy} aria-label="Sao chép tin nhắn" title="Sao chép">
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
        {!isUser && canRegenerate && (
          <button type="button" className="icon-button" onClick={onRegenerate} aria-label="Tạo lại câu trả lời" title="Tạo lại">
            <RotateCw size={16} />
          </button>
        )}
      </div>
    </article>
  );
}