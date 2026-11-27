"use client";

import { useState } from "react";
import { BookOpen, CalendarClock, Factory, GitBranch, Network } from "lucide-react";
import { FactoryWorkspace } from "../agents/factory-workspace";
import { WorkflowsList } from "./workflows-list";
import { SchedulesWorkspace } from "./schedules-workspace";
import { N8nPlatformWorkspace } from "./n8n-platform-workspace";
import { TemplateLibrary } from "./template-library";
import "../agents/factory.css";

// One page for the two ways the same agent team can run: inside MindFlow
// (Phase 6 workflows) or through the user's n8n (AI Factory, workflow 07).
// Same agents, same kind of goal — so they share one menu entry with two
// tabs instead of living on two separate pages.
export function WorkflowsHub({ initialTab = "workflows" }) {
  const [tab, setTab] = useState(
    ["factory", "schedules", "n8n", "library"].includes(initialTab) ? initialTab : "workflows",
  );
  return <div>
    <div className="wf-hub-tabs" role="tablist" aria-label="Cách chạy đội Agent">
      <button
        type="button"
        role="tab"
        aria-selected={tab === "workflows"}
        className={`wf-hub-tab${tab === "workflows" ? " active" : ""}`}
        onClick={() => setTab("workflows")}
      >
        <GitBranch size={16} /> Workflows — chạy trong MindFlow
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === "factory"}
        className={`wf-hub-tab${tab === "factory" ? " active" : ""}`}
        onClick={() => setTab("factory")}
      >
        <Factory size={16} /> AI Factory — chạy qua n8n
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === "schedules"}
        className={`wf-hub-tab${tab === "schedules" ? " active" : ""}`}
        onClick={() => setTab("schedules")}
      >
        <CalendarClock size={16} /> Lịch chạy — tự động theo giờ
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === "n8n"}
        className={`wf-hub-tab${tab === "n8n" ? " active" : ""}`}
        onClick={() => setTab("n8n")}
      >
        <Network size={16} /> Workflow Management — quản lý n8n
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={tab === "library"}
        className={`wf-hub-tab${tab === "library" ? " active" : ""}`}
        onClick={() => setTab("library")}
      >
        <BookOpen size={16} /> Thư viện mẫu — workflow có sẵn
      </button>
    </div>
    {tab === "workflows" ? (
      <WorkflowsList />
    ) : tab === "factory" ? (
      <FactoryWorkspace />
    ) : tab === "schedules" ? (
      <SchedulesWorkspace />
    ) : tab === "n8n" ? (
      <N8nPlatformWorkspace />
    ) : (
      <TemplateLibrary />
    )}
  </div>;
}
