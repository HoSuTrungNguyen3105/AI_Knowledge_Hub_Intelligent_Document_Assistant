"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, RefreshCw } from "lucide-react";
import {
  credentialBindingsService,
  getCredentialBindingsError,
} from "../../services/credential-bindings";

// Panel "Gán credential": map each credential TYPE the approved
// templates need to one of the user's own n8n credentials. Installs
// rewrite node credentials automatically from these bindings, and the
// bulk button re-applies them to workflows installed earlier.
export function CredentialBindingsPanel() {
  const [view, setView] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyType, setBusyType] = useState("");
  const [applying, setApplying] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await credentialBindingsService.list();
      setView(data);
      setError("");
    } catch (err) {
      setError(getCredentialBindingsError(err, "Không tải được danh sách gán credential."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function changeBinding(credType, credentialId) {
    setBusyType(credType);
    setNote("");
    try {
      if (credentialId) {
        await credentialBindingsService.set(credType, credentialId);
        setNote(`Đã gán ${credType} — các lần cài template sau sẽ tự dùng credential này.`);
      } else {
        await credentialBindingsService.remove(credType);
        setNote(`Đã gỡ gán ${credType}.`);
      }
      await load();
    } catch (err) {
      setError(getCredentialBindingsError(err, "Không lưu được mục gán credential."));
    } finally {
      setBusyType("");
    }
  }

  async function applyAll() {
    setApplying(true);
    setNote("");
    try {
      const result = await credentialBindingsService.applyInstalled();
      const failedNames = (result.results || [])
        .filter((item) => item.status === "failed")
        .map((item) => `${item.template_name || item.install_id} (${item.error || "?"})`);
      setNote(
        `Đã áp dụng cho workflow đã cài: ${result.updated} cập nhật · ${result.unchanged} không đổi · ${result.failed} lỗi.` +
          (failedNames.length ? ` Lỗi: ${failedNames.join(", ")}.` : ""),
      );
    } catch (err) {
      setError(getCredentialBindingsError(err, "Không áp dụng được cho workflow đã cài."));
    } finally {
      setApplying(false);
    }
  }

  const bindingsByType = {};
  (view?.bindings || []).forEach((binding) => {
    bindingsByType[binding.cred_type] = binding;
  });
  const rows = (view?.required_types || []).map((item) => item.cred_type);
  (view?.bindings || []).forEach((binding) => {
    if (!rows.includes(binding.cred_type)) rows.push(binding.cred_type);
  });
  const countByType = {};
  (view?.required_types || []).forEach((item) => {
    countByType[item.cred_type] = item.template_count;
  });

  return (
    <div className="n8n-node">
      <h3>
        <KeyRound size={15} /> Gán credential của bạn cho template
      </h3>
      <p className="fx-run-meta">
        Mỗi loại credential chỉ cần gán một lần: khi cài template, mọi node dùng loại đó sẽ tự
        trỏ về credential của bạn thay vì credential của máy tác giả gốc. Key dạng token có thể
        đẩy từ tab "Kho key — đẩy sang n8n"; riêng Gmail/Google là đăng nhập OAuth nên cần tạo
        credential một lần ngay trong n8n (Credentials → New) rồi quay lại đây gán.
      </p>
      {error ? (
        <p className="fx-alert" role="alert">
          {error}
        </p>
      ) : null}
      {view?.n8n_error ? (
        <p className="fx-run-meta">
          Chưa đọc được danh sách credential từ n8n ({view.n8n_error}) — hãy kiểm tra tab n8n
          Platform đã "Đã kết nối" chưa.
        </p>
      ) : null}
      {note ? <p className="fx-run-meta">{note}</p> : null}
      {loading ? (
        <p className="fx-run-meta">
          <Loader2 size={14} className="spin" /> Đang tải danh sách credential…
        </p>
      ) : rows.length === 0 ? (
        <p className="fx-run-meta">
          Chưa có template đã duyệt nào cần credential, hoặc chưa đọc được dữ liệu.
        </p>
      ) : (
        rows.map((credType) => {
          const bound = bindingsByType[credType];
          const options = (view?.n8n_credentials || []).filter(
            (credential) => credential.type === credType,
          );
          return (
            <label key={credType} className="fx-field" style={{ display: "block", marginTop: 10 }}>
              {credType}
              {countByType[credType]
                ? ` · dùng trong ${countByType[credType]} template đã duyệt`
                : ""}
              <select
                className="fx-input"
                value={bound ? bound.n8n_credential_id : ""}
                disabled={busyType === credType}
                onChange={(event) => changeBinding(credType, event.target.value)}
              >
                <option value="">— Chưa gán —</option>
                {bound &&
                !options.some((option) => option.id === bound.n8n_credential_id) ? (
                  <option value={bound.n8n_credential_id}>
                    {bound.n8n_credential_name || bound.n8n_credential_id} (đã gán — không còn
                    thấy trong n8n?)
                  </option>
                ) : null}
                {options.map((credential) => (
                  <option key={credential.id} value={credential.id}>
                    {credential.name || credential.id}
                  </option>
                ))}
              </select>
              {options.length === 0 && !bound ? (
                <span className="fx-run-meta">
                  n8n của bạn chưa có credential loại này — hãy tạo trong n8n hoặc đẩy từ Kho
                  key trước.
                </span>
              ) : null}
            </label>
          );
        })
      )}
      <div className="fx-actions" style={{ marginTop: 12 }}>
        <button
          type="button"
          className="fx-btn primary"
          onClick={applyAll}
          disabled={applying || loading}
        >
          {applying ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Áp dụng
          cho tất cả workflow đã cài
        </button>
      </div>
    </div>
  );
}
