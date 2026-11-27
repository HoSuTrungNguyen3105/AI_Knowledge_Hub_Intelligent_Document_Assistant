"use client";

import { useCallback, useEffect, useState } from "react";
import { Award, Pencil, Plus, RotateCcw, Trash2, X } from "lucide-react";
import { rolesService } from "../../services/workflows";
import { getWorkflowError, roleMeta } from "../../utils/workflows";
import { ConfirmDialog } from "../confirm-dialog";

// Chức danh (role catalog) page: the roles offered when assigning work in
// Agent Teams and collaboration rooms. System roles are built in and
// read-only; the user's own roles can be created, renamed (display name
// only — the slug stored on team members never changes) and deleted.
export function RolesWorkspace() {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });
  const [editingSlug, setEditingSlug] = useState(null);
  const [draft, setDraft] = useState({ name: "", description: "" });
  const [deletion, setDeletion] = useState(null);

  const load = useCallback(async (signal) => {
    try {
      setRoles(await rolesService.list(signal));
      setError("");
    } catch (err) {
      if (err?.code !== "ERR_CANCELED") setError(getWorkflowError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const role = await rolesService.create({
        name: form.name.trim(),
        description: form.description.trim() || null,
      });
      setRoles((prev) => [...prev, role]);
      setForm({ name: "", description: "" });
      setError("");
    } catch (err) {
      setError(getWorkflowError(err));
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (role) => {
    setEditingSlug(role.slug);
    setDraft({ name: role.name, description: role.description || "" });
  };

  const saveEdit = async (role) => {
    setBusy(true);
    try {
      const updated = await rolesService.patch(role.slug, {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
      });
      setRoles((prev) => prev.map((r) => (r.slug === role.slug ? updated : r)));
      setEditingSlug(null);
      setError("");
    } catch (err) {
      setError(getWorkflowError(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmDeletion = async () => {
    if (!deletion) return;
    setBusy(true);
    try {
      await rolesService.remove(deletion.slug);
      setRoles((prev) => prev.filter((r) => r.slug !== deletion.slug));
      setDeletion(null);
      setError("");
    } catch (err) {
      setError(getWorkflowError(err));
    } finally {
      setBusy(false);
    }
  };

  return <div className="wf-page">
    <div className="wf-header"><div><h1><Award size={26} /> Chức danh</h1>
      <p className="muted">Danh mục vai trò dùng khi phân công trong Agent Teams và phòng hợp tác — tạo nhóm là chọn đúng chức danh ở đây, Leader/Moderator của phòng cũng lấy từ phân công đó.</p></div></div>
    {error && <p className="wf-error" role="alert">{error}</p>}
    <div className="wf-card">
      <h2 style={{ marginTop: 0 }}><Plus size={17} /> Tạo chức danh mới</h2>
      <form className="wf-form" onSubmit={create}>
        <label>Tên chức danh<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Ví dụ: Content Writer" maxLength={40} required /></label>
        <label>Mô tả<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Chức danh này chịu trách nhiệm việc gì?" maxLength={500} /></label>
        <div><button className="wf-btn primary" type="submit" disabled={busy || !form.name.trim()}>
          <Plus size={16} /> {busy ? "Đang tạo…" : "Tạo chức danh"}</button></div>
      </form>
      <p className="muted" style={{ fontSize: 12.5 }}>Tên hiển thị có thể đổi sau; mã chức danh (tạo tự động từ tên) cố định để các nhóm đã gán không bị lệch.</p>
    </div>
    <div className="wf-list" style={{ marginTop: 16 }}>
      {loading ? <div className="wf-card"><p className="muted">Đang tải danh mục chức danh…</p></div>
        : roles.map((role) => <article className="wf-card wf-list-card" key={role.slug}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>
              <span className="wf-dot" style={{ background: roleMeta(role.slug).color, marginRight: 8 }} />
              {role.name}
              <span className="wf-badge" style={{ marginLeft: 8 }}>{role.is_system ? "Hệ thống" : "Tự tạo"}</span>
              <small className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>{role.slug}</small>
            </h3>
            {!role.is_system && (editingSlug === role.slug
              ? <button className="wf-btn" type="button" onClick={() => setEditingSlug(null)}><X size={15} /> Đóng</button>
              : <span className="row">
                  <button className="wf-btn" type="button" onClick={() => startEdit(role)}><Pencil size={15} /> Sửa</button>
                  <button className="wf-btn" type="button" onClick={() => setDeletion(role)}><Trash2 size={15} /> Xoá</button>
                </span>)}
          </div>
          {role.description && <p className="muted" style={{ fontSize: 12.5 }}>{role.description}</p>}
          {editingSlug === role.slug && <div className="wf-form" style={{ marginTop: 10 }}>
            <label>Tên hiển thị<input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} maxLength={40} /></label>
            <label>Mô tả<textarea rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} maxLength={500} /></label>
            <div><button className="wf-btn primary" type="button" disabled={busy || !draft.name.trim()} onClick={() => saveEdit(role)}>
              {busy ? "Đang lưu…" : "Lưu thay đổi"}</button></div>
          </div>}
        </article>)}
      {!loading && roles.length === 0 && <div className="wf-card">
        <p className="wf-error" role="alert">Không tải được danh mục chức danh.</p>
        <button className="wf-btn" type="button" onClick={() => { setLoading(true); load(); }}>
          <RotateCcw size={15} /> Thử lại</button>
      </div>}
    </div>
    <ConfirmDialog open={Boolean(deletion)} title="Xoá chức danh này?" busy={busy}
      onClose={() => setDeletion(null)} onConfirm={confirmDeletion} confirmLabel="Xoá chức danh">
      <p>Chức danh <b>{deletion?.name}</b> sẽ biến mất khỏi danh mục. Các nhóm đã gán chức danh này vẫn giữ mã của nó trong cấu hình — chỉ là không chọn lại được ở đây nữa.</p>
    </ConfirmDialog>
  </div>;
}
