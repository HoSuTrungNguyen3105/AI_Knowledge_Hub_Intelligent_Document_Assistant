"use client";

import { RefreshCw } from "lucide-react";
import { Markdown } from "../chat/markdown";
import { agentErrorFromEvent, executionStatusLabels, traceValue } from "../../utils/agents";
import { formatCost } from "../../utils/compare";

export function ExecutionDetail({ controller }) {
  const { execution, executionLoading, executionError, isStreaming, reloadExecution } = controller;
  if (executionLoading) return <section className="agent-execution" role="status" aria-label="Đang tải lượt thực thi"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></section>;
  if (executionError) return <section className="agent-execution"><p className="composer-error" role="alert">{executionError}</p><button type="button" className="button secondary" onClick={reloadExecution}>Thử lại lượt thực thi</button></section>;
  if (!execution) return <div className="agent-execution muted">Chọn một lượt trong lịch sử để xem chi tiết hoặc chạy yêu cầu mới.</div>;
  const steps = execution.steps ?? [];
  return <section className="agent-execution" aria-label="Chi tiết lượt thực thi">
    <div className="section-heading"><h3>{executionStatusLabels[execution.status] ?? execution.status}</h3>{execution.id && <button type="button" className="icon-button" onClick={reloadExecution} disabled={isStreaming} aria-label="Tải lại lượt thực thi"><RefreshCw size={16} /></button>}</div>
    <p className="message-text agent-execution-prompt">{execution.prompt}</p>
    <p className="message-meta agent-execution-target" aria-label="Model của lượt thực thi">Provider: {execution.provider ?? "Chưa có thông tin"} · Model: {execution.model ?? "Chưa có thông tin"}</p>
    <div className="message-meta"><span>{execution.step_count ?? steps.length} / 6 bước</span><span>{execution.input_tokens ?? "—"} token vào</span><span>{execution.output_tokens ?? "—"} token ra</span><span>{execution.latency_ms == null ? "—" : `${(execution.latency_ms / 1000).toFixed(1)} s`}</span><span title="Ước tính từ giá công bố; không phải khoản thu được provider xác nhận">Chi phí ước tính: {execution.estimated_cost == null ? "— (chưa có giá hoặc token)" : `≈ ${formatCost(execution.estimated_cost)}`}</span></div>
    {execution.error_code && <p className="message-flag error" role="alert">{agentErrorFromEvent({ code: execution.error_code })} ({execution.error_code})</p>}
    <div className="agent-steps" aria-label="Các bước thực thi">
      {!steps.length && <p className="muted" role="status">{isStreaming ? "Đang chờ bước đầu tiên…" : "Không có bước thực thi được ghi nhận."}</p>}
      {steps.map((step) => <section className="agent-step" key={step.index}><h4>Bước {step.index + 1}</h4>{step.content && <Markdown content={step.content} />}
        {(step.tool_calls ?? []).filter((call, index, calls) => calls.findIndex((item) => item.id === call.id) === index).map((call) => <details className="agent-tool-trace" key={call.id} open><summary>{call.name} · {executionStatusLabels[call.status] ?? call.status ?? "Đang gọi"}</summary><dl><dt>Tham số</dt><dd><pre>{traceValue(call.arguments)}</pre></dd>{(call.result != null || call.error_code || ["success", "error", "stopped"].includes(call.status)) && <><dt>Kết quả</dt><dd><pre>{traceValue(call.result)}</pre></dd></>}{call.error_code && <><dt>Mã lỗi</dt><dd>{call.error_code}</dd></>}{call.latency_ms != null && <><dt>Thời gian</dt><dd>{call.latency_ms} ms</dd></>}</dl></details>)}
        {(step.input_tokens != null || step.output_tokens != null) && <p className="message-meta">{step.input_tokens ?? "—"} token vào · {step.output_tokens ?? "—"} token ra</p>}
      </section>)}
    </div>
    <section className="agent-final" aria-label="Câu trả lời cuối"><h3>Câu trả lời cuối</h3>{execution.content ? <Markdown content={execution.content} /> : <p className="muted">{isStreaming ? "Đang thực thi; chưa có câu trả lời cuối." : "Lượt này chưa có câu trả lời cuối."}</p>}</section>
  </section>;
}
