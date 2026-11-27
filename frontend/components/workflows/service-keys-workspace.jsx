"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  Pencil,
  Plus,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { getServiceKeyError, serviceKeysService } from "../../services/service-keys";
import { ConfirmDialog } from "../confirm-dialog";
import "./service-keys.css";

const timeLabel = (iso) =>
  iso
    ? new Date(iso).toLocaleString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })
    : null;

export function ServiceKeysWorkspace() {
  const [presets, setPresets] = useState([]);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // form: null | { mode: "create" } | { mode: "edit", entry }
  const [form, setForm] = useState(null);
  const [pushingId, setPushingId] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [presetList, entryList] = await Promise.all([
        serviceKeysService.listPresets(),
        serviceKeysService.list(),
      ]);
      setPresets(presetList);
      setEntries(entryList);
      setError("");
    } catch (err) {
      setError(getServiceKeyError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const presetOf = (service) => presets.find((p) => p.service === service);

  const push = async (entry) => {
    setPushingId(entry.id);
    setError("");
    setNotice("");
    try {
      const result = await serviceKeysService.push(entry.id);
      setNotice(
        `Đã đẩy "${entry.name}" sang n8n — credential "${result.n8n_credential_name}" (${result.n8n_credential_type}). Trong n8n, mở node HTTP Request/Telegram và chọn credential này là dùng được.`,
      );
      await load();
    } catch (err) {
      setError(getServiceKeyError(err));
    } finally {
      setPushingId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await serviceKeysService.remove(deleting.id);
      setDeleting(null);
      setNotice(
        `Đã xoá "${deleting.name}" khỏi kho. Credential đã đẩy vào n8n vẫn còn nguyên — muốn gỡ hẳn thì xoá thêm trong n8n.`,
      );
      await load();
    } catch (err) {
      setError(getServiceKeyError(err));
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div className="sk-wrap">
      <div className="sk-head">
        <div>
          <h2 className="sk-title">
            <KeyRound size={18} /> Kho key — đẩy sang n8n
          </h2>
          <p className="sk-sub">
            Key của các dịch vụ ngoài (Zalo OA, Telegram…) lưu mã hoá ngay trong
            MindFlow. Bấm <strong>Đẩy sang n8n</strong> là credential tương ứng
            được tạo/cập nhật trong n8n của bạn — sửa key ở đây rồi bấm đẩy lại
            là n8n nhận giá trị mới, không phải mở n8n sửa tay. Key dạng OAuth
            (Google…) vẫn phải nối một lần trong n8n. Riêng Zalo: access token
            chỉ sống 25 giờ, hết hạn thì lấy token mới, cập nhật ở đây và đẩy
            lại.
          </p>
        </div>
        <button
          type="button"
          className="button primary"
          onClick={() => setForm({ mode: "create" })}
          disabled={loading || presets.length === 0}
        >
          <Plus size={16} /> Thêm key
        </button>
      </div>

      {error ? (
        <div className="sk-banner sk-banner-error">
          <AlertTriangle size={16} /> {error}
        </div>
      ) : null}
      {notice ? (
        <div className="sk-banner sk-banner-ok">
          <CheckCircle2 size={16} /> {notice}
        </div>
      ) : null}

      {loading ? (
        <p className="sk-empty">
          <LoaderCircle size={16} className="spin" /> Đang tải kho key…
        </p>
      ) : entries.length === 0 && !form ? (
        <p className="sk-empty">
          Chưa có key nào. Bấm "Thêm key" để lưu key dịch vụ đầu tiên — ví dụ
          Zalo OA cho chatbot trả lời tự động qua n8n.
        </p>
      ) : (
        <div className="sk-list">
          {entries.map((entry) => {
            const preset = presetOf(entry.service);
            return (
              <article key={entry.id} className="sk-card">
                <div className="sk-card-main">
                  <div className="sk-card-title">
                    <strong>{entry.name}</strong>
                    <span className="sk-badge">{preset?.label ?? entry.service}</span>
                  </div>
                  <div className="sk-card-meta">
                    Credential trong n8n: <code>{entry.credential_name}</code> (
                    {entry.n8n_credential_type})
                    {entry.last_pushed_at
                      ? ` · Đã đẩy lúc ${timeLabel(entry.last_pushed_at)}`
                      : " · Chưa đẩy sang n8n"}
                  </div>
                  <div className="sk-chips">
                    {entry.fields.map((field) => (
                      <span
                        key={field.key}
                        className={`sk-chip${field.has_value ? " has" : ""}`}
                      >
                        {field.label}: {field.has_value ? "đã có" : "chưa có"}
                        {field.required ? " *" : ""}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="sk-card-actions">
                  <button
                    type="button"
                    className="button primary"
                    onClick={() => push(entry)}
                    disabled={pushingId === entry.id}
                  >
                    {pushingId === entry.id ? (
                      <LoaderCircle size={15} className="spin" />
                    ) : (
                      <Upload size={15} />
                    )}{" "}
                    Đẩy sang n8n
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => setForm({ mode: "edit", entry })}
                  >
                    <Pencil size={15} /> Sửa
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => setDeleting(entry)}
                  >
                    <Trash2 size={15} /> Xoá
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {form ? (
        <ServiceKeyForm
          key={form.mode === "edit" ? form.entry.id : "create"}
          presets={presets}
          entry={form.mode === "edit" ? form.entry : null}
          onClose={() => setForm(null)}
          onSaved={async (message) => {
            setForm(null);
            setNotice(message);
            await load();
          }}
          onError={setError}
        />
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        title="Xoá key này?"
        busy={deleteBusy}
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
        confirmLabel="Xoá"
      >
        Xoá "{deleting?.name}" khỏi kho key của MindFlow. Credential đã đẩy vào
        n8n không bị xoá theo.
      </ConfirmDialog>
    </div>
  );
}

function ServiceKeyForm({ presets, entry, onClose, onSaved, onError }) {
  const isEdit = entry !== null;
  const [service, setService] = useState(entry?.service ?? presets[0]?.service ?? "zalo_oa");
  const preset = presets.find((p) => p.service === service) ?? presets[0];
  const [name, setName] = useState(entry?.name ?? "");
  const [credentialName, setCredentialName] = useState(entry?.credential_name ?? "");
  const [values, setValues] = useState({});
  const [cleared, setCleared] = useState({});
  const [shown, setShown] = useState({});
  const [saving, setSaving] = useState(false);

  const hasValueOf = (key) =>
    isEdit ? entry.fields.find((f) => f.key === key)?.has_value ?? false : false;

  const submit = async (event) => {
    event.preventDefault();
    if (!preset) return;
    setSaving(true);
    try {
      if (isEdit) {
        const fields = {};
        for (const field of preset.fields) {
          if (cleared[field.key]) fields[field.key] = "";
          else if (values[field.key]) fields[field.key] = values[field.key];
        }
        await serviceKeysService.update(entry.id, {
          name: name.trim(),
          credential_name: credentialName.trim() || entry.credential_name,
          fields,
        });
        onSaved(`Đã lưu thay đổi cho "${name.trim()}". Nhớ bấm Đẩy sang n8n để n8n nhận giá trị mới.`);
      } else {
        const fields = {};
        for (const field of preset.fields) {
          if (values[field.key]) fields[field.key] = values[field.key];
        }
        await serviceKeysService.create({
          name: name.trim(),
          service,
          credential_name: credentialName.trim() || undefined,
          fields,
        });
        onSaved(`Đã thêm "${name.trim()}" vào kho key. Bấm Đẩy sang n8n khi muốn tạo credential trong n8n.`);
      }
    } catch (err) {
      onError(getServiceKeyError(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="sk-form" onSubmit={submit}>
      <div className="sk-form-head">
        <strong>{isEdit ? `Sửa key — ${entry.name}` : "Thêm key mới"}</strong>
        <button type="button" className="button secondary" onClick={onClose}>
          <X size={15} /> Đóng
        </button>
      </div>

      <label className="sk-label">
        Dịch vụ
        <select
          value={service}
          disabled={isEdit}
          onChange={(e) => {
            setService(e.target.value);
            setValues({});
            setCleared({});
          }}
        >
          {presets.map((p) => (
            <option key={p.service} value={p.service}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {preset?.description ? <p className="sk-desc">{preset.description}</p> : null}

      <label className="sk-label">
        Tên gợi nhớ
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ví dụ: Zalo OA chính"
          required
          maxLength={120}
        />
      </label>
      <label className="sk-label">
        Tên credential trong n8n
        <input
          value={credentialName}
          onChange={(e) => setCredentialName(e.target.value)}
          placeholder={name ? `MindFlow — ${name}` : "MindFlow — <tên gợi nhớ>"}
          maxLength={160}
        />
      </label>

      {preset?.fields.map((field) => {
        const has = hasValueOf(field.key);
        const isCleared = Boolean(cleared[field.key]);
        return (
          <label key={field.key} className="sk-label">
            {field.label}
            {field.required ? " *" : ""}
            {has && !isCleared ? " (đã lưu — để trống là giữ nguyên)" : ""}
            {isCleared ? " (sẽ xoá khi lưu)" : ""}
            <span className="sk-input-row">
              <input
                type={field.secret && !shown[field.key] ? "password" : "text"}
                value={values[field.key] ?? ""}
                disabled={isCleared}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                placeholder={field.hint || (has ? "••••••••" : "")}
                autoComplete="off"
              />
              {field.secret ? (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() =>
                    setShown((prev) => ({ ...prev, [field.key]: !prev[field.key] }))
                  }
                  aria-label={shown[field.key] ? "Ẩn giá trị" : "Hiện giá trị"}
                >
                  {shown[field.key] ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              ) : null}
              {has ? (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() =>
                    setCleared((prev) => ({ ...prev, [field.key]: !prev[field.key] }))
                  }
                >
                  {isCleared ? "Hoàn tác" : "Xoá giá trị"}
                </button>
              ) : null}
            </span>
          </label>
        );
      })}

      <p className="sk-desc">
        Giá trị chỉ gồm ký tự ASCII không khoảng trắng, dài 8–4096 ký tự (đúng
        định dạng token/key của các dịch vụ). Giá trị đã lưu không bao giờ hiển
        thị lại — muốn thay thì nhập giá trị mới.
      </p>
      <div className="sk-form-actions">
        <button type="submit" className="button primary" disabled={saving || !name.trim()}>
          {saving ? <LoaderCircle size={15} className="spin" /> : null}{" "}
          {isEdit ? "Lưu thay đổi" : "Thêm vào kho"}
        </button>
        <button type="button" className="button secondary" onClick={onClose} disabled={saving}>
          Huỷ
        </button>
      </div>
    </form>
  );
}
