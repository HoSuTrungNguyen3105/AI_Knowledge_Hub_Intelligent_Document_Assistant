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
  const status = error?.response?.status;
  const code = error?.response?.data?.detail?.code;
  // Status-specific guidance first: a 404 on the Phase 6 routes almost always
  // means the locally running backend predates Phase 6 and was not restarted.
  if (status === 404) {
    return "Backend chưa có route Agent Teams/Workflows (404). Hãy khởi động lại backend (bản Phase 6) rồi thử lại.";
  }
  if (status === 401) return "Phiên đăng nhập đã hết hạn (401). Hãy đăng nhập lại rồi thử lại.";
  if (typeof status === "number" && status >= 500) {
    return `Lỗi máy chủ (${status}${code ? ` · ${code}` : ""}). Hãy thử lại sau ít phút.`;
  }
  const known = ERROR_MESSAGES[code] || error?.response?.data?.detail?.message;
  if (known) return status ? `${known} (${status}${code ? ` · ${code}` : ""})` : known;
  if (!error?.response && error?.request) return "Không kết nối được tới backend. Hãy kiểm tra backend đang chạy rồi thử lại.";
  return fallback;
}

// --- Starter agent set -------------------------------------------------------
// One-click bootstrap for accounts that have no Agents yet: the seven roles
// of the Phase 6 spec, created through the existing Agent API with Vietnamese
// role prompts. Tool names are the Phase 5 registry ids; the caller filters
// them against the live tools catalog (only available tools are sent).
export const STARTER_TEAM_NAME = "Nhóm Multi-Agent";

export const STARTER_AGENTS = [
  {
    name: "AI Leader", role: "coordinator", tools: ["data_analyzer"],
    description: "Coordinator/Leader — điều phối workflow, giao việc và tổng hợp kết quả cuối cùng.",
    system_prompt: "Bạn là AI Leader, Coordinator của một nhóm Agent trong MindFlow AI. Nhiệm vụ: hiểu mục tiêu chung, giao nhiệm vụ rõ ràng cho từng Agent phù hợp, theo dõi tiến độ, quyết định bước tiếp theo và tổng hợp kết quả cuối cùng cho người dùng bằng tiếng Việt. Không tự làm thay phần việc chuyên môn của Agent khác khi có thể giao việc.",
  },
  {
    name: "AI Planner", role: "planner", tools: ["data_analyzer"],
    description: "Planner — chia mục tiêu thành các task có thứ tự và phụ thuộc rõ ràng.",
    system_prompt: "Bạn là AI Planner trong MindFlow AI. Nhiệm vụ: phân tích mục tiêu, chia thành các task nhỏ có thứ tự thực hiện và phụ thuộc rõ ràng, nêu tiêu chí hoàn thành cho từng task. Trả lời bằng tiếng Việt, ngắn gọn, dạng danh sách đánh số.",
  },
  {
    name: "AI Architect", role: "architect", tools: ["data_analyzer"],
    description: "Architect — phân tích kiến trúc hiện tại và thiết kế giải pháp.",
    system_prompt: "Bạn là AI Architect trong MindFlow AI. Nhiệm vụ: phân tích kiến trúc hệ thống hiện tại dựa trên thông tin được cung cấp, chỉ ra ảnh hưởng/rủi ro và đề xuất thiết kế giải pháp khả thi. Không giả vờ đã đọc code hay sửa file nếu không có dữ liệu. Trả lời bằng tiếng Việt.",
  },
  {
    name: "AI Developer", role: "developer", tools: ["calculator", "data_analyzer"],
    description: "Developer — thực hiện nhiệm vụ kỹ thuật, đề xuất hướng dẫn/patch khi cần.",
    system_prompt: "Bạn là AI Developer trong MindFlow AI. Nhiệm vụ: thực hiện nhiệm vụ kỹ thuật được giao trong phạm vi context được cấp, trình bày giải pháp/hướng dẫn/patch đề xuất rõ ràng. Không giả vờ đã sửa file trên máy chủ. Trả lời bằng tiếng Việt, kèm ví dụ cụ thể khi hữu ích.",
  },
  {
    name: "AI Tester", role: "tester", tools: ["calculator", "data_analyzer"],
    description: "Tester — kiểm tra kết quả, tìm lỗi và gửi yêu cầu sửa khi chưa đạt.",
    system_prompt: "Bạn là AI Tester trong MindFlow AI. Nhiệm vụ: kiểm tra kết quả của Agent khác theo tiêu chí của task, liệt kê lỗi/thiếu sót cụ thể nếu có và yêu cầu sửa (REVISION_REQUEST) khi chưa đạt; xác nhận đạt khi kết quả đúng. Trả lời bằng tiếng Việt.",
  },
  {
    name: "AI Reviewer", role: "reviewer", tools: ["data_analyzer"],
    description: "Reviewer — phản biện, phê duyệt hoặc yêu cầu chỉnh sửa kết quả.",
    system_prompt: "Bạn là AI Reviewer trong MindFlow AI. Nhiệm vụ: đánh giá chất lượng kế hoạch/kết quả được gửi, phê duyệt (APPROVAL) khi đạt hoặc yêu cầu chỉnh sửa (REVISION_REQUEST) kèm lý do cụ thể khi chưa đạt. Trả lời bằng tiếng Việt, thẳng thắn và có căn cứ.",
  },
  {
    name: "AI Researcher", role: "researcher", tools: ["datetime", "data_analyzer"],
    description: "Researcher — thu thập và tóm tắt thông tin phục vụ nhiệm vụ chung.",
    system_prompt: "Bạn là AI Researcher trong MindFlow AI. Nhiệm vụ: thu thập, so sánh và tóm tắt thông tin liên quan tới nhiệm vụ từ context/công cụ được cấp, phân biệt rõ dữ kiện và suy luận, không bịa nguồn. Trả lời bằng tiếng Việt.",
  },
];

