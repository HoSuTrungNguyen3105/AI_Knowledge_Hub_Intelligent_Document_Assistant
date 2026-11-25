"use client";

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "../confirm-dialog";
import ProjectDiscussion from "./project-discussion";
import { providerService } from "../../services/providers";
import { ModelSelect } from "../model-select";
import { getProjectError, projectErrorByCode, projectsService } from "../../services/projects";

const PROJECT_STATUS = {
  draft: ["Nháp", "medium"],
  analyzed: ["Đã phân tích", "medium"],
  approved: ["Đã duyệt đội", "low"],
  in_progress: ["Đang thực hiện", "low"],
  done: ["Hoàn thành", "low"],
  archived: ["Lưu trữ", "high"],
};

const ALLOCATION_STATUS = {
  proposed: ["Đang chờ duyệt", "medium"],
  approved: ["Đã duyệt", "low"],
  rejected: ["Đã từ chối", "high"],
};

const SUGGESTED_LABEL = { human: "Người", ai: "AI", either: "Người hoặc AI" };

function splitList(text) {
  return text.split(",").map((part) => part.trim()).filter(Boolean);
}

function fmtDateTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("vi-VN");
}

function fmtDate(value) {
  if (!value) return "Chưa đặt deadline";
  return new Date(`${value}T00:00:00`).toLocaleDateString("vi-VN");
}

