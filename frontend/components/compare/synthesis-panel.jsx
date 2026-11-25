"use client";

import { useState } from "react";
import { CircleAlert, LoaderCircle, Sparkles } from "lucide-react";
import { Markdown } from "../chat/markdown";
import { formatLatency, formatTokens } from "../../utils/chat";
import { formatCost } from "../../utils/compare";
import { ModelSelect } from "../model-select";

export function SynthesisPanel({ providers, synthesis, liveText, canSynthesize, busy, streaming, onSynthesize }) {
  const { available, providerId, setProviderId, models, modelsLoading } = providers;
  const [model, setModel] = useState("");
  const selectedModel = models.find((item) => item.id === model) ?? models[0] ?? null;
  const effectiveModel = selectedModel?.id ?? "";
  const text = liveText || synthesis?.content || "";
  const disabled = busy || streaming || !canSynthesize || !providerId || !effectiveModel;

  function submit(event) {
    event.preventDefault();
    if (disabled) return;
    onSynthesize({ provider: providerId, model: effectiveModel });
  }

  return (
    <section className="synthesis-panel" aria-label="AI Synthesis">
      <div className="synthesis-head">
        <div>
          <h3>AI Synthesis (tùy chọn)</h3>
          <p className="muted">Gộp các câu trả lời thành công thành một câu trả lời cuối thống nhất. Chỉ dùng nội dung đã có, không bịa nguồn.</p>
        </div>
      </div>
      {!canSynthesize && !synthesis && !liveText && (
        <p className="setup-note"><CircleAlert size={14} />Chưa có câu trả lời thành công nào để tổng hợp. Hãy chạy so sánh trước.</p>
      )}
      {available.length > 0 && (
        <form className="synthesis-form" onSubmit={submit}>
          <div className="config-grid">
            <div>
              <label className="field-label" htmlFor="synthesis-provider">Provider tổng hợp</label>
              <select id="synthesis-provider" value={providerId} onChange={(event) => setProviderId(event.target.value)} disabled={busy || streaming}>
                {available.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="synthesis-model">Model tổng hợp</label>
              <ModelSelect id="synthesis-model" models={models} value={effectiveModel} onChange={setModel} disabled={busy || streaming || modelsLoading || models.length === 0} loading={modelsLoading} />
            </div>
          </div>
          <button type="submit" className="button secondary" disabled={disabled}>
            {streaming ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
            {synthesis ? "Tổng hợp lại" : "Tổng hợp câu trả lời"}
          </button>
        </form>
      )}
      {(text || streaming) && (
        <div className="synthesis-result">
          {synthesis && !liveText && (
            <p className="synthesis-by">{synthesis.provider} · {synthesis.model}{synthesis.status === "error" ? " · lỗi" : synthesis.status === "stopped" ? " · đã dừng" : ""}</p>
          )}
          {text ? <Markdown content={text} /> : <p className="run-pending"><LoaderCircle size={14} className="spin" />Đang tổng hợp…</p>}
          {synthesis && !liveText && synthesis.status === "success" && (
            <p className="run-meta">
              <span>{formatTokens(synthesis.input_tokens)} token vào</span>
              <span>{formatTokens(synthesis.output_tokens)} token ra</span>
              {synthesis.latency_ms !== null && synthesis.latency_ms !== undefined && <span>{formatLatency(synthesis.latency_ms)}</span>}
              <span title="Chi phí ước tính từ giá công bố, không phải khoản thu được provider xác nhận">≈ {formatCost(synthesis.estimated_cost)}</span>
            </p>
          )}
        </div>
      )}
    </section>
  );
}