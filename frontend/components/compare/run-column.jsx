"use client";

import { useState } from "react";
import { Check, CircleAlert, Copy, LoaderCircle } from "lucide-react";
import { Markdown } from "../chat/markdown";
import { formatLatency, formatTokens } from "../../utils/chat";
import { formatCost, runStatusLabels } from "../../utils/compare";

export function RunColumn({ run, liveText, streaming }) {
  const [copied, setCopied] = useState(false);
  const text = liveText !== undefined ? liveText : run.content;
  // While a run is in flight its previous answer (on re-run) is hidden until the
  // first new token arrives; a never-run column says so instead of spinning.
  const waiting = liveText === undefined && (streaming || run.status === "pending");
  const statusKey = streaming ? "running" : run.status;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className={`run-column status-${run.status}`}>
      <header className="run-head">
        <div className="run-title">
          <strong>{run.provider}</strong>
          <small>{run.model}</small>
        </div>
        <span className={`run-status ${statusKey}`}>{runStatusLabels[statusKey] ?? statusKey}</span>
      </header>
      <div className="run-body">
        {waiting ? (
          streaming
            ? <p className="run-pending" role="status"><LoaderCircle size={14} className="spin" />Đang tạo câu trả lời…</p>
            : <p className="run-pending">Chưa chạy. Bấm “Chạy so sánh” để gửi câu hỏi tới model này.</p>
        ) : (
          <Markdown content={text} />
        )}
        {!streaming && run.status === "error" && (
          <p className="message-flag error"><CircleAlert size={14} />Không tạo được nội dung{run.error_code ? ` · ${run.error_code}` : ""}</p>
        )}
        {!streaming && run.status === "stopped" && <p className="message-flag stopped">Đã dừng giữa chừng</p>}
      </div>
      <footer className="run-foot">
        {!streaming && run.status === "success" && (
          <p className="run-meta">
            <span>{formatTokens(run.input_tokens)} token vào</span>
            <span>{formatTokens(run.output_tokens)} token ra</span>
            {run.latency_ms !== null && run.latency_ms !== undefined && <span>{formatLatency(run.latency_ms)}</span>}
            <span title="Chi phí ước tính từ giá công bố, không phải khoản thu được provider xác nhận">≈ {formatCost(run.estimated_cost)}</span>
          </p>
        )}
        <button type="button" className="icon-button" onClick={copy} aria-label={`Sao chép câu trả lời của ${run.model}`} title="Sao chép" disabled={!text}>
          {copied ? <Check size={16} /> : <Copy size={16} />}
        </button>
      </footer>
    </article>
  );
}