"use client";

import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { agentsService } from "../../services/agents";
import { getAgentError } from "../../utils/agents";

// Quick rename for one Agent. The backend AgentPatch schema accepts a
// partial update, so renaming sends { name } only and leaves provider,
// model, tools and prompts exactly as stored.
export function RenameAgentDialog({ agent, onClose, onRenamed }) {
  const dialog = useRef(null);
  const titleId = useId();
  const [name, setName] = useState(agent?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    try {
      if (agent) dialog.current?.showModal();
      else dialog.current?.close();
    } catch { /* dialog already in the requested state */ }
  }, [agent]);

  if (!agent) return null;

  async function submit(event) {
    event.preventDefault();
    const clean = name.trim();
    if (!clean || busy) return;
    if (clean === agent.name) { onClose(); return; }
    setBusy(true); setError("");
    try {
      const updated = await agentsService.patch(agent.id, { name: clean });
      onRenamed?.(updated);
      onClose();
    } catch (e) {
      setError(getAgentError(e, "Không đổi tên được Agent."));
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="confirm-dialog" aria-labelledby={titleId}
    onCancel={(event) => { if (busy) event.preventDefault(); else onClose(); }}
    onClick={(event) => { if (!busy && event.target === event.currentTarget) onClose(); }}>
    <form className="confirm-content" onSubmit={submit}>
      <h2 id={titleId}>Đổi tên Agent</h2>
      <div className="confirm-description">
        <label className="field-label" htmlFor="rename-agent-name">Tên mới</label>
        <input id="rename-agent-name" value={name} onChange={(event) => setName(event.target.value)}
          required maxLength={120} disabled={busy} autoFocus style={{ width: "100%" }} />
        <p className="setup-note">Chỉ đổi tên hiển thị. Provider, model, công cụ và system prompt giữ nguyên.
          Lưu ý: vai trò suy từ tên (Leader/Planner/Developer…) có thể thay đổi theo tên mới khi Agent được xếp vào nhóm.</p>
        {error && <p className="composer-error" role="alert">{error}</p>}
      </div>
      <div className="confirm-actions">
        <button type="button" className="button secondary" onClick={onClose} disabled={busy}>Hủy</button>
        <button type="submit" className="button primary" disabled={busy || !name.trim()}>
          {busy && <LoaderCircle size={16} className="spin" />}Lưu tên mới</button>
      </div>
    </form>
  </dialog>;
}
