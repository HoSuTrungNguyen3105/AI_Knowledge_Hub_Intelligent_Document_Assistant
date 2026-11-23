import { WorkflowDetail } from "../../../../../components/workflows/workflow-detail";
import "../../../../../components/workflows/workflows.css";

export const metadata = { title: "Workflow Workspace" };
export default async function WorkflowDetailPage({ params }) {
  const { id } = await params;
  return <WorkflowDetail workflowId={id} />;
}
