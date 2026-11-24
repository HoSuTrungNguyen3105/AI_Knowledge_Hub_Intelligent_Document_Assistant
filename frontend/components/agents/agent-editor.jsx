"use client";

import { useState } from "react";
import Link from "next/link";
import { LoaderCircle, Save, Settings2 } from "lucide-react";
import { useChatProviders } from "../../hooks/use-chat-providers";
import { toolCapability } from "../../utils/agents";

export function AgentEditor({ agent, tools, busy, onSave, onCancel, reloadTools }) {
  const providers = useChatProviders(agent?.provider ?? "");
  const { available, providerId, setProviderId, models, modelsLoading, modelsError, catalog, reload } = providers;
  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [modelChoice, setModelChoice] = useState({ provider: agent?.provider ?? providerId, id: agent?.model ?? "" });
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt ?? "");
  const [temperature, setTemperature] = useState(agent?.temperature ?? "");
  const [maxTokens, setMaxTokens] = useState(agent?.max_output_tokens ?? "");
  const [selectedTools, setSelectedTools] = useState(agent?.tools ?? []);
  const selectedProvider = available.find((item) => item.id === providerId);
  const desiredModel = modelChoice.provider === providerId ? modelChoice.id : "";
  const selectedModel = models.find((item) => item.id === desiredModel) ?? (!desiredModel ? models[0] : null);
  const model = selectedModel?.id ?? "";
  const capability = toolCapability(selectedProvider, selectedModel);
  const blockedTools = selectedTools.some((name) => !tools.items.some((tool) => tool.name === name && tool.available));
  const validTemperature = temperature === "" || (Number.isFinite(Number(temperature)) && Number(temperature) >= 0 && Number(temperature) <= 2);
  const validTokens = maxTokens === "" || (Number.isInteger(Number(maxTokens)) && Number(maxTokens) >= 1 && Number(maxTokens) <= 8192);
  const ready = !catalog.loading && !catalog.error && !modelsLoading && !modelsError && model && name.trim() && !tools.loading && !tools.error && !blockedTools && !(selectedTools.length && capability === false) && validTemperature && validTokens;

  function toggleTool(name) {
    setSelectedTools((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  }
  function submit(event) {
    event.preventDefault();
    if (!ready || busy) return;
    onSave({ name: name.trim(), description: description.trim(), provider: providerId, model, system_prompt: systemPrompt,
      temperature: temperature === "" ? null : Number(temperature), max_output_tokens: maxTokens === "" ? null : Number(maxTokens), tools: selectedTools });
  }

  if (catalog.loading) return <div className="setup-panel" role="status" aria-label="Đang tải provider"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>;
  if (catalog.error) return <div className="setup-panel"><p className="composer-error" role="alert">{catalog.error}</p><button className="button secondary" onClick={reload}>Thử lại provider</button>{onCancel && <button className="button secondary" onClick={onCancel}>Hủy chỉnh sửa</button>}</div>;
  if (!available.length) return <div className="setup-panel setup-empty"><Settings2 size={24} /><h2>Chưa có provider sẵn sàng</h2><p>Lưu kết nối AI, bật provider và đồng bộ model để tạo Agent. Không có model giả lập.</p><Link className="button primary" href="/settings">Mở Cài đặt AI</Link>{onCancel && <button className="button secondary" onClick={onCancel}>Hủy chỉnh sửa</button>}</div>;

  return <form className="setup-panel agent-editor" onSubmit={submit}>
    <div className="setup-heading"><div><h2>{agent ? "Chỉnh sửa Agent" : "Tạo Agent"}</h2><p>Cấu hình riêng cho tài khoản của bạn. Mỗi lượt chạy độc lập, không giữ bộ nhớ giữa các lần chạy.</p></div></div>
    <label className="field-label" htmlFor="agent-name">Tên Agent</label>
    <input id="agent-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} disabled={busy} />
    <label className="field-label" htmlFor="agent-description">Mô tả</label>
    <textarea id="agent-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={2} maxLength={2000} disabled={busy} />
    <div className="config-grid">
      <div><label className="field-label" htmlFor="agent-provider">Provider</label><select id="agent-provider" value={providerId} onChange={(event) => setProviderId(event.target.value)} disabled={busy}>{available.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
      <div><label className="field-label" htmlFor="agent-model">Model đã đồng bộ</label><select id="agent-model" value={model} onChange={(event) => setModelChoice({ provider: providerId, id: event.target.value })} disabled={busy || modelsLoading || !models.length}><option value="">{modelsLoading ? "Đang tải model…" : "Chọn model"}</option>{models.map((item) => <option key={item.id} value={item.id}>{item.display_name || item.id}</option>)}</select></div>
    </div>
    {agent && agent.provider !== providerId && <p className="setup-note">Provider đang chọn khác cấu hình đã lưu ({agent.provider}). Kiểm tra provider và model trước khi lưu.</p>}
    {modelsError && <p className="composer-error" role="alert">{modelsError}</p>}
    {!modelsLoading && !model && <p className="setup-note">Model chưa được đồng bộ hoặc không còn khả dụng. Chọn model khác hoặc đồng bộ trong <Link href="/settings">Cài đặt AI</Link>.</p>}
    <button type="button" className="button secondary setup-submit" onClick={reload} disabled={busy || modelsLoading}>Tải lại provider và model</button>
    <label className="field-label" htmlFor="agent-system">System prompt</label>
    <textarea id="agent-system" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} rows={4} maxLength={8000} disabled={busy} placeholder="Vai trò, hướng dẫn và cách sử dụng công cụ của Agent." />
    <div className="config-grid">
      <div><label className="field-label" htmlFor="agent-temperature">Temperature</label><input id="agent-temperature" type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(event.target.value)} disabled={busy} placeholder="Mặc định provider" /></div>
      <div><label className="field-label" htmlFor="agent-tokens">Giới hạn token ra</label><input id="agent-tokens" type="number" min="1" max="8192" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} disabled={busy} placeholder="Mặc định 2048 mỗi bước" /></div>
    </div>
    <p className="field-hint">Temperature để trống dùng mặc định provider; token ra mặc định 2048 mỗi bước và được giảm theo ngân sách còn lại. Ngân sách toàn lượt chạy là 8000 đơn vị ước lượng bảo thủ, không phải số token tính phí.</p>
    <fieldset className="agent-tool-picker" disabled={busy}><legend>Công cụ được phép</legend>
      {tools.loading ? <div role="status" aria-label="Đang tải công cụ"><div className="skeleton" /><div className="skeleton" /></div> : tools.error ? <div><p className="composer-error" role="alert">{tools.error}</p><button type="button" className="button secondary" onClick={reloadTools}>Thử lại công cụ</button></div> : !tools.items.length ? <p className="muted">Chưa có công cụ trong danh mục.</p> : tools.items.map((tool) => <label className="agent-tool-row" key={tool.name}><input type="checkbox" style={{width: "20px"}} checked={selectedTools.includes(tool.name)} onChange={() => toggleTool(tool.name)} disabled={!tool.available || capability === false} /><span><strong>{tool.name}</strong><small>{tool.description}</small><small>{tool.available ? "Khả dụng" : `Chưa khả dụng · ${tool.phase ?? "Giai đoạn sau"}`}</small></span></label>)}
    </fieldset>
    {selectedTools.length > 0 && <button type="button" className="button secondary setup-submit" onClick={() => setSelectedTools([])} disabled={busy}>Bỏ chọn tất cả công cụ</button>}
    {blockedTools && <p className="composer-error" role="alert">Cấu hình có công cụ không khả dụng. Bỏ chọn công cụ trước khi lưu.</p>}
    {capability === false ? <p className="setup-note error" role="alert">Provider hoặc model không hỗ trợ function calling. Công cụ bị chặn; bỏ chọn công cụ để lưu và chạy chỉ văn bản.</p> : <p className="setup-note">{capability === null ? "Khả năng function calling chưa xác định; chỉ được kiểm chứng bằng lượt chạy thực tế." : "Danh mục báo hỗ trợ function calling; khả năng thực tế vẫn chỉ được kiểm chứng khi chạy."}</p>}
    <fieldset className="agent-tool-picker" disabled><legend>Tính năng giai đoạn sau</legend><label className="agent-tool-row"><input style={{width: "20px"}} type="checkbox" /><span>Knowledge Base (KB)<small>Chưa khả dụng · Phase 6</small></span></label><label className="agent-tool-row"><input style={{width: "20px"}} type="checkbox" /><span>Memory<small>Chưa khả dụng · Giai đoạn sau</small></span></label></fieldset>
    <div className="agent-actions"><button type="submit" className="button primary" disabled={busy || !ready}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}{agent ? "Lưu Agent" : "Tạo Agent"}</button>{onCancel && <button type="button" className="button secondary" onClick={onCancel} disabled={busy}>Hủy chỉnh sửa</button>}</div>
  </form>;
}