const normName = (value) => String(value || "").trim().toLowerCase();

export function missingStarterAgents(existingAgents) {
  const names = new Set((existingAgents || []).map((a) => normName(a.name)));
  return STARTER_AGENTS.filter((spec) => !names.has(normName(spec.name)));
}

// Creates the missing starter Agents (skipping names that already exist, so
// re-clicking never duplicates), then creates the starter Team when it does
// not exist yet. Stops at the first creation failure and reports exactly
// which Agents were created/reused so the UI can say what happened.
export async function createStarterSet({ existingAgents, existingTeams, provider, model, availableToolNames, createAgent, createTeam }) {
  const byName = new Map((existingAgents || []).map((a) => [normName(a.name), a]));
  const toolAllowlist = Array.isArray(availableToolNames) ? new Set(availableToolNames) : null;
  const created = [];
  const reused = [];
  const byRole = {};
  for (const spec of STARTER_AGENTS) {
    const existing = byName.get(normName(spec.name));
    if (existing) { reused.push(existing); byRole[spec.role] = existing; continue; }
    const tools = toolAllowlist ? spec.tools.filter((name) => toolAllowlist.has(name)) : [...spec.tools];
    let agent;
    try {
      agent = await createAgent({
        name: spec.name, description: spec.description, provider, model,
        system_prompt: spec.system_prompt, temperature: null, max_output_tokens: null, tools,
      });
    } catch (error) {
      return { created, reused, failed: { name: spec.name, error }, team: null, teamSkipped: false };
    }
    created.push(agent); byRole[spec.role] = agent;
  }
  const teamExists = (existingTeams || []).some((t) => normName(t.name) === normName(STARTER_TEAM_NAME));
  if (teamExists) return { created, reused, failed: null, team: null, teamSkipped: true };
  const members = STARTER_AGENTS.map((spec) => ({ agent_id: byRole[spec.role].id, role: spec.role, enabled: true }));
  try {
    const team = await createTeam({
      name: STARTER_TEAM_NAME,
      description: "Nhóm Multi-Agent mẫu gồm 7 Agent theo vai trò Phase 6, do AI Leader điều phối.",
      coordinator_agent_id: byRole.coordinator.id, members,
    });
    return { created, reused, failed: null, team, teamSkipped: false };
  } catch (error) {
    return { created, reused, failed: { name: STARTER_TEAM_NAME, error }, team: null, teamSkipped: false };
  }
}
