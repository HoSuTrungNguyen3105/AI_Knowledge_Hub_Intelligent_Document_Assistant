"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleAlert, LoaderCircle, MessagesSquare, Settings2, Sparkles } from "lucide-react";

function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function SetupPanel({ providers, busy, onCreate }) {
  const { available, providerId, setProviderId, models, modelsLoading, modelsError, catalog, reload } = providers;
  const [model, setModel] = useState("");
  const [title, setTitle] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [temperature, setTemperature] = useState("");
  const [maxTokens, setMaxTokens] = useState("");

  const selectedModel = models.find((item) => item.id === model) ?? models[0] ?? null;
  const effectiveModel = selectedModel?.id ?? "";

  function submit(event) {
    event.preventDefault();
    if (!providerId || !effectiveModel || busy) return;
    const payload = { provider: providerId, model: effectiveModel };
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
      <p>Bạn cần lưu API key, bật provider và đồng bộ model trong Cài đặt AI trước khi trò chuyện. Không có model hoặc kết quả giả lập tại đây.</p>
      <Link className="button primary" href="/settings"><Settings2 size={16} />Mở Cài đặt AI</Link>
    </div>
  );

  return (
    <form className="setup-panel" onSubmit={submit}>
      <div className="setup-heading"><span className="soft-icon"><MessagesSquare size={22} /></span><div><h2>Hội thoại mới</h2><p>Chọn provider và model đã cấu hình. Mỗi hội thoại thuộc riêng tài khoản của bạn.</p></div></div>
      <div className="config-grid">
        <div>
          <label className="field-label" htmlFor="setup-provider">Provider</label>
          <select id="setup-provider" value={providerId} onChange={(event) => setProviderId(event.target.value)} disabled={busy}>
            {available.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="setup-model">Model</label>
          <select id="setup-model" value={effectiveModel} onChange={(event) => setModel(event.target.value)} disabled={busy || modelsLoading || models.length === 0}>
            {models.length === 0 && <option value="">{modelsLoading ? "Đang tải model…" : "Chưa có model chat"}</option>}
            {models.map((item) => <option key={item.id} value={item.id}>{item.display_name || item.id}</option>)}
          </select>
        </div>
      </div>
      {modelsError && <p className="setup-note error" role="alert"><CircleAlert size={14} />{modelsError}</p>}
      {!modelsLoading && !modelsError && models.length === 0 && <p className="setup-note">Provider này chưa có model chat được đồng bộ. Hãy kiểm tra kết nối trong <Link href="/settings">Cài đặt AI</Link>.</p>}
      <label className="field-label" htmlFor="setup-title">Tên hội thoại (tùy chọn)</label>
      <input id="setup-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="Tự đặt theo tin nhắn đầu tiên nếu để trống" disabled={busy} />
      <label className="field-label" htmlFor="setup-system">System prompt (tùy chọn)</label>
      <textarea id="setup-system" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={3} maxLength={8000} placeholder="Hướng dẫn vai trò/phong cách cho model." disabled={busy} />
      <div className="config-grid">
        <div>
          <label className="field-label" htmlFor="setup-temp">Temperature</label>
          <input id="setup-temp" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
        <div>
          <label className="field-label" htmlFor="setup-tokens">Giới hạn token ra</label>
          <input id="setup-tokens" type="number" min="1" max="8192" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
      </div>
      <p className="field-hint">Để trống để dùng mặc định của provider. Model chỉ khả dụng khi đã đồng bộ và hỗ trợ chat.</p>
      <button type="submit" className="button primary setup-submit" disabled={busy || !providerId || !effectiveModel}>{busy ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}Bắt đầu hội thoại</button>
    </form>
  );
}