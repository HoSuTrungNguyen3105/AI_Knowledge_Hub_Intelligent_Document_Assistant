import { redirect } from "next/navigation";

// AI Factory was merged into the Workflows page as its second tab (both
// run the same agent teams). Old bookmarks land on the right tab.
export default function AIFactoryPage() {
  redirect("/agents/workflows?tab=factory");
}
