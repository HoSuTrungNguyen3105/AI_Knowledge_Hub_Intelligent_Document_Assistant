"use client";

import { useState } from "react";
import { Factory, GitBranch } from "lucide-react";
import { FactoryWorkspace } from "../agents/factory-workspace";
import { WorkflowsList } from "./workflows-list";
import "../agents/factory.css";

// One page for the two ways the same agent team can run: inside MindFlow
// (Phase 6 workflows) or through the user's n8n (AI Factory, workflow 07).
// Same agents, same kind of goal — so they share one menu entry with two
// tabs instead of living on two separate pages.
export function WorkflowsHub({ initialTab = "workflows" }) {
  const [tab, setTab] = useState(initialTab === "factory" ? "factory" : "workflows");
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
    </div>
    {tab === "workflows" ? <WorkflowsList /> : <FactoryWorkspace />}
  </div>;
}
