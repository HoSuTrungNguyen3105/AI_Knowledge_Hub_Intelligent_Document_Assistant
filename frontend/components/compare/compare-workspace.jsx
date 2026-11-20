"use client";

import { useCompare } from "../../hooks/use-compare";
import { useChatProviders } from "../../hooks/use-chat-providers";
import { ComparisonList } from "./comparison-list";
import { ComparisonView } from "./comparison-view";
import { CompareSetup } from "./compare-setup";

export function CompareWorkspace() {
  const controller = useCompare();
  const providers = useChatProviders();

  return (
    <>
      <div className="compare-layout">
        <ComparisonList comparisons={controller.comparisons} activeId={controller.activeId} onSelect={controller.selectComparison} onNew={controller.newComparison} onReload={controller.reloadList} busy={controller.busy} />
        <div className="chat-main">
          {controller.activeId
            ? <ComparisonView controller={controller} providers={providers} />
            : <CompareSetup providers={providers} busy={controller.busy === "create"} onCreate={controller.createComparison} />}
        </div>
      </div>
      <p className="chat-scope-note">Phase 4 · Multi-AI Comparison. Một model lỗi không làm hỏng cả phép so sánh. Chi phí hiển thị là ước tính từ giá công bố, không phải khoản thu được provider xác nhận.</p>
    </>
  );
}