"use client";

import { CircleAlert, LockKeyhole, RefreshCw, ShieldCheck, ChevronRight } from "lucide-react";
import { useProviders } from "../../hooks/use-providers";
import { useSession } from "../../stores/session";
import { providerStatus } from "../../utils/providers";
import { ConfirmDialog } from "../confirm-dialog";
import { ProviderDetails } from "./provider-details";

export function ProviderSettings() {
  const controller = useProviders();
  const { catalog, provider, selectedId, selectProvider, busy, reload, confirmDelete, setConfirmDelete, disconnect } = controller;
  const user = useSession((state) => state.user);
  return <>
    <section className="settings-account"><span className="soft-icon"><ShieldCheck size={21} /></span><div><strong>{user?.name}</strong><p>{user?.email}</p></div><span className="private-label"><LockKeyhole size={14} />Chỉ tài khoản của bạn</span></section>
    {catalog.error && <div className="error-panel settings-error" role="alert"><CircleAlert size={23} /><div><h2>Chưa tải được cấu hình AI</h2><p>{catalog.error}</p></div><button className="button secondary" onClick={reload} disabled={Boolean(busy)}>Thử lại</button></div>}
    {catalog.loading && !catalog.data ? <div className="provider-page-loading" role="status" aria-label="Đang tải provider"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div> : catalog.data && <>
      {!catalog.data.encryption_ready && <div className="encryption-warning" role="alert"><LockKeyhole size={20} /><div><strong>Chưa thể lưu API key an toàn</strong><p>Backend chưa có khóa mã hóa. Chạy <code>python scripts/init_env.py</code>, sau đó khởi động lại backend. Không gửi khóa mã hóa vào ô API key.</p></div></div>}
      <div className="provider-workspace"><nav className="provider-list" aria-label="Chọn nhà cung cấp AI"><h2>AI Providers</h2>{catalog.data.providers.map((item) => { const status = providerStatus(item); return <button type="button" key={item.id} aria-pressed={selectedId === item.id} className={`provider-choice ${selectedId === item.id ? "selected" : ""}`} disabled={Boolean(busy)} onClick={() => selectProvider(item.id)}><span className={`provider-monogram ${item.id}`} aria-hidden="true">{item.name[0]}</span><span className="provider-choice-text"><strong>{item.name}</strong><small>{!item.implemented ? "Chưa tích hợp" : item.configured ? item.enabled ? "Đã cấu hình · Đang bật" : "Đã cấu hình · Đang tắt" : status.label}</small></span><ChevronRight size={15} /></button>; })}<p className="provider-list-note">API key và danh sách model được lưu riêng cho từng tài khoản.</p></nav>
        {provider?.implemented ? <ProviderDetails key={provider.id} controller={controller} encryptionReady={catalog.data.encryption_ready} /> : provider && <section className="future-provider"><span className="soft-icon"><LockKeyhole size={23} /></span><h2>{provider.name}</h2><p>Adapter này chưa được tích hợp. Không có API key nào được thu thập hoặc kết nối giả tại đây.</p><p className="muted">Hiện đã hỗ trợ quản lý kết nối: {catalog.data.providers.filter((item) => item.implemented).map((item) => item.name).join(", ")}. Các adapter khác sẽ được bổ sung từng bước.</p></section>}
      </div>
      <p className="settings-scope-note">API key được mã hóa và lưu riêng cho từng tài khoản; danh sách model đồng bộ trực tiếp từ provider, không có dữ liệu mẫu.</p>
    </>}
    <ConfirmDialog open={confirmDelete} title={`Xóa API key ${provider?.name || ""}?`} busy={busy === "delete"} onClose={() => setConfirmDelete(false)} onConfirm={disconnect} confirmLabel="Xóa API key"><p>API key mã hóa, danh sách model và model mặc định của provider này sẽ bị xóa khỏi tài khoản.</p><p>Hội thoại, tài liệu và dữ liệu của tài khoản khác không bị ảnh hưởng. Bạn có thể kết nối lại bằng API key sau.</p></ConfirmDialog>
  </>;
}
