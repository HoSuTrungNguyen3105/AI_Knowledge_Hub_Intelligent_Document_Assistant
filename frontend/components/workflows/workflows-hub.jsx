"use client";

import { useState } from "react";
import { BookOpen, CalendarClock, Factory, GitBranch, KeyRound, Network } from "lucide-react";
import { FactoryWorkspace } from "../agents/factory-workspace";
import { WorkflowsList } from "./workflows-list";
import { SchedulesWorkspace } from "./schedules-workspace";
import { N8nPlatformWorkspace } from "./n8n-platform-workspace";
import { TemplateLibrary } from "./template-library";
import { ServiceKeysWorkspace } from "./service-keys-workspace";
import "../agents/factory.css";

// One tab registry shared by the two workflow pages, so each tab's
// label, icon and panel are defined exactly once:
// - /agents/agent-workflows hosts the two ways the same agent team can
//   run: inside MindFlow (Phase 6 workflows) or through the user's n8n
//   (AI Factory, workflow 07).
// - /agents/workflows hosts the n8n management tooling around them:
//   Workflow Management, schedules, the template library and the
//   service-key vault.
const TABS = {
  workflows: { label: "Workflows — chạy trong MindFlow", icon: GitBranch, Panel: WorkflowsList },
  factory: { label: "AI Factory — chạy qua n8n", icon: Factory, Panel: FactoryWorkspace },
  n8n: { label: "Workflow Management — quản lý n8n", icon: Network, Panel: N8nPlatformWorkspace },
  schedules: { label: "Lịch chạy — tự động theo giờ", icon: CalendarClock, Panel: SchedulesWorkspace },
  library: { label: "Thư viện mẫu — workflow có sẵn", icon: BookOpen, Panel: TemplateLibrary },
  keys: { label: "Kho key — đẩy sang n8n", icon: KeyRound, Panel: ServiceKeysWorkspace },
};

function HubTabs({ tabIds, initialTab, ariaLabel }) {
  const [tab, setTab] = useState(tabIds.includes(initialTab) ? initialTab : tabIds[0]);
  const { Panel } = TABS[tab];
  return <div>
    <div className="wf-hub-tabs" role="tablist" aria-label={ariaLabel}>
      {tabIds.map((id) => {
        const { label, icon: Icon } = TABS[id];
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`wf-hub-tab${tab === id ? " active" : ""}`}
            onClick={() => setTab(id)}
          >
            <Icon size={16} /> {label}
          </button>
        );
      })}
    </div>
    <Panel />
  </div>;
}

// The run-time tabs: agent-team workflows executed inside MindFlow or
// through n8n (AI Factory). Lives on /agents/agent-workflows.
export function AgentWorkflowsHub({ initialTab = "workflows" }) {
  return <HubTabs tabIds={["workflows", "factory"]} initialTab={initialTab} ariaLabel="Cách chạy đội Agent" />;
}

// The n8n management tabs. Lives on /agents/workflows and defaults to
// Workflow Management now that the run-time tabs have their own page.
export function WorkflowsHub({ initialTab = "n8n" }) {
  return <HubTabs tabIds={["n8n", "schedules", "library", "keys"]} initialTab={initialTab} ariaLabel="Quản lý workflow n8n" />;
}
