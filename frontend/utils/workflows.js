// Pure derivations for the Phase 6 workspace. Everything here is computed
// from real API data (teams, workflows, tasks, messages, events) — no
// hard-coded activity, counts or timings.
export const ROLE_META = {
  coordinator: { label: "Coordinator", short: "Leader", color: "#7c3aed", soft: "#ede9fe" },
  planner: { label: "Planner", short: "Planner", color: "#2563eb", soft: "#dbeafe" },
  architect: { label: "Architect", short: "Architect", color: "#16a34a", soft: "#dcfce7" },
  developer: { label: "Developer", short: "Developer", color: "#ea580c", soft: "#ffedd5" },
  tester: { label: "Tester", short: "Tester", color: "#0d9488", soft: "#ccfbf1" },
  reviewer: { label: "Reviewer", short: "Reviewer", color: "#9333ea", soft: "#f3e8ff" },
  researcher: { label: "Researcher", short: "Researcher", color: "#059669", soft: "#d1fae5" },
  member: { label: "Member", short: "Agent", color: "#64748b", soft: "#e2e8f0" },
};

export function roleMeta(role) {
  return ROLE_META[String(role || "member").toLowerCase()] || ROLE_META.member;
}

export const WORKFLOW_STATUS = {
  queued: { label: "Queued", color: "#2563eb" },
  running: { label: "Running", color: "#16a34a" },
  waiting: { label: "Paused", color: "#d97706" },
  completed: { label: "Completed", color: "#16a34a" },
  failed: { label: "Failed", color: "#dc2626" },
  cancelled: { label: "Cancelled", color: "#64748b" },
};

export const TASK_COLUMNS = [
  { key: "pending", label: "Pending" },
  { key: "in_progress", label: "In Progress" },
  { key: "review", label: "Review" },
  { key: "completed", label: "Completed" },
  { key: "failed", label: "Failed" },
];

export function progressOf(tasks) {
  const total = tasks.length;
  const completed = tasks.filter((t) => t.status === "completed").length;
  const inProgress = tasks.filter((t) => t.status === "in_progress" || t.status === "review").length;
  const pending = tasks.filter((t) => t.status === "pending").length;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  return { total, completed, inProgress, pending, percent };
}

// Agent card status derived from that agent's latest task in this workflow.
export function agentStatus(agentId, tasks, workflow) {
  const mine = tasks.filter((t) => t.assigned_agent_id === agentId);
  const latest = mine[mine.length - 1];
  if (latest?.status === "in_progress") return { label: "Working", color: "#16a34a", note: latest.title };
  if (latest?.status === "review") return { label: "Reviewing", color: "#d97706", note: latest.title };
  if (latest?.status === "completed") return { label: "Done", color: "#16a34a", note: latest.title };
  if (latest?.status === "failed") return { label: "Failed", color: "#dc2626", note: latest.title };
  if (workflow?.status === "completed") return { label: "Done", color: "#16a34a", note: "Workflow completed" };
  return { label: "Waiting", color: "#2563eb", note: "Waiting for task…" };
}

// Stepper Plan → Develop → Test → Review → Complete, derived from the roles
// of completed tasks and the workflow status.
export function stepperOf(tasks, workflow) {
  const doneRoles = new Set(
    tasks.filter((t) => t.status === "completed").map((t) => (t.title.split(":")[0] || "").toLowerCase()),
  );
  const steps = [
    { key: "plan", label: "Plan", roles: ["planner"] },
    { key: "develop", label: "Develop", roles: ["architect", "developer", "researcher"] },
    { key: "test", label: "Test", roles: ["tester"] },
    { key: "review", label: "Review", roles: ["reviewer"] },
    { key: "complete", label: "Complete", roles: [] },
  ];
  return steps.map((step) => {
    let state = "todo";
    if (step.key === "complete") state = workflow?.status === "completed" ? "done" : "todo";
    else if (step.roles.some((r) => doneRoles.has(r))) state = "done";
    else if (tasks.some((t) => t.status === "in_progress" && step.roles.includes((t.title.split(":")[0] || "").toLowerCase()))) state = "active";
    return { ...step, state };
  });
}

export function elapsedLabel(workflow, now = Date.now()) {
  if (!workflow?.created_at) return null;
  const start = new Date(workflow.created_at).getTime();
  const end = workflow.completed_at ? new Date(workflow.completed_at).getTime() : now;
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export function timeLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const ERROR_MESSAGES = {
  team_not_found: "Không tìm thấy nhóm Agent.",
  workflow_not_found: "Không tìm thấy workflow.",
  invalid_team_members: "Chỉ được chọn Agent thuộc tài khoản của bạn.",
  coordinator_not_in_team: "Coordinator phải là thành viên của nhóm.",
  workflow_not_runnable: "Workflow không ở trạng thái có thể thực hiện thao tác này.",
  workflow_already_running: "Workflow đang chạy.",
};

export function getWorkflowError(error, fallback = "Đã xảy ra lỗi. Vui lòng thử lại.") {
  const code = error?.response?.data?.detail?.code;
  return ERROR_MESSAGES[code] || error?.response?.data?.detail?.message || fallback;
}
