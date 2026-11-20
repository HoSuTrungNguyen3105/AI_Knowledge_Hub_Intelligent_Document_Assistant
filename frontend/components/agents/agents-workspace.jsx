"use client";

import { useAgents } from "../../hooks/use-agents";
import { ConfirmDialog } from "../confirm-dialog";
import { AgentEditor } from "./agent-editor";
import { AgentList } from "./agent-list";
import { AgentView } from "./agent-view";

export function AgentsWorkspace() {
  const controller = useAgents();
  const { activeId, agent, detailLoading, detailError, busy, tools, deletion, setDeletion, confirmDeletion } = controller;
  return <>
    <div className="agents-layout"><AgentList controller={controller} /><div className="chat-main">
      {!activeId ? <AgentEditor key={`new:${controller.selectionRevision}`} tools={tools} busy={Boolean(busy)} onSave={controller.saveAgent} reloadTools={controller.reloadTools} /> : detailLoading ? <div className="setup-panel" role="status" aria-label="Đang tải cấu hình Agent"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div> : detailError ? <div className="setup-panel"><p className="composer-error" role="alert">{detailError}</p><button type="button" className="button secondary" onClick={controller.reloadDetail}>Thử lại cấu hình Agent</button></div> : agent ? <AgentView key={agent.id} controller={controller} /> : null}
    </div></div>
    <p className="chat-scope-note">Phase 5 · Agent Studio. Dữ liệu thật, riêng theo tài khoản. Chi phí chỉ là ước tính, không phải khoản thu được provider xác nhận. Không có bộ nhớ bền vững giữa các lượt chạy.</p>
    <ConfirmDialog open={Boolean(deletion)} title={deletion?.executionId ? "Xóa lượt thực thi này?" : "Xóa Agent này?"} busy={busy === "delete"} onClose={() => setDeletion(null)} onConfirm={confirmDeletion} confirmLabel={deletion?.executionId ? "Xóa lượt thực thi" : "Xóa Agent"}><p>{deletion?.executionId ? "Prompt, các bước và kết quả của lượt thực thi này sẽ bị xóa." : "Cấu hình Agent và toàn bộ lịch sử thực thi của Agent sẽ bị xóa."}</p><p>Chỉ dữ liệu trong tài khoản của bạn bị ảnh hưởng. Thao tác không thể hoàn tác.</p></ConfirmDialog>
  </>;
}