function StatusBadge({ map, value }) {
  const [label, tone] = map[value] || [value, "medium"];
  return <span className={`wf-badge ${tone}`}>{label}</span>;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [analyses, setAnalyses] = useState([]);
  const [allocations, setAllocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", tech_stack: "", deadline: "" });
  const [briefFile, setBriefFile] = useState(null);
  const [fileReset, setFileReset] = useState(0);
  const [providers, setProviders] = useState([]);
  const [providerId, setProviderId] = useState("");
  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [busyKey, setBusyKey] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const selected = projects.find((project) => project.id === selectedId) || null;

  const loadProjects = useCallback(async () => {
    try {
      const items = await projectsService.list();
      setProjects(items);
      setSelectedId((current) =>
        current && items.some((item) => item.id === current) ? current : items[0]?.id || null,
      );
    } catch (err) {
      setError(getProjectError(err, "Không tải được danh sách dự án."));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (projectId) => {
    if (!projectId) {
      setAnalyses([]);
      setAllocations([]);
      return;
    }
    try {
      const [analysisItems, allocationItems] = await Promise.all([
        projectsService.analyses(projectId),
        projectsService.allocations(projectId),
      ]);
      setAnalyses(analysisItems);
      setAllocations(allocationItems);
    } catch (err) {
      setError(getProjectError(err, "Không tải được chi tiết dự án."));
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    let cancelled = false;
    providerService
      .list()
      .then((data) => {
        if (cancelled) return;
        const ready = (data.providers || []).filter(
          (provider) => provider.implemented && provider.configured && provider.enabled,
        );
        setProviders(ready);
        if (ready.length > 0) setProviderId((current) => current || ready[0].id);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!providerId) {
      setModels([]);
      setModelId("");
      return;
    }
    let cancelled = false;
    providerService
      .models(providerId)
      .then((data) => {
        if (cancelled) return;
        const chatModels = (data.models || []).filter(
          (model) => model.capabilities?.chat !== false,
        );
        setModels(chatModels);
        const provider = providers.find((item) => item.id === providerId);
        setModelId(
          chatModels.some((model) => model.id === provider?.default_model)
            ? provider.default_model
            : chatModels[0]?.id || "",
        );
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [providerId, providers]);

  async function createProject(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setCreating(true);
    try {
      if (briefFile) {
        // One-shot flow: upload the brief and the backend creates the
        // project, analyzes it and drafts the team recommendation.
        const result = await projectsService.importFile(briefFile, {
          name: form.name.trim(),
          techStack: form.tech_stack.trim(),
          provider: providerId,
          model: modelId,
        });
        setForm({ name: "", description: "", tech_stack: "", deadline: "" });
        setBriefFile(null);
        setFileReset((value) => value + 1);
        await loadProjects();
        setSelectedId(result.project.id);
        if (result.analysis_error) {
          setError(
            `Đã tạo dự án từ file nhưng chưa phân tích được: ${projectErrorByCode(result.analysis_error, result.analysis_error)} Bạn có thể bấm "Phân tích dự án" ở phần dưới để thử lại.`,
          );
        } else {
          setNotice(
            "Đã đọc file, phân tích xong và tạo sẵn đề xuất phân công ở phần dưới — chỉ còn bước duyệt đội.",
          );
        }
        return;
      }
      const created = await projectsService.create({
        name: form.name.trim(),
        description: form.description.trim(),
        tech_stack: splitList(form.tech_stack),
        deadline: form.deadline || null,
      });
      setForm({ name: "", description: "", tech_stack: "", deadline: "" });
      await loadProjects();
      setSelectedId(created.id);
      setNotice("Đã tạo dự án. Hãy phân tích bằng AI để chia task.");
    } catch (err) {
      setError(getProjectError(err, "Không tạo được dự án."));
    } finally {
      setCreating(false);
    }
  }

  async function runAnalyze() {
    if (!selected || !providerId || !modelId) return;
    setError("");
    setNotice("");
    setAnalyzing(true);
    try {
      await projectsService.analyze(selected.id, { provider: providerId, model: modelId });
      await loadProjects();
      await loadDetail(selected.id);
      setNotice("Phân tích xong. Kiểm tra danh sách task rồi tạo đề xuất phân công.");
    } catch (err) {
      setError(getProjectError(err, "Không phân tích được dự án."));
    } finally {
      setAnalyzing(false);
    }
  }

  async function runRecommend(analysisId) {
    if (!selected) return;
    setError("");
    setNotice("");
    setBusyKey(`recommend-${analysisId}`);
    try {
      await projectsService.recommend(selected.id, analysisId);
      await loadDetail(selected.id);
      setNotice("Đã tạo đề xuất phân công. Bạn có thể đổi người cho từng task rồi duyệt.");
    } catch (err) {
      setError(getProjectError(err, "Không tạo được đề xuất phân công."));
    } finally {
      setBusyKey("");
    }
  }

  async function runReassign(allocation, taskIndex, resourceId) {
    if (!selected) return;
    setError("");
    setBusyKey(`assign-${allocation.id}-${taskIndex}`);
    try {
      const updated = await projectsService.reassign(selected.id, allocation.id, [
        { task_index: taskIndex, resource_id: resourceId || null },
      ]);
      setAllocations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (err) {
      setError(getProjectError(err, "Không đổi được phân công."));
    } finally {
      setBusyKey("");
    }
  }

  async function runDecide(allocation, decision) {
    if (!selected) return;
    setError("");
    setNotice("");
    setBusyKey(`decide-${allocation.id}`);
    try {
      const updated = await projectsService.decide(selected.id, allocation.id, decision);
      setAllocations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      await loadProjects();
      setNotice(
        decision === "approved"
          ? "Đã duyệt đội cho dự án."
          : "Đã từ chối bản đề xuất này. Bạn vẫn tạo được đề xuất mới.",
      );
    } catch (err) {
      setError(getProjectError(err, "Không ghi được quyết định."));
    } finally {
      setBusyKey("");
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await projectsService.remove(deleting.id);
      setDeleting(null);
      await loadProjects();
    } catch (err) {
      setError(getProjectError(err, "Không xoá được dự án."));
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="wf-page">
      <div className="wf-header">
        <div>
          <h1>Dự án</h1>
          <p>
            Phân tích yêu cầu bằng AI, đề xuất phân công theo điểm năng lực và duyệt đội
            trước khi thực hiện.
          </p>
        </div>
      </div>

      {error ? <p className="wf-error">{error}</p> : null}
      {notice ? (
        <div className="wf-card">
          <p>{notice}</p>
        </div>
      ) : null}

      <form className="wf-form" onSubmit={createProject}>
        <h2>Tạo dự án mới</h2>
        <label>
          Tên dự án
          <input
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="Website thương mại điện tử"
            required={!briefFile}
          />
        </label>
        <label>
          Mô tả và yêu cầu
          <textarea
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            placeholder="Mục tiêu, tính năng chính, ràng buộc kỹ thuật, đối tượng sử dụng..."
            rows={4}
            required={!briefFile}
          />
        </label>
        <label>
          Hoặc tải lên file mô tả dự án (.md, .txt, .pdf, .docx — tối đa 5 MB)
          <input
            key={fileReset}
            type="file"
            accept=".md,.markdown,.txt,.pdf,.docx"
            onChange={(event) => setBriefFile(event.target.files?.[0] || null)}
          />
        </label>
        {briefFile ? (
          <>
            <p className="wf-empty">
              AI sẽ đọc file này, chia task và tạo sẵn đề xuất phân công — bạn chỉ còn bước
              duyệt đội. Tên dự án để trống thì lấy theo dòng đầu tiên của file; ô mô tả
              phía trên sẽ không được dùng.
            </p>
            <label>
              Provider phân tích
              <select
                value={providerId}
                onChange={(event) => setProviderId(event.target.value)}
              >
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Model phân tích
              <ModelSelect models={models} value={modelId} onChange={setModelId} />
            </label>
          </>
        ) : null}
        <label>
          Công nghệ dự kiến (cách nhau bằng dấu phẩy)
          <input
            value={form.tech_stack}
            onChange={(event) => setForm({ ...form, tech_stack: event.target.value })}
            placeholder="Next.js, PostgreSQL"
          />
        </label>
        <label>
          Deadline
          <input
            type="date"
            value={form.deadline}
            onChange={(event) => setForm({ ...form, deadline: event.target.value })}
          />
        </label>
        <div className="wf-actions">
          <button
            type="submit"
            className="wf-btn"
            disabled={
              creating ||
              (briefFile
                ? !providerId || !modelId
                : !form.name.trim() || !form.description.trim())
            }
          >
            {creating
              ? briefFile
                ? "Đang đọc file và phân tích..."
                : "Đang tạo..."
              : briefFile
                ? "Tải lên & phân tích ngay"
                : "Tạo dự án"}
          </button>
        </div>
      </form>

      <h2>Danh sách dự án</h2>
      {loading ? (
        <p>Đang tải...</p>
      ) : projects.length === 0 ? (
        <p className="wf-empty">Chưa có dự án nào. Tạo dự án đầu tiên ở biểu mẫu phía trên.</p>
      ) : (
        <div className="wf-list">
          {projects.map((project) => (
            <article key={project.id} className="wf-card">
              <div className="wf-chip-row">
                <strong>{project.name}</strong>
                <StatusBadge map={PROJECT_STATUS} value={project.status} />
                <span className="wf-badge">{fmtDate(project.deadline)}</span>
              </div>
              <p>{project.description}</p>
              {project.tech_stack.length > 0 ? (
                <div className="wf-chip-row">
                  {project.tech_stack.map((tech) => (
                    <span key={tech} className="wf-chip">{tech}</span>
                  ))}
                </div>
              ) : null}
              <div className="wf-actions">
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => setSelectedId(project.id)}
                >
                  {project.id === selectedId ? "Đang xem" : "Xem chi tiết"}
                </button>
                <button type="button" className="wf-btn" onClick={() => setDeleting(project)}>
                  Xoá
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {selected ? (
        <section className="wf-design">
          <span className="wf-design-label">Chi tiết dự án</span>
          <h2>{selected.name}</h2>

          <div className="wf-form">
            <h3>Phân tích bằng AI</h3>
            {providers.length === 0 ? (
              <p>
                Chưa có provider nào sẵn sàng (đã cấu hình key và đang bật). Hãy mở trang
                Providers trước.
              </p>
            ) : (
              <>
                <label>
                  Provider
                  <select
                    value={providerId}
                    onChange={(event) => setProviderId(event.target.value)}
                  >
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Model
                  <ModelSelect models={models} value={modelId} onChange={setModelId} />
                </label>
                <div className="wf-actions">
                  <button
                    type="button"
                    className="wf-btn"
                    onClick={runAnalyze}
                    disabled={analyzing || !modelId}
                  >
                    {analyzing ? "Đang phân tích..." : "Phân tích dự án"}
                  </button>
                </div>
                <p>Một lượt phân tích có thể mất 30-60 giây tuỳ model.</p>
              </>
            )}
          </div>

          <h3>Các bản phân tích</h3>
          {analyses.length === 0 ? (
            <p className="wf-empty">Chưa có bản phân tích nào cho dự án này.</p>
          ) : (
            analyses.map((analysis) => (
              <article key={analysis.id} className="wf-card">
                <div className="wf-chip-row">
                  <strong>{fmtDateTime(analysis.created_at)}</strong>
                  <span className="wf-badge">{analysis.provider} / {analysis.model}</span>
                  {analysis.total_estimated_hours != null ? (
                    <span className="wf-badge low">
                      Tổng ~{analysis.total_estimated_hours} giờ
                    </span>
                  ) : null}
                </div>
                <p>{analysis.summary}</p>
                {analysis.tasks.map((task, index) => (
                  <div key={index} className="wf-task">
                    <div className="wf-chip-row">
                      <strong>{task.title}</strong>
                      <span className="wf-badge">
                        {SUGGESTED_LABEL[task.suggested_type] || task.suggested_type}
                      </span>
                      {task.estimated_hours != null ? (
                        <span className="wf-badge">~{task.estimated_hours} giờ</span>
                      ) : null}
                    </div>
                    {task.description ? <p>{task.description}</p> : null}
                    {task.acceptance_criteria ? (
                      <p>Tiêu chí nghiệm thu: {task.acceptance_criteria}</p>
                    ) : null}
                    {task.skills_required.length > 0 ? (
                      <div className="wf-chip-row">
                        {task.skills_required.map((skill) => (
                          <span key={skill} className="wf-chip">{skill}</span>
                        ))}
                        {task.scopes.map((scope) => (
                          <span key={scope} className="wf-badge high">{scope}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
                {analysis.risks.length > 0 ? (
                  <p>Rủi ro: {analysis.risks.join("; ")}</p>
                ) : null}
                <div className="wf-actions">
                  <button
                    type="button"
                    className="wf-btn"
                    onClick={() => runRecommend(analysis.id)}
                    disabled={busyKey === `recommend-${analysis.id}`}
                  >
                    {busyKey === `recommend-${analysis.id}`
                      ? "Đang chấm điểm..."
                      : "Tạo đề xuất phân công"}
                  </button>
                </div>
              </article>
            ))
          )}

          <h3>Đề xuất phân công</h3>
          {allocations.length === 0 ? (
            <p className="wf-empty">
              Chưa có đề xuất nào. Tạo đề xuất từ một bản phân tích ở trên — hệ thống chấm
              điểm mọi nguồn lực trong Workforce cho từng task.
            </p>
          ) : (
            allocations.map((allocation) => (
              <article key={allocation.id} className="wf-card">
                <div className="wf-chip-row">
                  <strong>Đề xuất {fmtDateTime(allocation.created_at)}</strong>
                  <StatusBadge map={ALLOCATION_STATUS} value={allocation.status} />
                </div>
                {allocation.items.map((item) => (
                  <div key={item.task_index} className="wf-task">
                    <div className="wf-chip-row">
                      <strong>{item.task_title}</strong>
                      {item.resource_name ? (
                        <span className="wf-badge low">
                          {item.resource_name} — {item.score} điểm
                        </span>
                      ) : (
                        <span className="wf-badge high">Chưa phân công</span>
                      )}
                    </div>
                    {item.reason ? <p>{item.reason}</p> : null}
                    {allocation.status === "proposed" ? (
                      <label>
                        Đổi phân công
                        <select
                          value={item.resource_id || ""}
                          disabled={busyKey === `assign-${allocation.id}-${item.task_index}`}
                          onChange={(event) =>
                            runReassign(allocation, item.task_index, event.target.value)
                          }
                        >
                          <option value="">— Chưa phân công —</option>
                          {item.candidates.map((candidate) => (
                            <option key={candidate.resource_id} value={candidate.resource_id}>
                              {candidate.name} ({candidate.type === "ai" ? "AI" : "Người"}) —{" "}
                              {candidate.score} điểm
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                    {item.excluded.length > 0 ? (
                      <p>
                        Bị loại:{" "}
                        {item.excluded.map((entry) => `${entry.name} (${entry.reason})`).join("; ")}
                      </p>
                    ) : null}
                  </div>
                ))}
                {allocation.status === "proposed" ? (
                  <div className="wf-actions">
                    <button
                      type="button"
                      className="wf-btn"
                      onClick={() => runDecide(allocation, "approved")}
                      disabled={busyKey === `decide-${allocation.id}`}
                    >
                      Duyệt phân công
                    </button>
                    <button
                      type="button"
                      className="wf-btn"
                      onClick={() => runDecide(allocation, "rejected")}
                      disabled={busyKey === `decide-${allocation.id}`}
                    >
                      Từ chối
                    </button>
                  </div>
                ) : null}
              </article>
            ))
          )}

          <ProjectDiscussion
            projectId={selected.id}
            onTasksChanged={() => loadDetail(selected.id)}
          />
        </section>
      ) : null}

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xoá dự án?"
        confirmLabel="Xoá dự án"
        busy={deleteBusy}
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      >
        {deleting
          ? `Dự án "${deleting.name}" cùng các bản phân tích và đề xuất phân công của nó sẽ bị xoá.`
          : ""}
      </ConfirmDialog>
    </div>
  );
}
