"use client";

import { useCallback, useEffect, useState } from "react";

import { agentsService } from "../../services/agents";
import {
  getProjectError,
  projectErrorByCode,
  projectsService,
} from "../../services/projects";

const DECISION_STATUS = {
  proposed: ["Đề xuất", "normal"],
  approved: ["Đã duyệt", "low"],
  rejected: ["Từ chối", "high"],
  superseded: ["Đã thay thế", "zip"],
};

function fmtTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("vi-VN");
}

function firstLine(text) {
  return (text || "").split("\n").find((line) => line.trim())?.trim() || "";
}

// Discussion & decisions inside one project (Project_Discussion.md).
// Mentions are picked from the owner's real Agent list and sent as
// Agent IDs; the text only carries the display name.
export default function ProjectDiscussion({ projectId, onTasksChanged }) {
  const [agents, setAgents] = useState([]);
  const [messages, setMessages] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [picked, setPicked] = useState({});
  const [pickAll, setPickAll] = useState(false);
  const [picker, setPicker] = useState(null);
  const [sending, setSending] = useState(false);
  const [retryingId, setRetryingId] = useState(null);
  const [taskForm, setTaskForm] = useState(null);
  const [decisionForm, setDecisionForm] = useState(null);
  const [supersedeChoice, setSupersedeChoice] = useState({});
  const [busyKey, setBusyKey] = useState("");

  const loadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [msgs, decs, ags] = await Promise.all([
        projectsService.discussion(projectId),
        projectsService.decisions(projectId),
        agentsService.list(),
      ]);
      setMessages(msgs);
      setDecisions(decs);
      setAgents(ags);
    } catch (err) {
      setError(getProjectError(err, "Không tải được phần thảo luận."));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const agentName = useCallback(
    (id) => agents.find((agent) => agent.id === id)?.name || "Agent",
    [agents],
  );

  function handleDraftChange(event) {
    const value = event.target.value;
    setDraft(value);
    const caret = event.target.selectionStart ?? value.length;
    const match = value.slice(0, caret).match(/@([^\s@]*)$/);
    setPicker(
      match ? { start: caret - match[0].length, filter: match[1] } : null,
    );
  }

  function chooseMention(agent) {
    if (!picker) return;
    const label = agent ? agent.name : "All";
    const next =
      draft.slice(0, picker.start) +
      `@${label} ` +
      draft.slice(picker.start + 1 + picker.filter.length);
    if (agent) setPicked((prev) => ({ ...prev, [agent.id]: agent.name }));
    else setPickAll(true);
    setDraft(next);
    setPicker(null);
  }

  async function send() {
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setError("");
    setNotice("");
    try {
      const mentionIds = Object.keys(picked).filter((id) =>
        draft.includes(`@${picked[id]}`),
      );
      const created = await projectsService.postDiscussion(projectId, {
        content,
        mention_agent_ids: mentionIds,
        mention_all: pickAll && draft.includes("@All"),
      });
      setMessages((prev) => [...prev, ...created]);
      setDraft("");
      setPicked({});
      setPickAll(false);
      setPicker(null);
    } catch (err) {
      setError(getProjectError(err, "Không gửi được tin nhắn."));
    } finally {
      setSending(false);
    }
  }

  async function retry(message) {
    if (!message.in_reply_to || retryingId) return;
    setRetryingId(message.id);
    setError("");
    try {
      await projectsService.retryDiscussion(projectId, message.in_reply_to);
      const msgs = await projectsService.discussion(projectId);
      setMessages(msgs);
    } catch (err) {
      setError(getProjectError(err, "Không thử lại được."));
    } finally {
      setRetryingId(null);
    }
  }

  async function submitTaskForm(event) {
    event.preventDefault();
    if (!taskForm) return;
    setBusyKey("task");
    setError("");
    try {
      const result = await projectsService.convertTask(
        projectId,
        taskForm.messageId,
        {
          title: taskForm.title,
          acceptance_criteria: taskForm.criteria,
          suggested_type: taskForm.type,
        },
      );
      setNotice(`Đã tạo task "${result.task_title}" trong bản phân tích của dự án.`);
      setTaskForm(null);
      const msgs = await projectsService.discussion(projectId);
      setMessages(msgs);
      if (onTasksChanged) onTasksChanged();
    } catch (err) {
      setError(getProjectError(err, "Không tạo được task từ tin nhắn này."));
    } finally {
      setBusyKey("");
    }
  }

  async function submitDecisionForm(event) {
    event.preventDefault();
    if (!decisionForm) return;
    setBusyKey("decision");
    setError("");
    try {
      const created = await projectsService.createDecision(projectId, {
        title: decisionForm.title,
        reason: decisionForm.reason,
        source_message_id: decisionForm.sourceId || undefined,
      });
      setDecisions((prev) => [created, ...prev]);
      setDecisionForm(null);
      setNotice("Đã lưu quyết định ở trạng thái Đề xuất — duyệt để nó thành chính thức.");
    } catch (err) {
      setError(getProjectError(err, "Không lưu được quyết định."));
    } finally {
      setBusyKey("");
    }
  }

  async function actOnDecision(decision, status) {
    setBusyKey(`decision-${decision.id}`);
    setError("");
    try {
      const payload = { status };
      if (status === "approved" && supersedeChoice[decision.id]) {
        payload.supersedes_id = supersedeChoice[decision.id];
      }
      await projectsService.patchDecision(projectId, decision.id, payload);
      const decs = await projectsService.decisions(projectId);
      setDecisions(decs);
    } catch (err) {
      setError(getProjectError(err, "Không cập nhật được quyết định."));
    } finally {
      setBusyKey("");
    }
  }

  const pickerAgents = picker
    ? agents.filter((agent) =>
        agent.name.toLowerCase().includes(picker.filter.toLowerCase()),
      )
    : [];
  const showAllOption =
    picker && "all".includes(picker.filter.toLowerCase());
  const approvedDecisions = decisions.filter((d) => d.status === "approved");

  return (
    <div className="wf-disc">
      <h3>Thảo luận với AI Agents</h3>
      {error ? <p className="wf-error">{error}</p> : null}
      {notice ? <p>{notice}</p> : null}
      {loading ? (
        <p>Đang tải thảo luận...</p>
      ) : (
        <>
          {messages.length === 0 ? (
            <p className="wf-empty">
              Chưa có trao đổi nào trong dự án này. Hãy hỏi các Agent về kết quả
              phân tích, gõ @ để chọn Agent cụ thể (ví dụ @Architect), hoặc gửi
              tin nhắn thường để hệ thống tự chọn Agent phù hợp.
            </p>
          ) : (
            <div className="wf-disc-messages">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={`wf-disc-msg ${message.sender_type}`}
                >
                  <div className="wf-chip-row">
                    <strong>
                      {message.sender_type === "user"
                        ? "Bạn"
                        : message.agent_name || "AI Agent"}
                    </strong>
                    <span className="wf-badge">{fmtTime(message.created_at)}</span>
                    {message.mention_all ? (
                      <span className="wf-chip">@All</span>
                    ) : null}
                    {(message.mentions || []).map((id) => (
                      <span key={id} className="wf-chip">@{agentName(id)}</span>
                    ))}
                    {message.converted_analysis_id ? (
                      <span className="wf-badge low">Đã tạo task</span>
                    ) : null}
                  </div>
                  {message.status === "error" ? (
                    <div className="wf-disc-error">
                      <p>
                        Agent chưa trả lời được:{" "}
                        {projectErrorByCode(
                          message.error_code,
                          "Đã xảy ra lỗi phía provider.",
                        )}
                      </p>
                      <button
                        type="button"
                        className="wf-btn"
                        disabled={retryingId === message.id}
                        onClick={() => retry(message)}
                      >
                        {retryingId === message.id ? "Đang thử lại..." : "Thử lại"}
                      </button>
                    </div>
                  ) : (
                    <div className="wf-disc-body">{message.content}</div>
                  )}
                  {message.status !== "error" ? (
                    <div className="wf-actions">
                      <button
                        type="button"
                        className="wf-btn"
                        onClick={() =>
                          setTaskForm({
                            messageId: message.id,
                            title: firstLine(message.content).slice(0, 200),
                            criteria: "",
                            type: "either",
                          })
                        }
                      >
                        Tạo task
                      </button>
                      <button
                        type="button"
                        className="wf-btn"
                        onClick={() =>
                          setDecisionForm({
                            title: firstLine(message.content).slice(0, 200),
                            reason: "",
                            sourceId: message.id,
                          })
                        }
                      >
                        Lưu quyết định
                      </button>
                    </div>
                  ) : null}
                  {taskForm && taskForm.messageId === message.id ? (
                    <form className="wf-form" onSubmit={submitTaskForm}>
                      <label>
                        Tiêu đề task
                        <input
                          value={taskForm.title}
                          onChange={(event) =>
                            setTaskForm({ ...taskForm, title: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        Tiêu chí nghiệm thu
                        <input
                          value={taskForm.criteria}
                          onChange={(event) =>
                            setTaskForm({ ...taskForm, criteria: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        Gợi ý người thực hiện
                        <select
                          value={taskForm.type}
                          onChange={(event) =>
                            setTaskForm({ ...taskForm, type: event.target.value })
                          }
                        >
                          <option value="either">Người hoặc AI</option>
                          <option value="human">Người</option>
                          <option value="ai">AI</option>
                        </select>
                      </label>
                      <div className="wf-actions">
                        <button
                          type="submit"
                          className="wf-btn"
                          disabled={busyKey === "task" || !taskForm.title.trim()}
                        >
                          {busyKey === "task" ? "Đang tạo..." : "Tạo task"}
                        </button>
                        <button
                          type="button"
                          className="wf-btn"
                          onClick={() => setTaskForm(null)}
                        >
                          Huỷ
                        </button>
                      </div>
                    </form>
                  ) : null}
                </article>
              ))}
            </div>
          )}

          <div className="wf-disc-composer">
            {picker && (pickerAgents.length > 0 || showAllOption) ? (
              <div className="wf-disc-picker">
                {showAllOption ? (
                  <button type="button" onClick={() => chooseMention(null)}>
                    @All — để hệ thống chọn Agent phù hợp
                  </button>
                ) : null}
                {pickerAgents.map((agent) => (
                  <button
                    key={agent.id}
                    type="button"
                    onClick={() => chooseMention(agent)}
                  >
                    @{agent.name}
                    <span>
                      {agent.provider} / {agent.model}
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
            <textarea
              rows={3}
              value={draft}
              onChange={handleDraftChange}
              placeholder="Trao đổi với các Agent về dự án này... Gõ @ để mention một Agent."
            />
            <div className="wf-actions">
              <button
                type="button"
                className="wf-btn primary"
                disabled={sending || !draft.trim()}
                onClick={send}
              >
                {sending ? "Agent đang trả lời..." : "Gửi"}
              </button>
              {agents.length === 0 ? (
                <span>
                  Bạn chưa có Agent nào — hãy tạo Agent ở trang Agents trước,
                  tin nhắn vẫn được lưu nhưng chưa có ai trả lời.
                </span>
              ) : null}
            </div>
          </div>

          {decisionForm ? (
            <form className="wf-form" onSubmit={submitDecisionForm}>
              <h4>Lưu quyết định</h4>
              <label>
                Quyết định
                <input
                  value={decisionForm.title}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, title: event.target.value })
                  }
                />
              </label>
              <label>
                Lý do
                <input
                  value={decisionForm.reason}
                  onChange={(event) =>
                    setDecisionForm({ ...decisionForm, reason: event.target.value })
                  }
                />
              </label>
              <div className="wf-actions">
                <button
                  type="submit"
                  className="wf-btn"
                  disabled={busyKey === "decision" || !decisionForm.title.trim()}
                >
                  {busyKey === "decision" ? "Đang lưu..." : "Lưu quyết định"}
                </button>
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => setDecisionForm(null)}
                >
                  Huỷ
                </button>
              </div>
            </form>
          ) : null}

          <h4>Quyết định của dự án</h4>
          {decisions.length === 0 ? (
            <p className="wf-empty">
              Chưa có quyết định nào. Dùng nút "Lưu quyết định" ở một tin nhắn,
              hoặc tạo mới:
            </p>
          ) : (
            decisions.map((decision) => {
              const [label, tone] = DECISION_STATUS[decision.status] || [
                decision.status,
                "normal",
              ];
              return (
                <article key={decision.id} className="wf-card">
                  <div className="wf-chip-row">
                    <strong>{decision.title}</strong>
                    <span className={`wf-badge ${tone}`}>{label}</span>
                  </div>
                  {decision.reason ? <p>{decision.reason}</p> : null}
                  <p>
                    Lịch sử:{" "}
                    {(decision.status_history || [])
                      .map(
                        (entry) =>
                          `${(DECISION_STATUS[entry.status] || [entry.status])[0]} (${fmtTime(entry.at)})`,
                      )
                      .join(" → ")}
                  </p>
                  {decision.status === "proposed" ? (
                    <div className="wf-actions">
                      <button
                        type="button"
                        className="wf-btn"
                        disabled={busyKey === `decision-${decision.id}`}
                        onClick={() => actOnDecision(decision, "approved")}
                      >
                        Duyệt
                      </button>
                      <button
                        type="button"
                        className="wf-btn"
                        disabled={busyKey === `decision-${decision.id}`}
                        onClick={() => actOnDecision(decision, "rejected")}
                      >
                        Từ chối
                      </button>
                      {approvedDecisions.length > 0 ? (
                        <select
                          value={supersedeChoice[decision.id] || ""}
                          onChange={(event) =>
                            setSupersedeChoice({
                              ...supersedeChoice,
                              [decision.id]: event.target.value,
                            })
                          }
                        >
                          <option value="">Không thay thế quyết định cũ</option>
                          {approvedDecisions.map((old) => (
                            <option key={old.id} value={old.id}>
                              Thay thế: {old.title}
                            </option>
                          ))}
                        </select>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
          {!decisionForm ? (
            <div className="wf-actions">
              <button
                type="button"
                className="wf-btn"
                onClick={() =>
                  setDecisionForm({ title: "", reason: "", sourceId: null })
                }
              >
                Thêm quyết định
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
