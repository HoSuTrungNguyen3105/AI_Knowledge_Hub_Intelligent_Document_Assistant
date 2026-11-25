import { WorkflowsHub } from "../../../../components/workflows/workflows-hub";
import "../../../../components/workflows/workflows.css";

export const metadata = { title: "Agent Workflows" };

// One page, two tabs: Workflows (runs inside MindFlow) and AI Factory
// (runs through n8n). ?tab=factory opens the n8n tab — the old
// /agents/factory route redirects here.
export default async function AgentWorkflowsPage({ searchParams }) {
  const params = await searchParams;
  const initialTab =
    params?.tab === "factory" || params?.tab === "schedules" || params?.tab === "n8n"
      ? params.tab
      : "workflows";
  return <WorkflowsHub initialTab={initialTab} />;
}
