import { redirect } from "next/navigation";

// AI Factory is the second tab of the Agent Workflows page (both tabs
// run the same agent teams). Old bookmarks land on the right tab.
export default function AIFactoryPage() {
  redirect("/agents/agent-workflows?tab=factory");
}
