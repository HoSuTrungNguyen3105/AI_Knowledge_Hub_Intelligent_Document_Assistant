"use client";

import { CircleAlert, LoaderCircle, Play, RotateCw, Square, Trash2 } from "lucide-react";
import { RunColumn } from "./run-column";
import { SynthesisPanel } from "./synthesis-panel";
import { ConfirmDialog } from "../confirm-dialog";

export function ComparisonView({ controller, providers }) {
  const {
    comparison, detailLoading, detailError, runText, activeRuns = {}, synthesisText, phase, isStreaming,
    streamError, busy, confirmDelete, setConfirmDelete, canExecute, canSynthesize,
    execute, synthesize, stop, deleteComparison, reloadDetail,
  } = controller;

  if (detailLoading) return <div className="thread-state" role="status"><LoaderCircle size={22} className="spin" /><p>Đang tải phép so sánh…</p></div>;
  if (detailError) return <div className="thread-state"><div className="error-panel" role="alert"><CircleAlert size={22} /><div><h2>Chưa tải được phép so sánh</h2><p>{detailError}</p></div><button type="button" className="button secondary" onClick={reloadDetail}>Thử lại</button></div></div>;
  if (!comparison) return null;

  const hasResults = comparison.runs.some((run) => run.status !== "pending");
  const executing = phase === "execute";

  return (
    <section className="conversation-view">
      <header className="conversation-header">
        <div className="conversation-title">
          <h2>{comparison.title}</h2>
          <span className="conversation-model">{comparison.runs.length} model · {comparison.runs.map((run) => run.provider).join(", ")}</span>
        </div>
        <div className="conversation-tools">
          {executing ? (
            <button type="button" className="button secondary" onClick={stop}><Square size={15} />Dừng</button>
          ) : (
            <button type="button" className="button primary" onClick={execute} disabled={!canExecute || Boolean(busy)}>
              {hasResults ? <RotateCw size={16} /> : <Play size={16} />}{hasResults ? "Chạy lại" : "Chạy so sánh"}
            </button>
          )}
          <button type="button" className="icon-button danger" onClick={() => setConfirmDelete(true)} aria-label="Xóa phép so sánh" title="Xóa" disabled={Boolean(busy) || isStreaming}><Trash2 size={17} /></button>
        </div>
      </header>

      <div className="comparison-body">
        <div className="comparison-prompt">
          <span className="message-role">Bạn</span>
          <p className="message-text">{comparison.prompt}</p>
        </div>
        {streamError && <p className="composer-error" role="alert"><CircleAlert size={15} />{streamError}</p>}
        <div className="run-columns">
          {comparison.runs.map((run) => (
            <RunColumn key={run.id} run={run} liveText={runText[run.id]} streaming={executing && Boolean(activeRuns[run.id])} />
          ))}
        </div>
        <SynthesisPanel
          providers={providers}
          synthesis={comparison.synthesis}
          liveText={synthesisText}
          canSynthesize={canSynthesize}
          busy={Boolean(busy)}
          streaming={phase === "synthesize"}
          onSynthesize={synthesize}
        />
      </div>

      <ConfirmDialog open={confirmDelete} title="Xóa phép so sánh này?" busy={busy === "delete"} onClose={() => setConfirmDelete(false)} onConfirm={deleteComparison} confirmLabel="Xóa phép so sánh">
        <p>Toàn bộ câu trả lời và kết quả tổng hợp sẽ bị xóa khỏi tài khoản của bạn.</p>
        <p>Dữ liệu của tài khoản khác không bị ảnh hưởng. Thao tác này không thể hoàn tác.</p>
      </ConfirmDialog>
    </section>
  );
}