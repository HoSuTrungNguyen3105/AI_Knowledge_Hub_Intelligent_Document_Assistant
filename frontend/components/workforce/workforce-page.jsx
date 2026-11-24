"use client";

import { useEffect, useState } from "react";
import { Bot, Briefcase, Pencil, Plus, Trash2, UserRound, X } from "lucide-react";
import { resourcesService, getResourceError } from "../../services/resources";
import { agentsService } from "../../services/agents";
import { ConfirmDialog } from "../confirm-dialog";

// Workforce Management (mindflow-workforce-feature.md sections 3 + 9):
// one roster of project resources with two tabs — people and AI. Both
// kinds share skills / availability / cost; the profile block differs.
// AI resources may link to an existing MindFlow Agent or stand alone as
// an external profile (e.g. a coding-agent runtime). No API key is ever
// entered or stored here — keys stay in the Providers vault.

const HUMAN_STATUS = [
  ["available", "Sẵn sàng"],
  ["busy", "Đang bận"],
  ["unavailable", "Không khả dụng"],
];
const AI_STATUS = [
  ["connected", "Đã kết nối"],
  ["disconnected", "Chưa kết nối"],
];
const statusLabel = (type, value) =>
  (type === "ai" ? AI_STATUS : HUMAN_STATUS).find(([key]) => key === value)?.[1] || value;

const emptyForm = (type) => ({
  name: "",
  role: "",
  availability_status: type === "ai" ? "disconnected" : "available",
  cost_per_hour: "",
  notes: "",
  skills: [{ name: "", level: 3 }],
  experience_years: "",
  hours_per_week: "",
  current_project_count: "0",
  provider: "",
  model: "",
  runtime: "model-api",
  agent_id: "",
  allowed_tools: "",
  denied_scopes: "",
  token_limit_per_task: "",
});

const numOrNull = (value) => {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};
const splitList = (value) =>
  [...new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean))];

function formFromResource(resource) {
  const form = emptyForm(resource.type);
  form.name = resource.name;
  form.role = resource.role;
  form.availability_status = resource.availability_status;
  form.cost_per_hour = resource.cost_per_hour ?? "";
  form.notes = resource.notes || "";
  form.skills = resource.skills?.length ? resource.skills.map((s) => ({ ...s })) : [{ name: "", level: 3 }];
  if (resource.type === "human" && resource.human) {
    form.experience_years = resource.human.experience_years ?? "";
    form.hours_per_week = resource.human.hours_per_week ?? "";
    form.current_project_count = resource.human.current_project_count ?? 0;
  }
  if (resource.type === "ai" && resource.ai) {
    form.provider = resource.ai.provider || "";
    form.model = resource.ai.model || "";
    form.runtime = resource.ai.runtime || "model-api";
    form.agent_id = resource.ai.agent_id || "";
    form.allowed_tools = (resource.ai.allowed_tools || []).join(", ");
    form.denied_scopes = (resource.ai.denied_scopes || []).join(", ");
    form.token_limit_per_task = resource.ai.token_limit_per_task ?? "";
  }
  return form;
}

function payloadFromForm(type, form) {
  const payload = {
    name: form.name.trim(),
    role: form.role.trim(),
    skills: form.skills
      .filter((skill) => skill.name.trim())
      .map((skill) => ({ name: skill.name.trim(), level: Number(skill.level) || 1 })),
    availability_status: form.availability_status,
    cost_per_hour: numOrNull(form.cost_per_hour),
    notes: form.notes.trim() || null,
  };
  if (type === "human") {
    payload.human = {
      experience_years: numOrNull(form.experience_years),
      hours_per_week: numOrNull(form.hours_per_week),
      current_project_count: numOrNull(form.current_project_count) ?? 0,
    };
  } else {
    payload.ai = {
      provider: form.provider.trim() || null,
      model: form.model.trim() || null,
      runtime: form.runtime,
      agent_id: form.agent_id || null,
      allowed_tools: splitList(form.allowed_tools),
      denied_scopes: splitList(form.denied_scopes),
      token_limit_per_task: numOrNull(form.token_limit_per_task),
    };
  }
  return payload;
}

