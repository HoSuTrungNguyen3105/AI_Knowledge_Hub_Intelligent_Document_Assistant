import { WorkflowsHub } from "../../../../components/workflows/workflows-hub";
import "../../../../components/workflows/workflows.css";

export const metadata = { title: "Workflows" };

// The n8n management tooling: Workflow Management (default tab),
// schedules, the template library and the service-key vault. The
// run-time tabs (MindFlow workflows + AI Factory) live on their own
// page at /agents/agent-workflows.
export default async function WorkflowsPage({ searchParams }) {
  const params = await searchParams;
  const initialTab =
    params?.tab === "schedules" ||
    params?.tab === "library" ||
    params?.tab === "keys"
      ? params.tab
      : "n8n";
  return <WorkflowsHub initialTab={initialTab} />;
}
