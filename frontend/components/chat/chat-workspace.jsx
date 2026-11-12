"use client";

import { useChat } from "../../hooks/use-chat";
import { useChatProviders } from "../../hooks/use-chat-providers";
import { ConversationList } from "./conversation-list";
import { ConversationView } from "./conversation-view";
import { SetupPanel } from "./setup-panel";

export function ChatWorkspace() {
  const controller = useChat();
  const providers = useChatProviders();

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MindFlow AI · Không gian cá nhân</p>
          <h1>AI Chat</h1>
          <p className="muted">Trò chuyện với nhiều model qua provider đã cấu hình. Streaming, lịch sử và hội thoại riêng tư.</p>
        </div>
      </div>
      <div className="chat-layout">
        <ConversationList conversations={controller.conversations} activeId={controller.activeId} onSelect={controller.selectConversation} onNew={controller.newConversation} onReload={controller.reloadList} busy={controller.busy} />
        <div className="chat-main">
          {controller.activeId
            ? <ConversationView controller={controller} />
            : <SetupPanel providers={providers} busy={controller.busy === "create"} onCreate={controller.createConversation} />}
        </div>
      </div>
      <p className="chat-scope-note">Phase 3 · Multi-model chat. Tài liệu/RAG, Compare AI và Agent triển khai ở các phase sau; không có dữ liệu AI mẫu.</p>
    </>
  );
}