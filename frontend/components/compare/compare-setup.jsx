"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleAlert, Columns2, LoaderCircle, Plus, Settings2, Sparkles, X } from "lucide-react";
import { providerFailureReason } from "../../utils/providers";
import { modelOptionLabel } from "../../utils/model-info";

const MAX_TARGETS = 4;
const MIN_TARGETS = 2;

function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function CompareSetup({ providers, busy, onCreate }) {
  const { available, providerId, setProviderId, models, modelsLoading, modelsError, catalog, reload } = providers;
  const [model, setModel] = useState("");
  const [targets, setTargets] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [temperature, setTemperature] = useState("");
  const [maxTokens, setMaxTokens] = useState("");

  const selectedModel = models.find((item) => item.id === model) ?? models[0] ?? null;
  const effectiveModel = selectedModel?.id ?? "";
  const selectedProvider = available.find((item) => item.id === providerId) ?? null;
  const checkFailed = selectedProvider?.connection_status === "error";
  const alreadyAdded = targets.some((target) => target.provider === providerId && target.model === effectiveModel);

  function addTarget() {
    if (!providerId || !effectiveModel || alreadyAdded || targets.length >= MAX_TARGETS) return;
    const providerName = selectedProvider?.name ?? providerId;
    const modelName = selectedModel?.display_name || effectiveModel;
    setTargets((prev) => [...prev, { provider: providerId, model: effectiveModel, providerName, modelName }]);
  }

  function removeTarget(index) {
    setTargets((prev) => prev.filter((_, position) => position !== index));
  }

  function submit(event) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || targets.length < MIN_TARGETS || busy) return;
    const payload = { prompt: text, targets: targets.map(({ provider, model: id }) => ({ provider, model: id })) };
    if (title.trim()) payload.title = title.trim();
    if (systemPrompt.trim()) payload.system_prompt = systemPrompt;
    const temp = toNumber(temperature);
    if (temp !== null) payload.temperature = temp;
    const max = toNumber(maxTokens);
    if (max !== null) payload.max_output_tokens = max;
    onCreate(payload);
  }

  if (catalog.loading) return <div className="setup-panel" role="status"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>;
  if (catalog.error) return <div className="setup-panel"><div className="error-panel" role="alert"><CircleAlert size={22} /><div><h2>Chưa tải được provider</h2><p>{catalog.error}</p></div><button type="button" className="button secondary" onClick={reload}>Thử lại</button></div></div>;
  if (available.length === 0) return (
    <div className="setup-panel setup-empty">
      <span className="soft-icon"><Settings2 size={24} /></span>
      <h2>Chưa có provider sẵn sàng</h2>
      <p>Bạn cần lưu API key, bật provider và đồng bộ model trong Cài đặt AI trước khi so sánh. Không có model hoặc kết quả giả lập tại đây.</p>
      <Link className="button primary" href="/settings"><Settings2 size={16} />Mở Cài đặt AI</Link>
    </div>
  );

  return (
    <form className="setup-panel" onSubmit={submit}>
      <div className="setup-heading"><span className="soft-icon"><Columns2 size={22} /></span><div><h2>Phép so sánh mới</h2><p>Chọn từ {MIN_TARGETS} đến {MAX_TARGETS} model khác nhau, nhập một câu hỏi chung. Mỗi model trả lời độc lập và riêng tư theo tài khoản của bạn.</p></div></div>

      <div className="config-grid">
        <div>
          <label className="field-label" htmlFor="compare-provider">Provider</label>
          <select id="compare-provider" value={providerId} onChange={(event) => setProviderId(event.target.value)} disabled={busy}>
            {available.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="compare-model">Model</label>
          <select id="compare-model" value={effectiveModel} onChange={(event) => setModel(event.target.value)} disabled={busy || modelsLoading || models.length === 0}>
            {models.length === 0 && <option value="">{modelsLoading ? "Đang tải model…" : "Chưa có model chat"}</option>}
            {models.map((item) => <option key={item.id} value={item.id}>{modelOptionLabel(item)}</option>)}
          </select>
        </div>
      </div>
      {modelsError && <p className="setup-note error" role="alert"><CircleAlert size={14} />{modelsError}</p>}
      {!modelsLoading && !modelsError && models.length === 0 && (checkFailed
        ? <p className="setup-note error" role="alert"><CircleAlert size={14} />Lần kiểm tra {selectedProvider.name} gần nhất thất bại. {providerFailureReason(selectedProvider.last_error_code)} Vào <Link href="/settings">Cài đặt AI</Link> để sửa API key và đồng bộ lại model.</p>
        : <p className="setup-note">Provider này chưa có model chat được đồng bộ. Hãy kiểm tra kết nối trong <Link href="/settings">Cài đặt AI</Link>.</p>)}
      <button type="button" className="button secondary target-add" onClick={addTarget} disabled={busy || !providerId || !effectiveModel || alreadyAdded || targets.length >= MAX_TARGETS}>
        <Plus size={16} />{alreadyAdded ? "Model đã có trong danh sách" : "Thêm model vào so sánh"}
      </button>

      {targets.length > 0 && (
        <ul className="target-list" aria-label="Model đã chọn">
          {targets.map((target, index) => (
            <li key={`${target.provider}:${target.model}`} className="target-row">
              <span className="target-name"><strong>{target.providerName}</strong><small>{target.modelName}</small></span>
              <button type="button" className="icon-button danger" onClick={() => removeTarget(index)} aria-label={`Bỏ ${target.providerName} ${target.modelName}`} disabled={busy}><X size={16} /></button>
            </li>
          ))}
        </ul>
      )}
      <p className={`setup-note ${targets.length < MIN_TARGETS ? "error" : ""}`} role={targets.length < MIN_TARGETS ? "status" : undefined}>
        {targets.length < MIN_TARGETS ? `Cần chọn ít nhất ${MIN_TARGETS} model khác nhau (đã chọn ${targets.length}).` : `Đã chọn ${targets.length}/${MAX_TARGETS} model.`}
      </p>

      <label className="field-label" htmlFor="compare-prompt">Câu hỏi chung</label>
      <textarea id="compare-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} maxLength={32000} placeholder="Nhập câu hỏi sẽ gửi đến tất cả model đã chọn." disabled={busy} required />

      <label className="field-label" htmlFor="compare-title">Tên phép so sánh (tùy chọn)</label>
      <input id="compare-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="Tự đặt theo câu hỏi nếu để trống" disabled={busy} />
      <label className="field-label" htmlFor="compare-system">System prompt (tùy chọn)</label>
      <textarea id="compare-system" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={3} maxLength={8000} placeholder="Hướng dẫn vai trò/phong cách chung cho các model." disabled={busy} />
      <div className="config-grid">
        <div>
          <label className="field-label" htmlFor="compare-temp">Temperature</label>
          <input id="compare-temp" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
        <div>
          <label className="field-label" htmlFor="compare-tokens">Giới hạn token ra</label>
          <input id="compare-tokens" type="number" min="1" max="8192" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
      </div>
      <p className="field-hint">Để trống để dùng mặc định của provider. Model chỉ khả dụng khi đã đồng bộ và hỗ trợ chat.</p>
      <button type="submit" className="button primary setup-submit" disabled={busy || !prompt.trim() || targets.length < MIN_TARGETS}>{busy ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}{busy ? "Đang gửi…" : "Gửi và so sánh"}</button>
    </form>
  );
}