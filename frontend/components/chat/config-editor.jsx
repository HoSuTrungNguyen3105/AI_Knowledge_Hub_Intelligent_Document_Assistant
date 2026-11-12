"use client";

import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";

function toNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// Edits the per-conversation generation settings the backend allows changing
// after creation (provider/model are fixed). Empty numeric fields mean "default".
export function ConfigEditor({ conversation, busy, onSave }) {
  const [systemPrompt, setSystemPrompt] = useState(conversation.system_prompt ?? "");
  const [temperature, setTemperature] = useState(conversation.temperature ?? "");
  const [maxTokens, setMaxTokens] = useState(conversation.max_output_tokens ?? "");

  function submit(event) {
    event.preventDefault();
    onSave({
      system_prompt: systemPrompt.trim() === "" ? null : systemPrompt,
      temperature: toNumber(temperature),
      max_output_tokens: toNumber(maxTokens),
    });
  }

  return (
    <form className="config-editor" onSubmit={submit}>
      <label className="field-label" htmlFor="config-system">System prompt</label>
      <textarea id="config-system" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={3} maxLength={8000} placeholder="Hướng dẫn vai trò/phong cách cho model (tùy chọn)." disabled={busy} />
      <div className="config-grid">
        <div>
          <label className="field-label" htmlFor="config-temp">Temperature</label>
          <input id="config-temp" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
        <div>
          <label className="field-label" htmlFor="config-tokens">Giới hạn token ra</label>
          <input id="config-tokens" type="number" min="1" max="8192" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} placeholder="Mặc định" disabled={busy} />
        </div>
      </div>
      <p className="field-hint">Để trống để dùng mặc định của provider. Temperature 0–2, token ra 1–8192.</p>
      <button type="submit" className="button secondary" disabled={busy}>{busy && <LoaderCircle size={15} className="spin" />}<Save size={15} />Lưu cấu hình</button>
    </form>
  );
}