export function WorkforcePage() {
  const [tab, setTab] = useState("human");
  const [resources, setResources] = useState([]);
  const [agents, setAgents] = useState([]);
  const [form, setForm] = useState(() => emptyForm("human"));
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [seedBusy, setSeedBusy] = useState(false);

  const load = async (signal) => {
    try {
      const [items, agentItems] = await Promise.all([
        resourcesService.list(undefined, signal),
        agentsService.list(signal).catch(() => []),
      ]);
      setResources(items);
      setAgents(agentItems || []);
      setError("");
    } catch (err) {
      if (err?.code !== "ERR_CANCELED") setError(getResourceError(err, "Không tải được danh sách nguồn lực."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchTab = (next) => {
    setTab(next);
    setEditingId(null);
    setForm(emptyForm(next));
    setError("");
    setNotice("");
  };

  const set = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  const setSkill = (index, key) => (event) =>
    setForm((prev) => ({
      ...prev,
      skills: prev.skills.map((skill, i) => (i === index ? { ...skill, [key]: event.target.value } : skill)),
    }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = payloadFromForm(tab, form);
      if (editingId) {
        const updated = await resourcesService.patch(editingId, payload);
        setResources((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
        setNotice(`Đã cập nhật ${updated.name}.`);
      } else {
        const created = await resourcesService.create({ type: tab, ...payload });
        setResources((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
        setNotice(`Đã thêm ${created.name} vào đội ngũ.`);
      }
      setEditingId(null);
      setForm(emptyForm(tab));
    } catch (err) {
      setError(getResourceError(err, "Không lưu được nguồn lực."));
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (resource) => {
    setEditingId(resource.id);
    setForm(formFromResource(resource));
    setError("");
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(emptyForm(tab));
  };

  const removeResource = async () => {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      await resourcesService.remove(confirmDelete.id);
      setResources((prev) => prev.filter((item) => item.id !== confirmDelete.id));
      if (editingId === confirmDelete.id) cancelEdit();
      setNotice(`Đã xoá ${confirmDelete.name}.`);
    } catch (err) {
      setError(getResourceError(err, "Không xoá được nguồn lực."));
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  };

  const runSeed = async () => {
    setError("");
    setNotice("");
    setSeedBusy(true);
    try {
      const result = await resourcesService.seedEmployees();
      setNotice(result.created > 0
        ? `Đã nạp ${result.created} nhân viên mẫu vào Workforce (bỏ qua ${result.skipped} người đã có).`
        : "Dữ liệu mẫu đã có đủ — không nạp thêm.");
      await load();
    } catch (err) {
      setError(getResourceError(err, "Không nạp được dữ liệu mẫu."));
    } finally {
      setSeedBusy(false);
    }
  };

  const runClearSeed = async () => {
    setError("");
    setNotice("");
    setSeedBusy(true);
    try {
      const result = await resourcesService.clearSeededEmployees();
      setNotice(`Đã xoá ${result.removed} nhân viên mẫu. Nhân viên thật không bị ảnh hưởng.`);
      await load();
    } catch (err) {
      setError(getResourceError(err, "Không xoá được dữ liệu mẫu."));
    } finally {
      setSeedBusy(false);
    }
  };

  const visible = resources.filter((item) => item.type === tab);
  const statusOptions = tab === "ai" ? AI_STATUS : HUMAN_STATUS;

  return <div className="wf-page">
    <div className="wf-header">
      <div>
        <h1><Briefcase size={26} /> Workforce</h1>
        <p>Nguồn lực thực hiện dự án: nhân viên và AI dùng chung một danh sách. AI phân tích dự án và đề xuất phân công sẽ dựa trên hồ sơ năng lực ở đây.</p>
      </div>
    </div>

    <section className="wf-card" aria-label="Dữ liệu mẫu">
      <h2>Dữ liệu mẫu để test</h2>
      <p>Nạp sẵn 50 nhân viên mẫu (đủ vai trò: dev, QA, DevOps, thiết kế, PM...) với kỹ năng, kinh nghiệm, chi phí và trạng thái sẵn sàng khác nhau để thử phân tích dự án và đề xuất phân công. Nạp lại không tạo trùng; xoá dữ liệu mẫu chỉ xoá đúng 50 người này.</p>
      <div className="wf-actions">
        <button type="button" className="wf-btn" onClick={runSeed} disabled={seedBusy}>
          {seedBusy ? "Đang xử lý..." : "Nạp 50 nhân viên mẫu"}
        </button>
        <button type="button" className="wf-btn" onClick={runClearSeed} disabled={seedBusy}>
          Xoá dữ liệu mẫu
        </button>
      </div>
    </section>

    <div className="wf-hub-tabs" role="tablist" aria-label="Loại nguồn lực">
      <button type="button" role="tab" aria-selected={tab === "human"} className={`wf-hub-tab${tab === "human" ? " active" : ""}`} onClick={() => switchTab("human")}>
        <UserRound size={16} /> Nhân viên ({resources.filter((r) => r.type === "human").length})
      </button>
      <button type="button" role="tab" aria-selected={tab === "ai"} className={`wf-hub-tab${tab === "ai" ? " active" : ""}`} onClick={() => switchTab("ai")}>
        <Bot size={16} /> AI Agents ({resources.filter((r) => r.type === "ai").length})
      </button>
    </div>

    {error && <p className="wf-error" role="alert">{error}</p>}
    {notice && <p aria-live="polite">{notice}</p>}

    <section className="wf-card" aria-label={editingId ? "Sửa nguồn lực" : "Thêm nguồn lực"}>
      <h2>{editingId ? <Pencil size={17} /> : <Plus size={17} />} {editingId ? "Sửa nguồn lực" : tab === "ai" ? "Thêm AI" : "Thêm nhân viên"}</h2>
      <form className="wf-form" onSubmit={submit}>
        <label>Tên
          <input value={form.name} onChange={set("name")} required maxLength={120} placeholder={tab === "ai" ? "VD: Claude Code" : "VD: Nguyễn Văn A"} />
        </label>
        <label>Vai trò chuyên môn
          <input value={form.role} onChange={set("role")} required maxLength={120} placeholder={tab === "ai" ? "VD: Coding Agent" : "VD: Frontend Developer"} />
        </label>
        <label>Trạng thái sẵn sàng
          <select value={form.availability_status} onChange={set("availability_status")}>
            {statusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Chi phí mỗi giờ (tuỳ chọn)
          <input value={form.cost_per_hour} onChange={set("cost_per_hour")} type="number" min="0" step="any" placeholder="VD: 25" />
        </label>

        <fieldset className="wf-design">
          <legend>Kỹ năng</legend>
          {form.skills.map((skill, index) => (
            <div className="wf-member-row" key={index}>
              <input
                value={skill.name}
                onChange={setSkill(index, "name")}
                placeholder="Tên kỹ năng, VD: React"
                maxLength={80}
                aria-label={`Kỹ năng ${index + 1}`}
                style={{ flex: "1 1 180px", border: "1px solid var(--line)", borderRadius: 8, padding: "7px 10px" }}
              />
              <label className="wf-design-label">Mức
                <select value={skill.level} onChange={setSkill(index, "level")} aria-label={`Mức độ kỹ năng ${index + 1}`}>
                  {[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level}/5</option>)}
                </select>
              </label>
              {form.skills.length > 1 && (
                <button type="button" className="wf-btn" onClick={() => setForm((prev) => ({ ...prev, skills: prev.skills.filter((_, i) => i !== index) }))} aria-label="Xoá kỹ năng">
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
          <div>
            <button type="button" className="wf-btn" onClick={() => setForm((prev) => ({ ...prev, skills: [...prev.skills, { name: "", level: 3 }] }))}>
              <Plus size={14} /> Thêm kỹ năng
            </button>
          </div>
        </fieldset>

        {tab === "human" ? (
          <fieldset className="wf-design">
            <legend>Hồ sơ nhân viên</legend>
            <label>Số năm kinh nghiệm
              <input value={form.experience_years} onChange={set("experience_years")} type="number" min="0" max="70" step="any" placeholder="VD: 4" />
            </label>
            <label>Số giờ làm việc mỗi tuần
              <input value={form.hours_per_week} onChange={set("hours_per_week")} type="number" min="0" max="80" placeholder="VD: 40" />
            </label>
            <label>Số dự án đang tham gia
              <input value={form.current_project_count} onChange={set("current_project_count")} type="number" min="0" max="100" />
            </label>
          </fieldset>
        ) : (
          <fieldset className="wf-design">
            <legend>Hồ sơ AI</legend>
            <label>Nhà cung cấp
              <input value={form.provider} onChange={set("provider")} maxLength={60} placeholder="VD: anthropic, groq, ollama" />
            </label>
            <label>Model
              <input value={form.model} onChange={set("model")} maxLength={160} placeholder="VD: openai/gpt-oss-120b" />
            </label>
            <label>Runtime
              <select value={form.runtime} onChange={set("runtime")}>
                <option value="model-api">Model API (gọi qua provider)</option>
                <option value="coding-agent">Coding Agent (runtime riêng)</option>
              </select>
            </label>
            <label>Liên kết Agent trong MindFlow (tuỳ chọn)
              <select value={form.agent_id} onChange={set("agent_id")}>
                <option value="">Không liên kết — hồ sơ độc lập</option>
                {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
              </select>
            </label>
            <label>Tools được phép dùng (cách nhau dấu phẩy)
              <input value={form.allowed_tools} onChange={set("allowed_tools")} placeholder="VD: fs, git" />
            </label>
            <label>Phạm vi bị cấm — ràng buộc cứng (cách nhau dấu phẩy)
              <input value={form.denied_scopes} onChange={set("denied_scopes")} placeholder="VD: payment-data" />
            </label>
            <label>Giới hạn token mỗi task (tuỳ chọn)
              <input value={form.token_limit_per_task} onChange={set("token_limit_per_task")} type="number" min="1" placeholder="VD: 200000" />
            </label>
          </fieldset>
        )}

        <label>Ghi chú
          <textarea value={form.notes} onChange={set("notes")} maxLength={2000} rows={2} placeholder="Điểm mạnh, lưu ý khi phân công…" />
        </label>

        <div className="wf-actions">
          <button type="submit" className="wf-btn primary" disabled={busy}>
            {editingId ? <Pencil size={15} /> : <Plus size={15} />} {editingId ? "Lưu thay đổi" : "Thêm vào đội ngũ"}
          </button>
          {editingId && <button type="button" className="wf-btn" onClick={cancelEdit} disabled={busy}>Huỷ sửa</button>}
        </div>
      </form>
    </section>

    <section aria-label="Danh sách nguồn lực">
      {loading ? <p className="wf-empty">Đang tải…</p> : visible.length === 0 ? (
        <p className="wf-empty">{tab === "ai" ? "Chưa có AI nào. Thêm AI đầu tiên bằng form phía trên." : "Chưa có nhân viên nào. Thêm nhân viên đầu tiên bằng form phía trên."}</p>
      ) : (
        <div className="wf-list">
          {visible.map((resource) => (
            <article className="wf-card" key={resource.id}>
              <h2>{resource.type === "ai" ? <Bot size={17} /> : <UserRound size={17} />} {resource.name}</h2>
              <p>{resource.role} · {statusLabel(resource.type, resource.availability_status)}</p>
              {resource.skills?.length > 0 && (
                <div className="wf-chip-row">
                  {resource.skills.map((skill) => <span className="wf-chip" key={skill.name} style={{ cursor: "default" }}>{skill.name} · {skill.level}/5</span>)}
                </div>
              )}
              {resource.type === "human" && resource.human && (
                <p>
                  {resource.human.experience_years != null && <>Kinh nghiệm {resource.human.experience_years} năm · </>}
                  {resource.human.hours_per_week != null && <>{resource.human.hours_per_week} giờ/tuần · </>}
                  Đang tham gia {resource.human.current_project_count} dự án
                </p>
              )}
              {resource.type === "ai" && resource.ai && (
                <p>
                  {[resource.ai.provider, resource.ai.model].filter(Boolean).join(" · ") || "Chưa khai provider/model"}
                  {resource.ai.runtime === "coding-agent" ? " · Coding Agent" : " · Model API"}
                  {resource.ai.agent_id ? " · Đã liên kết Agent" : ""}
                </p>
              )}
              {resource.type === "ai" && resource.ai?.denied_scopes?.length > 0 && (
                <span className="wf-badge high">Cấm: {resource.ai.denied_scopes.join(", ")}</span>
              )}
              {resource.cost_per_hour != null && <span className="wf-badge low">Chi phí: {resource.cost_per_hour}/giờ</span>}
              {resource.notes && <p>{resource.notes}</p>}
              <div className="wf-actions">
                <button type="button" className="wf-btn" onClick={() => startEdit(resource)}><Pencil size={14} /> Sửa</button>
                <button type="button" className="wf-btn" onClick={() => setConfirmDelete(resource)}><Trash2 size={14} /> Xoá</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>

    <ConfirmDialog
      open={Boolean(confirmDelete)}
      title="Xoá nguồn lực"
      confirmLabel="Xoá"
      busy={busy}
      onConfirm={removeResource}
      onClose={() => setConfirmDelete(null)}>
      Xoá &quot;{confirmDelete?.name}&quot; khỏi danh sách nguồn lực? Các phân công đã duyệt trước đây không bị ảnh hưởng. Không thể hoàn tác.
    </ConfirmDialog>
  </div>;
}
