"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ClipboardList, Play, Sparkles, TriangleAlert, Users } from "lucide-react";
import { agentsService } from "../../services/agents";
import { workflowsService } from "../../services/workflows";
import { OUTPUT_TYPES, getWorkflowError, roleMeta } from "../../utils/workflows";

const COUNTS = [1, 2, 3, 5];
const COMPLEXITY = {
  low: ["Thấp", "low"],
  medium: ["Trung bình", "medium"],
  high: ["Cao", "high"],
  critical: ["Rất cao", "high"],
};

// Dynamic planning panel: the user describes the work once, the AI
// Leader analyzes + decomposes + sizes the team (auto) or validates the
// user's own size (manual), and applying the plan creates the team and
// the workflow in one step. Everything rendered here comes from the
// backend plan — no demo data.
export function WorkflowPlanner() {
  const router = useRouter();
  const [agents, setAgents] = useState([]);
  const [agentsError, setAgentsError] = useState("");
  const [form, setForm] = useState({ agent_id: "", title: "", goal: "", answers: "" });
  const [mode, setMode] = useState("auto");
  const [count, setCount] = useState(2);
  const [plan, setPlan] = useState(null);
  const [planning, setPlanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [applyForm, setApplyForm] = useState({
    team_name: "",
    output_type: "text",
    requires_approval: false,
  });

  useEffect(() => {
    let cancelled = false;
    agentsService
      .list()
      .then((list) => {
        if (cancelled) return;
        setAgents(list);
        // Prefer an agent whose name reads as the leader/coordinator.
        const leader =
          list.find((a) => /lead|coordinat|manager|leader/i.test(a.name)) || list[0];
        if (leader) setForm((f) => ({ ...f, agent_id: f.agent_id || leader.id }));
      })
      .catch(() => {
        if (!cancelled) setAgentsError("Không tải được danh sách Agent.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function runPlan(event) {
    event.preventDefault();
    setError("");
    setPlan(null);
    setPlanning(true);
    try {
      const result = await workflowsService.plan({
        agent_id: form.agent_id,
        title: form.title.trim(),
        goal: form.goal.trim(),
        mode,
        agent_count: mode === "manual" ? count : undefined,
        answers: form.answers.trim() || undefined,
      });
      setPlan(result);
    } catch (e) {
      setError(getWorkflowError(e, "Không lập được kế hoạch."));
    } finally {
      setPlanning(false);
    }
  }

  async function applyPlan() {
    if (!plan) return;
    setError("");
    setApplying(true);
    try {
      const result = await workflowsService.applyPlan({
        plan,
        team_name: applyForm.team_name.trim() || undefined,
        output_type: applyForm.output_type,
        requires_approval: applyForm.requires_approval,
      });
      router.push(`/agents/workflows/${result.workflow.id}`);
    } catch (e) {
      setError(getWorkflowError(e, "Không áp dụng được kế hoạch."));
    } finally {
      setApplying(false);
    }
  }

  const taskByKey = new Map((plan?.tasks || []).map((t) => [t.key, t]));
  const suggestionsByTask = new Map();
  for (const s of plan?.human_suggestions || []) {
    const list = suggestionsByTask.get(s.task_key) || [];
    list.push(s);
    suggestionsByTask.set(s.task_key, list);
  }
  const complexity = COMPLEXITY[plan?.complexity] || COMPLEXITY.medium;

  return (
    <div className="wf-card">
      <h2>
        <Sparkles size={17} /> Lập kế hoạch bằng AI Leader
      </h2>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
        Mô tả công việc một lần: AI Leader phân tích yêu cầu, chia task có phụ thuộc,
        đề xuất số Agent phù hợp (1/2/3/5) và ghép đội từ các Agent thật của bạn.
        Duyệt kế hoạch xong mới tạo đội và workflow — chưa có gì chạy tự động.
      </p>
      {error && (
        <p className="wf-error" role="alert">
          {error}
        </p>
      )}
      {agentsError && (
        <p className="wf-error" role="alert">
          {agentsError}
        </p>
      )}
      <form className="wf-form" onSubmit={runPlan} style={{ marginTop: 14 }}>
        <label>
          AI Leader (Agent phân tích và điều phối)
          <select
            value={form.agent_id}
            onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} — {a.provider}/{a.model}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tiêu đề công việc
          <input
            value={form.title}
            maxLength={200}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Ví dụ: Landing Page bán giày sneaker"
            required
          />
        </label>
        <label>
          Yêu cầu chi tiết
          <textarea
            rows={5}
            value={form.goal}
            onChange={(e) => setForm({ ...form, goal: e.target.value })}
            placeholder="Mục tiêu, phạm vi, tính năng chính, ràng buộc, đầu ra mong muốn..."
            required
          />
        </label>
        <span className="wf-design-label">Chế độ chọn số Agent</span>
        <div className="wf-chip-row">
          <button
            type="button"
            aria-pressed={mode === "auto"}
            className={`wf-chip${mode === "auto" ? " selected" : ""}`}
            onClick={() => setMode("auto")}
          >
            Tự động — AI đề xuất
          </button>
          <button
            type="button"
            aria-pressed={mode === "manual"}
            className={`wf-chip${mode === "manual" ? " selected" : ""}`}
            onClick={() => setMode("manual")}
          >
            Thủ công — tôi tự chọn
          </button>
          {mode === "manual" &&
            COUNTS.map((n) => (
              <button
                type="button"
                key={n}
                aria-pressed={count === n}
                className={`wf-chip${count === n ? " selected" : ""}`}
                onClick={() => setCount(n)}
              >
                {n} Agent
              </button>
            ))}
        </div>
        {plan?.clarifying_questions?.length > 0 && (
          <label>
            Trả lời các câu hỏi làm rõ của AI Leader (rồi bấm lập kế hoạch lại)
            <textarea
              rows={3}
              value={form.answers}
              onChange={(e) => setForm({ ...form, answers: e.target.value })}
              placeholder="Bổ sung thông tin còn thiếu mà AI đã hỏi..."
            />
          </label>
        )}
        <div>
          <button
            className="wf-btn primary"
            type="submit"
            disabled={planning || !form.agent_id || !form.title.trim() || !form.goal.trim()}
          >
            <ClipboardList size={16} />{" "}
            {planning ? "Đang phân tích..." : "Phân tích & lập kế hoạch"}
          </button>
        </div>
        <small className="muted">Một lượt phân tích có thể mất 30-60 giây tuỳ model.</small>
      </form>

      {plan && (
        <div className="wf-plan">
          <h3 style={{ marginTop: 18 }}>Kế hoạch đề xuất</h3>
          <p style={{ marginTop: 8 }}>{plan.summary}</p>
          <div className="row" style={{ marginTop: 8 }}>
            <span className={`wf-badge ${complexity[1]}`}>
              Độ phức tạp: {complexity[0]}
            </span>
            <span className="wf-badge low">
              Đề xuất: {plan.recommended_agent_count} Agent
            </span>
            <span className="wf-badge medium">Sẽ dùng: {plan.chosen_agent_count} Agent</span>
            <span className="wf-badge medium">{plan.tasks.length} task</span>
          </div>
          {plan.count_reason && (
            <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
              Lý do chọn số Agent: {plan.count_reason}
            </p>
          )}
          {plan.warnings.map((warning) => (
            <p className="wf-plan-warning" key={warning}>
              <TriangleAlert size={14} /> {warning}
            </p>
          ))}
          {plan.clarifying_questions.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <span className="wf-design-label">Câu hỏi cần làm rõ</span>
              <ul className="wf-plan-list">
                {plan.clarifying_questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </div>
          )}
          {plan.missing_info.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <span className="wf-design-label">Thông tin còn thiếu / giả định</span>
              <ul className="wf-plan-list">
                {[...plan.missing_info, ...plan.assumptions].map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <span className="wf-design-label" style={{ marginTop: 14 }}>
            Cây task (theo đợt chạy — wave)
          </span>
          <div className="wf-plan-tasks">
            {plan.tasks.map((task) => {
              const meta = roleMeta(task.suggested_role);
              return (
                <article className="wf-plan-task" key={task.key}>
                  <p>
                    <b>
                      {task.key} · {task.title}
                    </b>{" "}
                    <span
                      className="wf-badge medium"
                      style={{ background: meta.soft, color: meta.color }}
                    >
                      {meta.label}
                    </span>{" "}
                    <span className="wf-badge low">Wave {task.wave}</span>{" "}
                    {task.parallelizable && (
                      <span className="wf-badge low">Chạy song song</span>
                    )}{" "}
                    <span className={`wf-badge ${task.priority === "high" ? "high" : "medium"}`}>
                      Ưu tiên: {task.priority}
                    </span>
                  </p>
                  {task.description && (
                    <p className="muted" style={{ fontSize: 12.5 }}>
                      {task.description}
                    </p>
                  )}
                  {task.depends_on.length > 0 && (
                    <p style={{ fontSize: 12.5 }}>
                      Phụ thuộc:{" "}
                      {task.depends_on
                        .map((k) => `${k} (${taskByKey.get(k)?.title || "?"})`)
                        .join(", ")}
                    </p>
                  )}
                  {task.expected_output && (
                    <p style={{ fontSize: 12.5 }}>Đầu ra: {task.expected_output}</p>
                  )}
                  {task.skills_required.length > 0 && (
                    <p style={{ fontSize: 12.5 }}>
                      Kỹ năng: {task.skills_required.join(", ")}
                    </p>
                  )}
                  {task.acceptance_criteria.length > 0 && (
                    <p style={{ fontSize: 12.5 }}>
                      Nghiệm thu: {task.acceptance_criteria.join("; ")}
                    </p>
                  )}
                  {(suggestionsByTask.get(task.key) || []).map((s) => (
                    <p style={{ fontSize: 12.5 }} key={s.resource_id}>
                      <Users size={13} /> Gợi ý nhân viên: <b>{s.name}</b>
                      {s.role ? ` (${s.role})` : ""} — khớp kỹ năng {s.score}%
                    </p>
                  ))}
                </article>
              );
            })}
          </div>

          <span className="wf-design-label" style={{ marginTop: 14 }}>
            Đội hình thực thi (ghép từ Agent thật của bạn)
          </span>
          <div className="wf-plan-tasks">
            {plan.lineup.map((item, index) => (
              <article className="wf-plan-task" key={`${item.role}-${index}`}>
                <p>
                  <b>{roleMeta(item.role).label}</b> —{" "}
                  {item.agent_name ? (
                    <>
                      {item.agent_name}{" "}
                      <span className="muted">
                        ({item.provider}/{item.model})
                      </span>
                    </>
                  ) : (
                    <span className="wf-error">Chưa có Agent cho vai trò này</span>
                  )}
                </p>
                <p style={{ fontSize: 12.5 }}>
                  Nhận task: {item.task_keys.join(", ") || "—"}
                </p>
              </article>
            ))}
            {!plan.lineup.length && (
              <p className="wf-empty">Chưa ghép được đội hình — hãy tạo thêm Agent.</p>
            )}
          </div>

          {plan.acceptance_criteria.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <span className="wf-design-label">Tiêu chí nghiệm thu chung</span>
              <ul className="wf-plan-list">
                {plan.acceptance_criteria.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="wf-form" style={{ marginTop: 14 }}>
            <label>
              Tên đội (tuỳ chọn)
              <input
                value={applyForm.team_name}
                maxLength={120}
                onChange={(e) => setApplyForm({ ...applyForm, team_name: e.target.value })}
                placeholder="Để trống thì tự đặt theo tiêu đề công việc"
              />
            </label>
            <label>
              Sản phẩm đầu ra
              <select
                value={applyForm.output_type}
                onChange={(e) => setApplyForm({ ...applyForm, output_type: e.target.value })}
              >
                {OUTPUT_TYPES.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
              <input
                type="checkbox"
                checked={applyForm.requires_approval}
                onChange={(e) =>
                  setApplyForm({ ...applyForm, requires_approval: e.target.checked })
                }
              />
              Cần duyệt trước khi hoàn thành
            </label>
            <div>
              <button
                className="wf-btn primary"
                type="button"
                disabled={applying || !plan.lineup.some((item) => item.agent_id)}
                onClick={applyPlan}
              >
                <Play size={16} />{" "}
                {applying ? "Đang tạo..." : "Áp dụng kế hoạch — tạo đội & workflow"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
