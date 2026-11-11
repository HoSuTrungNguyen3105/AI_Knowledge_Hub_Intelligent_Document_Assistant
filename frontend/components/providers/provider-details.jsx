"use client";

import { KeyRound, LoaderCircle, PlugZap, ShieldCheck, Trash2 } from "lucide-react";
import { formatDate } from "../../utils/format";
import { providerStatus } from "../../utils/providers";
import { ModelCatalog } from "./model-catalog";

export function ProviderDetails({ controller, encryptionReady }) {
  const { provider, modelState, modelsLoading, busy, keyError, saveKey, testConnection, setEnabled, saveDefaultModel, setConfirmDelete, reload } = controller;
  const status = providerStatus(provider);
  const models = modelState.provider === provider.id ? modelState.models : [];
  const disabled = Boolean(busy) || !encryptionReady;
  return <section className="provider-detail" aria-label={`Cấu hình ${provider.name}`}>
    <div className="provider-detail-heading"><div><h2>{provider.name}</h2><span className={`provider-status ${status.tone}`}>{status.label}</span></div><label className="provider-toggle"><span>{provider.enabled ? "Đang bật" : "Đang tắt"}</span><input type="checkbox" role="switch" aria-label={`Bật ${provider.name}`} checked={provider.enabled} disabled={Boolean(busy) || !provider.configured || !encryptionReady} onChange={(event) => setEnabled(event.target.checked)} /></label></div>
    <div className="provider-section">
      <div className="provider-section-heading"><div><h3><KeyRound size={16} />API key</h3><p>{provider.configured ? "Đã lưu key mã hóa. Hệ thống không hiển thị lại key đã lưu." : "Dùng API key của riêng bạn để kết nối provider."}</p></div><span className="key-safety"><ShieldCheck size={14} />Mã hóa ở backend</span></div>
      <form className="provider-key-form" onSubmit={saveKey} aria-busy={busy === "save-key"}>
        <label htmlFor={`key-${provider.id}`} className="field-label">{provider.configured ? "API key mới (chỉ nhập khi muốn thay thế)" : "Nhập API key"}</label>
        <div className="key-input-row"><input id={`key-${provider.id}`} name="apiKey" type="password" autoComplete="off" spellCheck={false} autoCapitalize="none" placeholder={provider.configured ? "Nhập key mới để thay thế" : "Dán API key tại đây"} maxLength={4096} required disabled={disabled} aria-describedby={`key-hint-${provider.id}`} /><button className="button primary" disabled={disabled} type="submit">{busy === "save-key" && <LoaderCircle size={16} className="spin" />}{provider.configured ? "Thay API key" : "Lưu API key"}</button></div>
        <p id={`key-hint-${provider.id}`} className="field-hint">Key được gửi một lần đến backend, không lưu trong localStorage và không trả lại trong API response. Thay key sẽ xóa danh sách model và lựa chọn mặc định cũ.</p>
        {keyError && <p className="form-error" role="alert">{keyError}</p>}
      </form>
      <div className="connection-actions"><button type="button" className="button secondary" onClick={testConnection} disabled={disabled || !provider.configured}>{busy === "test" ? <LoaderCircle size={16} className="spin" /> : <PlugZap size={16} />}{busy === "test" ? "Đang kiểm tra…" : "Kiểm tra & đồng bộ model"}</button><span>{provider.last_checked_at ? `Đã kiểm tra: ${formatDate(provider.last_checked_at)}` : "Chưa thực hiện kiểm tra kết nối"}</span></div>
      <p className="provider-test-note">Chỉ gọi API liệt kê model, không gửi prompt hoặc tạo nội dung tính phí. Provider đã tắt vẫn có thể được kiểm tra.</p>
      {provider.connection_status === "error" && <p className="provider-status-explanation">Lần kiểm tra gần nhất chưa thành công. Nếu còn danh sách model bên dưới, đó là dữ liệu của lần đồng bộ thành công trước.</p>}
    </div>
    <div className="provider-section">
      <div className="provider-section-heading"><div><h3>Model mặc định</h3><p>Lựa chọn này được lưu để dùng ở các tính năng Chat, Compare và Agent sắp triển khai.</p></div></div>
      <form key={`${provider.id}-${provider.default_model || "none"}-${provider.models_synced_at || "unsynced"}`} onSubmit={saveDefaultModel} className="default-model-form"><label htmlFor={`model-${provider.id}`} className="field-label">Chọn từ model đã đồng bộ</label><div className="key-input-row"><select id={`model-${provider.id}`} name="defaultModel" defaultValue={provider.default_model || ""} disabled={Boolean(busy) || !provider.configured || modelsLoading || models.length === 0} aria-label={`Model mặc định ${provider.name}`}><option value="">Chưa chọn model mặc định</option>{models.map((model) => <option key={model.id} value={model.id}>{model.display_name || model.id} ({model.id})</option>)}</select><button type="submit" className="button secondary" disabled={Boolean(busy) || !provider.configured || modelsLoading || models.length === 0}>{busy === "default-model" && <LoaderCircle size={16} className="spin" />}Lưu model</button></div></form>
    </div>
    <ModelCatalog key={provider.id} models={models} loading={modelsLoading} error={modelState.provider === provider.id ? modelState.error : ""} syncedAt={provider.models_synced_at} onRetry={reload} />
    {provider.configured && <div className="provider-delete-row"><p>Xóa kết nối chỉ xóa API key và model cache của provider này.</p><button type="button" className="button danger-outline" disabled={Boolean(busy)} onClick={() => setConfirmDelete(true)}><Trash2 size={15} />Xóa API key</button></div>}
  </section>;
}
