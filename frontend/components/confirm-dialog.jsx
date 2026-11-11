"use client";

import { useEffect, useId, useRef } from "react";
import { LoaderCircle } from "lucide-react";

export function ConfirmDialog({ open, title, children, busy, onClose, onConfirm, confirmLabel = "Xác nhận" }) {
  const dialog = useRef(null);
  const titleId = useId();
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  return <dialog ref={dialog} className="confirm-dialog" aria-labelledby={titleId} onCancel={(event) => { if (busy) event.preventDefault(); else onClose(); }} onClick={(event) => { if (!busy && event.target === event.currentTarget) onClose(); }}>
    <div className="confirm-content"><h2 id={titleId}>{title}</h2><div className="confirm-description">{children}</div><div className="confirm-actions"><button type="button" className="button secondary" onClick={onClose} disabled={busy} autoFocus>Hủy</button><button type="button" className="button danger" onClick={onConfirm} disabled={busy}>{busy && <LoaderCircle size={16} className="spin" />}{confirmLabel}</button></div></div>
  </dialog>;
}
