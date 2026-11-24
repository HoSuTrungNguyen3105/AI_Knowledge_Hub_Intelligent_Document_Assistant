"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Plus, Trash2, UserPlus, Users } from "lucide-react";
import { getWorkspaceError, workspacesService } from "../../services/workspaces";
import { ConfirmDialog } from "../confirm-dialog";

const ROLE_LABELS = {
  owner: "Chủ sở hữu",
  admin: "Quản trị viên",
  leader: "Trưởng nhóm",
  employee: "Nhân viên",
  operator: "Vận hành AI",
  viewer: "Chỉ xem",
};
const ASSIGNABLE = ["admin", "leader", "employee", "operator", "viewer"];
const roleLabel = (role) => ROLE_LABELS[role] || role;

export function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", description: "" });
  const [selectedId, setSelectedId] = useState("");
  const [members, setMembers] = useState([]);
  const [membersError, setMembersError] = useState("");
  const [editForm, setEditForm] = useState({ name: "", description: "" });
  const [memberForm, setMemberForm] = useState({ email: "", role: "employee" });
  const [deletion, setDeletion] = useState(null);

  const selected = workspaces.find((w) => w.id === selectedId) || null;
  const canManage = selected && (selected.my_role === "owner" || selected.my_role === "admin");

  const loadWorkspaces = useCallback(async (signal) => {
    try {
      const list = await workspacesService.list(signal);
      setWorkspaces(list);
      setError("");
      setSelectedId((current) => current || list[0]?.id || "");
    } catch (e) {
      if (e?.name !== "AbortError") setError(getWorkspaceError(e, "Không tải được danh sách workspace."));
    } finally { setLoading(false); }
  }, []);

  const loadMembers = useCallback(async (id, signal) => {
    if (!id) { setMembers([]); return; }
    try {
      setMembers(await workspacesService.listMembers(id, signal));
      setMembersError("");
    } catch (e) {
      if (e?.name !== "AbortError") setMembersError(getWorkspaceError(e, "Không tải được danh sách thành viên."));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadWorkspaces(controller.signal);
    return () => controller.abort();
  }, [loadWorkspaces]);

  useEffect(() => {
    if (!selected) return;
    setEditForm({ name: selected.name, description: selected.description || "" });
    const controller = new AbortController();
    loadMembers(selected.id, controller.signal);
    return () => controller.abort();
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(event) {
    event.preventDefault();
    setBusy(true); setNotice(""); setError("");
    try {
      const created = await workspacesService.create({
        name: createForm.name,
        description: createForm.description || null,
      });
      setCreateForm({ name: "", description: "" });
      setNotice(`Đã tạo workspace "${created.name}".`);
      await loadWorkspaces();
      setSelectedId(created.id);
    } catch (e) { setError(getWorkspaceError(e, "Không tạo được workspace.")); }
    finally { setBusy(false); }
  }

  async function saveEdit(event) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true); setNotice(""); setError("");
    try {
      await workspacesService.patch(selected.id, {
        name: editForm.name,
        description: editForm.description || null,
      });
      setNotice("Đã lưu thay đổi workspace.");
      await loadWorkspaces();
    } catch (e) { setError(getWorkspaceError(e, "Không lưu được thay đổi.")); }
    finally { setBusy(false); }
  }

  async function addMember(event) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true); setNotice(""); setError("");
    try {
      const member = await workspacesService.addMember(selected.id, memberForm);
      setMemberForm({ email: "", role: "employee" });
      setNotice(`Đã thêm ${member.email} với vai trò ${roleLabel(member.role)}.`);
      await Promise.allSettled([loadMembers(selected.id), loadWorkspaces()]);
    } catch (e) { setError(getWorkspaceError(e, "Không thêm được thành viên.")); }
    finally { setBusy(false); }
  }

  async function changeRole(member, role) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await workspacesService.patchMember(selected.id, member.user_id, { role });
      await loadMembers(selected.id);
    } catch (e) { setError(getWorkspaceError(e, "Không đổi được vai trò.")); }
    finally { setBusy(false); }
  }

  async function removeMember(member) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await workspacesService.removeMember(selected.id, member.user_id);
      setNotice(`Đã xoá ${member.email} khỏi workspace.`);
      await Promise.allSettled([loadMembers(selected.id), loadWorkspaces()]);
    } catch (e) { setError(getWorkspaceError(e, "Không xoá được thành viên.")); }
    finally { setBusy(false); }
  }

  async function confirmDeletion() {
    if (!deletion) return;
    setBusy(true); setError("");
    try {
      await workspacesService.remove(deletion.id);
      setNotice(`Đã xoá workspace "${deletion.name}".`);
      setDeletion(null);
      setSelectedId("");
      await loadWorkspaces();
    } catch (e) { setError(getWorkspaceError(e, "Không xoá được workspace.")); setDeletion(null); }
    finally { setBusy(false); }
  }

  return <div className="wf-page">
    <div className="wf-header"><div><h1><Building2 size={26} /> Workspaces</h1>
      <p className="muted">Không gian làm việc của bạn và các workspace nhóm bạn tham gia. Dữ liệu hiện vẫn thuộc về từng tài khoản; các module sẽ chuyển sang phạm vi workspace theo từng đợt.</p></div></div>
    {error && <p className="wf-error" role="alert">{error}</p>}
    {notice && <p className="muted" role="status">{notice}</p>}

    <div className="wf-card">
      <h2><Plus size={17} /> Tạo workspace nhóm</h2>
      <form className="wf-form" onSubmit={create}>
        <label>Tên workspace<input value={createForm.name} onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} placeholder="Ví dụ: Nhóm sản phẩm" required /></label>
        <label>Mô tả<textarea rows={2} value={createForm.description} onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} /></label>
        <div><button className="wf-btn primary" type="submit" disabled={busy}><Plus size={15} /> Tạo workspace</button></div>
      </form>
    </div>

    <div className="wf-list">
      {loading ? <p className="wf-empty">Đang tải…</p>
        : workspaces.map((ws) => <article className="wf-card wf-list-card" key={ws.id}
            style={ws.id === selectedId ? { outline: "2px solid var(--accent, #7c3aed)" } : undefined}>
          <h3>{ws.name}</h3>
          {ws.description && <p className="muted" style={{ fontSize: 12.5 }}>{ws.description}</p>}
          <div className="row"><span>{ws.kind === "personal" ? "Không gian cá nhân" : "Workspace nhóm"} · Vai trò của bạn: <b>{roleLabel(ws.my_role)}</b> · {ws.member_count} thành viên</span></div>
          <div className="row"><button className="wf-btn" type="button" onClick={() => setSelectedId(ws.id)}>
            <Users size={15} /> {ws.id === selectedId ? "Đang xem" : "Xem chi tiết"}</button></div>
        </article>)}
    </div>

    {selected && <div className="wf-card" style={{ marginTop: 16 }}>
      <h2><Users size={17} /> Chi tiết — {selected.name}</h2>
      {canManage ? <form className="wf-form" onSubmit={saveEdit}>
        <label>Tên workspace<input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required /></label>
        <label>Mô tả<textarea rows={2} value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} /></label>
        <div><button className="wf-btn primary" type="submit" disabled={busy}>Lưu thay đổi</button></div>
      </form> : <p className="muted" style={{ fontSize: 12.5 }}>Bạn là {roleLabel(selected.my_role)} — chỉ chủ sở hữu/quản trị viên mới sửa được thông tin và thành viên.</p>}

      <h3 style={{ marginTop: 18 }}>Thành viên</h3>
      {membersError ? <p className="wf-error" role="alert">{membersError}</p>
        : members.map((m) => <div className="row" key={m.user_id} style={{ justifyContent: "space-between" }}>
          <span><b>{m.name || m.email}</b> · {m.email}</span>
          {canManage && m.role !== "owner" ? <>
            <select aria-label={`Vai trò của ${m.email}`} value={m.role} disabled={busy}
              onChange={(e) => changeRole(m, e.target.value)}>
              {ASSIGNABLE.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
            </select>
            <button className="wf-btn" type="button" disabled={busy} onClick={() => removeMember(m)}><Trash2 size={14} /> Xoá</button>
          </> : <span>{roleLabel(m.role)}</span>}
        </div>)}

      {canManage && <form className="wf-form" onSubmit={addMember} style={{ marginTop: 14 }}>
        <label>Email thành viên (phải có tài khoản MindFlow)<input type="email" value={memberForm.email} onChange={(e) => setMemberForm({ ...memberForm, email: e.target.value })} placeholder="ban@congty.com" required /></label>
        <label>Vai trò<select value={memberForm.role} onChange={(e) => setMemberForm({ ...memberForm, role: e.target.value })}>
          {ASSIGNABLE.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
        </select></label>
        <div><button className="wf-btn primary" type="submit" disabled={busy}><UserPlus size={15} /> Thêm thành viên</button></div>
      </form>}

      {selected.my_role === "owner" && selected.kind !== "personal" && <div className="row" style={{ marginTop: 14 }}>
        <button className="wf-btn" type="button" onClick={() => setDeletion(selected)}><Trash2 size={15} /> Xoá workspace này</button>
      </div>}
    </div>}

    <ConfirmDialog open={Boolean(deletion)} title="Xoá workspace này?" busy={busy}
      onClose={() => setDeletion(null)} onConfirm={confirmDeletion} confirmLabel="Xoá workspace">
      <p>Workspace và danh sách thành viên sẽ bị xoá. Dữ liệu Agent/workflow của từng tài khoản không bị xoá.</p>
    </ConfirmDialog>
  </div>;
}
