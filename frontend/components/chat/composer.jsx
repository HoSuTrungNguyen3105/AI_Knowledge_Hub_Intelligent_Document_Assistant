"use client";

import { useState } from "react";
import { ArrowUp, CircleAlert, Square } from "lucide-react";

export function Composer({ disabled, isStreaming, onSend, onStop, error }) {
  const [value, setValue] = useState("");

  function submit(event) {
    event.preventDefault();
    const text = value.trim();
    if (!text || disabled || isStreaming) return;
    onSend(text);
    setValue("");
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(event);
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      {error && <p className="composer-error" role="alert"><CircleAlert size={15} />{error}</p>}
      <div className="composer-row">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={disabled ? "Chọn provider và model để bắt đầu…" : "Nhập tin nhắn… (Enter để gửi, Shift+Enter để xuống dòng)"}
          aria-label="Nội dung tin nhắn"
          disabled={disabled || isStreaming}
        />
        {isStreaming ? (
          <button type="button" className="button secondary composer-stop" onClick={onStop}><Square size={15} />Dừng</button>
        ) : (
          <button type="submit" className="button primary composer-send" disabled={disabled || !value.trim()} aria-label="Gửi tin nhắn"><ArrowUp size={17} /></button>
        )}
      </div>
    </form>
  );
}