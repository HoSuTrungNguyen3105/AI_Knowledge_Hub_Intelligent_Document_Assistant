"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CalendarClock,
  Eye,
  History,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
  Zap,
} from "lucide-react";
import { ConfirmDialog } from "../confirm-dialog";
import { agentsService } from "../../services/agents";
import { n8nPlatformService } from "../../services/n8n-platform";
import {
  getScheduleError,
  workflowSchedulesService,
} from "../../services/workflow-schedules";
import { useNotice } from "../../stores/notice";

const ROLES = [
  { role: "AI Leader", hint: "leader" },
  { role: "AI Planner", hint: "planner" },
  { role: "AI Architect", hint: "architect" },
  { role: "AI Developer", hint: "developer" },
  { role: "AI Tester", hint: "tester" },
  { role: "AI Reviewer", hint: "reviewer" },
  { role: "AI Researcher", hint: "researcher" },
];

const STATUS_LABEL = {
  active: "Đang hoạt động",
  paused: "Tạm dừng",
  completed: "Đã hoàn thành",
  error: "Lỗi",
};

const TYPE_OPTIONS = [
  ["once", "Một lần"],
  ["daily", "Hằng ngày"],
  ["weekly", "Hằng tuần"],
  ["monthly", "Hằng tháng"],
  ["interval", "Theo khoảng thời gian"],
  ["cron", "Cron tùy chỉnh"],
];

const TIMEZONES = [
  "Asia/Ho_Chi_Minh",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Tokyo",
  "UTC",
  "Europe/London",
  "America/New_York",
];

const EXECUTION_STATUS = {
  running: "Đang chạy",
  success: "Thành công",
  failed: "Thất bại",
  skipped: "Bị bỏ qua",
};

const WEEKDAYS = [
  [1, "T2"],
  [2, "T3"],
  [3, "T4"],
  [4, "T5"],
  [5, "T6"],
  [6, "T7"],
  [7, "CN"],
];

function emptyForm() {
  return {
    id: null,
    name: "",
    description: "",
    targetKind: "factory",
    workflowId: "",
    payloadText: "",
    requirement: "",
    domain: "",
    scheduleType: "daily",
    hour: 8,
    minute: 0,
    weekdays: [1],
    dayOfMonth: 1,
    runAt: "",
    every: 30,
    unit: "minutes",
    cron: "",
    timezone: "Asia/Ho_Chi_Minh",
    concurrency: "skip",
    notifySuccess: false,
    notifyFailure: true,
    maxRuns: "",
    status: "active",
    assignments: {},
  };
}

function toLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function formFromSchedule(schedule) {
  const config = schedule.config || {};
  const form = emptyForm();
  form.id = schedule.id;
  form.name = schedule.name;
  form.description = schedule.description || "";
  const target = schedule.target || { kind: "factory" };
  form.targetKind = target.kind || "factory";
  form.workflowId = target.workflow_id || "";
  form.payloadText =
    target.payload && Object.keys(target.payload).length
      ? JSON.stringify(target.payload, null, 2)
      : "";
  form.requirement = schedule.factory_request?.requirement || "";
  form.domain = (schedule.factory_request?.domain || []).join(", ");
  form.assignments = schedule.factory_request?.assignments || {};
  form.scheduleType = schedule.schedule_type;
  form.cron = schedule.cron_expression || "";
  form.timezone = schedule.timezone;
  form.hour = config.hour ?? 8;
  form.minute = config.minute ?? 0;
  form.weekdays = config.weekdays?.length ? config.weekdays : [1];
  form.dayOfMonth = config.day_of_month ?? 1;
  form.runAt = toLocalInput(config.run_at);
  form.every = config.every ?? 30;
  form.unit = config.unit || "minutes";
  form.concurrency = schedule.concurrency_policy || "skip";
  form.notifySuccess = Boolean(schedule.notify_on_success);
  form.notifyFailure = Boolean(schedule.notify_on_failure);
  form.maxRuns = schedule.max_runs ?? "";
  form.status = schedule.status;
  return form;
}

function buildTiming(form) {
  const config = {};
  if (form.scheduleType === "once") config.run_at = form.runAt || null;
  if (["daily", "weekly", "monthly"].includes(form.scheduleType)) {
    config.hour = Number(form.hour);
    config.minute = Number(form.minute);
  }
  if (form.scheduleType === "weekly") config.weekdays = form.weekdays;
  if (form.scheduleType === "monthly") config.day_of_month = Number(form.dayOfMonth);
  if (form.scheduleType === "interval") {
    config.every = Number(form.every);
    config.unit = form.unit;
  }
  return {
    schedule_type: form.scheduleType,
    cron_expression: form.scheduleType === "cron" ? form.cron.trim() : null,
    config,
    timezone: form.timezone,
  };
}

function buildPayload(form, payloadJson = {}) {
  const base = {
    name: form.name.trim(),
    description: form.description.trim(),
    ...buildTiming(form),
    concurrency_policy: form.concurrency,
    notify_on_success: form.notifySuccess,
    notify_on_failure: form.notifyFailure,
    max_runs: form.maxRuns === "" ? null : Number(form.maxRuns),
  };
  if (form.targetKind === "n8n_workflow") {
    return {
      ...base,
      target: {
        kind: "n8n_workflow",
        workflow_id: form.workflowId,
        payload: payloadJson,
      },
    };
  }
  const chosen = {};
  for (const { role } of ROLES) {
    if (form.assignments[role]) chosen[role] = form.assignments[role];
  }
  return {
    ...base,
    target: { kind: "factory" },
    factory_request: {
      requirement: form.requirement.trim(),
      domain: form.domain.split(",").map((d) => d.trim()).filter(Boolean),
      assignments: chosen,
    },
  };
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function SchedulesWorkspace() {
  const showNotice = useNotice((state) => state.show);
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({ total: 0, active: 0, paused: 0, completed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [agents, setAgents] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [health, setHealth] = useState(null);
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deletion, setDeletion] = useState(null);
  const [historyId, setHistoryId] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const load = useCallback(async (signal) => {
    try {
      const data = await workflowSchedulesService.list(
        { status: statusFilter || undefined, search: search || undefined },
        signal,
      );
      setItems(data.items || []);
      setStats(data.stats || { total: 0, active: 0, paused: 0, completed: 0 });
      setError("");
    } catch (e) {
      if (e?.name !== "AbortError") {
        setError(getScheduleError(e, "Không tải được danh sách lịch."));
      }
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    n8nPlatformService
      .listWorkflows(controller.signal)
      .then((data) => setWorkflows(data.items || []))
      .catch(() => {});
    workflowSchedulesService
      .getHealth(controller.signal)
      .then((data) => setHealth(data))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    agentsService
      .list(controller.signal)
      .then((list) => {
        setAgents(list);
        setForm((prev) => {
          if (!prev || Object.keys(prev.assignments).length) return prev;
          const next = { ...prev, assignments: { ...prev.assignments } };
          for (const { role, hint } of ROLES) {
            const match = list.find((a) => a.name.toLowerCase().includes(hint));
            if (match) next.assignments[role] = match.id;
          }
          return next;
        });
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const set = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setPreview(null);
  };

  const toggleWeekday = (day) => {
    setForm((prev) => {
      const has = prev.weekdays.includes(day);
      const weekdays = has
        ? prev.weekdays.filter((d) => d !== day)
        : [...prev.weekdays, day].sort();
      return { ...prev, weekdays };
    });
    setPreview(null);
  };

  const runPreview = async () => {
    setPreviewBusy(true);
    setFormError("");
    try {
      const data = await workflowSchedulesService.preview(buildTiming(form));
      setPreview(data);
    } catch (e) {
      setFormError(getScheduleError(e, "Không xem trước được lịch này."));
    } finally {
      setPreviewBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      let payloadJson = {};
      if (form.targetKind === "n8n_workflow") {
        if (!form.workflowId) {
          setFormError("Hãy chọn workflow đích cho lịch này.");
          setBusy(false);
          return;
        }
        const text = form.payloadText.trim();
        if (text) {
          try {
            payloadJson = JSON.parse(text);
          } catch {
            setFormError(
              "Dữ liệu gửi kèm chưa phải JSON hợp lệ — sửa lại hoặc để trống.",
            );
            setBusy(false);
            return;
          }
          if (
            typeof payloadJson !== "object" ||
            payloadJson === null ||
            Array.isArray(payloadJson)
          ) {
            setFormError("Dữ liệu gửi kèm phải là một đối tượng JSON.");
            setBusy(false);
            return;
          }
        }
      }
      const payload = buildPayload(form, payloadJson);
      if (form.id) {
        await workflowSchedulesService.update(form.id, payload);
        showNotice("Đã cập nhật lịch chạy.");
      } else {
        await workflowSchedulesService.create({ ...payload, status: form.status });
        showNotice("Đã tạo lịch chạy.");
      }
      setForm(null);
      setPreview(null);
      setLoading(true);
      await load();
    } catch (e) {
      setFormError(getScheduleError(e, "Không lưu được lịch này."));
    } finally {
      setBusy(false);
    }
  };

  const togglePause = async (schedule) => {
    setBusy(true);
    try {
      if (schedule.status === "active") {
        await workflowSchedulesService.pause(schedule.id);
        showNotice("Đã tạm dừng lịch.");
      } else {
        await workflowSchedulesService.resume(schedule.id);
        showNotice("Đã kích hoạt lại lịch.");
      }
      await load();
    } catch (e) {
      setError(getScheduleError(e, "Không đổi được trạng thái lịch."));
    } finally {
      setBusy(false);
    }
  };

  const runNow = async (schedule) => {
    setBusy(true);
    try {
      const execution = await workflowSchedulesService.runNow(schedule.id);
      if (execution.status === "skipped") {
        showNotice("Lịch đang có lượt chạy chưa xong nên lần này bị bỏ qua.");
      } else if (execution.status === "failed") {
        showNotice("Không kích hoạt được — kiểm tra n8n ở máy của bạn.");
      } else if (schedule.target?.kind === "n8n_workflow") {
        showNotice(
          "Đã kích hoạt chạy ngay — xem tiến trình ở tab Workflow Management.",
        );
      } else {
        showNotice("Đã kích hoạt chạy ngay — xem tiến trình ở tab AI Factory.");
      }
      await load();
      if (historyId === schedule.id) await loadExecutions(schedule.id);
    } catch (e) {
      setError(getScheduleError(e, "Không chạy ngay được lịch này."));
    } finally {
      setBusy(false);
    }
  };

  const loadExecutions = async (scheduleId) => {
    setHistoryLoading(true);
    try {
      const data = await workflowSchedulesService.listExecutions(scheduleId);
      setExecutions(data.items || []);
    } catch (e) {
      setError(getScheduleError(e, "Không tải được lịch sử chạy."));
    } finally {
      setHistoryLoading(false);
    }
  };

  const toggleHistory = (schedule) => {
    if (historyId === schedule.id) {
      setHistoryId(null);
      return;
    }
    setHistoryId(schedule.id);
    loadExecutions(schedule.id);
  };

  const confirmDeletion = async () => {
    setBusy(true);
    try {
      await workflowSchedulesService.remove(deletion.id);
      showNotice("Đã xóa lịch chạy.");
      setDeletion(null);
      await load();
    } catch (e) {
      setError(getScheduleError(e, "Không xóa được lịch này."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wf-page">
      <div className="wf-header">
        <div>
          <h1>
            <CalendarClock size={26} /> Lịch chạy Workflow
          </h1>
          <p className="muted">
            Đặt lịch để hệ thống tự kích hoạt đúng giờ qua n8n — cho đội Agent
            (AI Factory) hoặc bất kỳ workflow webhook nào — và báo kết quả qua
            chuông thông báo.
          </p>
        </div>
        <div className="wf-actions">
          <button
            type="button"
            className="wf-btn primary"
            onClick={() => {
              setForm(emptyForm());
              setFormError("");
              setPreview(null);
            }}
          >
            <Plus size={16} /> Tạo lịch
          </button>
        </div>
      </div>

      {error && (
        <p className="wf-error" role="alert">
          {error}
        </p>
      )}

      <div className="wf-sched-stats">
        <div className="wf-card">
          <strong>{stats.total}</strong>
          <span>Tổng số lịch</span>
        </div>
        <div className="wf-card">
          <strong>{stats.active}</strong>
          <span>Đang hoạt động</span>
        </div>
        <div className="wf-card">
          <strong>{stats.paused}</strong>
          <span>Tạm dừng</span>
        </div>
        <div className="wf-card">
          <strong>{stats.completed}</strong>
          <span>Đã hoàn thành</span>
        </div>
      </div>

      {health && (
        <div className="wf-sched-stats" aria-label="Sức khỏe đường chạy">
          <div className="wf-card">
            <strong>
              {health.external_tick_configured ? "Đã cấu hình" : "Chưa cấu hình"}
            </strong>
            <span>
              Tick ngoài (cron đánh thức backend) —{" "}
              {health.external_tick_configured
                ? "lịch chạy kể cả khi backend đang ngủ"
                : "chưa có: lịch chỉ chạy khi backend đang thức"}
            </span>
          </div>
          <div className="wf-card">
            <strong>
              {health.last_tick_at ? formatTime(health.last_tick_at) : "Chưa rõ"}
            </strong>
            <span>
              Lần tick gần nhất
              {health.last_tick_source
                ? health.last_tick_source === "external"
                  ? " (từ cron ngoài)"
                  : " (vòng lặp trong backend)"
                : ""}
            </span>
          </div>
          <div className="wf-card">
            <strong>
              {!health.n8n_configured
                ? "Chưa cấu hình"
                : health.n8n_reachable === null
                  ? "Chưa rõ"
                  : health.n8n_reachable
                    ? "Đang kết nối"
                    : "Không kết nối được"}
            </strong>
            <span>Kết nối n8n</span>
          </div>
        </div>
      )}

      <div className="wf-sched-toolbar">
        <input
          type="search"
          placeholder="Tìm theo tên lịch…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Tìm theo tên lịch"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Lọc theo trạng thái"
        >
          <option value="">Mọi trạng thái</option>
          <option value="active">Đang hoạt động</option>
          <option value="paused">Tạm dừng</option>
          <option value="completed">Đã hoàn thành</option>
          <option value="error">Lỗi</option>
        </select>
      </div>

      {form && (
        <form className="wf-card wf-form" onSubmit={submit}>
          <h2>{form.id ? "Chỉnh sửa lịch" : "Tạo lịch mới"}</h2>
          {formError && (
            <p className="wf-error" role="alert">
              {formError}
            </p>
          )}
          <label>
            Tên lịch
            <input
              required
              maxLength={200}
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Ví dụ: Bản tin EdTech sáng thứ Hai"
            />
          </label>
          <label>
            Mô tả
            <input
              maxLength={2000}
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </label>
          <label>
            Đích chạy
            <select
              value={form.targetKind}
              onChange={(e) => set("targetKind", e.target.value)}
            >
              <option value="factory">Đội Agent (AI Factory — workflow 07)</option>
              <option value="n8n_workflow">
                Một workflow n8n bất kỳ (qua Webhook)
              </option>
            </select>
          </label>
          {form.targetKind === "n8n_workflow" && (
            <>
              <label>
                Workflow đích
                <select
                  required
                  value={form.workflowId}
                  onChange={(e) => set("workflowId", e.target.value)}
                >
                  <option value="">— Chọn workflow —</option>
                  {workflows.map((workflow) => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.name}
                      {workflow.active ? "" : " (đang tắt)"}
                      {workflow.triggers?.includes("webhook")
                        ? ""
                        : " — chưa có Webhook trigger"}
                    </option>
                  ))}
                </select>
              </label>
              {!workflows.length && (
                <p className="muted">
                  Chưa lấy được danh sách workflow từ n8n — kiểm tra kết nối ở
                  tab Workflow Management.
                </p>
              )}
              <label>
                Dữ liệu gửi kèm (JSON, không bắt buộc)
                <textarea
                  rows={3}
                  value={form.payloadText}
                  onChange={(e) => set("payloadText", e.target.value)}
                  placeholder='{"topic": "tin sáng"}'
                />
              </label>
              <p className="muted">
                Tới giờ, lịch sẽ gọi Webhook của workflow đích kèm dữ liệu
                trên. Workflow cần đang bật và có node Webhook trigger thì mới
                chạy được.
              </p>
            </>
          )}
          {form.targetKind === "factory" && (
            <>
          <label>
            Yêu cầu cho đội Agent (nội dung lượt chạy)
            <textarea
              required
              rows={3}
              maxLength={32000}
              value={form.requirement}
              onChange={(e) => set("requirement", e.target.value)}
              placeholder="Ví dụ: Tổng hợp tin EdTech tuần qua thành bản tin ngắn"
            />
          </label>
          <label>
            Lĩnh vực (cách nhau bằng dấu phẩy)
            <input
              value={form.domain}
              onChange={(e) => set("domain", e.target.value)}
              placeholder="research, edtech"
            />
          </label>
          <div className="wf-sched-roles">
            {ROLES.map(({ role }) => (
              <label key={role}>
                {role}
                <select
                  value={form.assignments[role] || ""}
                  onChange={(e) =>
                    set("assignments", { ...form.assignments, [role]: e.target.value })
                  }
                >
                  <option value="">— Tự chọn khi chạy —</option>
                  {agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
            </>
          )}
          <div className="wf-sched-row">
            <label>
              Loại lịch
              <select
                value={form.scheduleType}
                onChange={(e) => set("scheduleType", e.target.value)}
              >
                {TYPE_OPTIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Múi giờ
              <select
                value={form.timezone}
                onChange={(e) => set("timezone", e.target.value)}
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </label>
            {!form.id && (
              <label>
                Trạng thái ban đầu
                <select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="active">Hoạt động ngay</option>
                  <option value="paused">Tạm dừng</option>
                </select>
              </label>
            )}
          </div>

          {form.scheduleType === "once" && (
            <label>
              Ngày và giờ chạy
              <input
                type="datetime-local"
                required
                value={form.runAt}
                onChange={(e) => set("runAt", e.target.value)}
              />
            </label>
          )}
          {["daily", "weekly", "monthly"].includes(form.scheduleType) && (
            <div className="wf-sched-row">
              <label>
                Giờ
                <input
                  type="number"
                  min={0}
                  max={23}
                  required
                  value={form.hour}
                  onChange={(e) => set("hour", e.target.value)}
                />
              </label>
              <label>
                Phút
                <input
                  type="number"
                  min={0}
                  max={59}
                  required
                  value={form.minute}
                  onChange={(e) => set("minute", e.target.value)}
                />
              </label>
              {form.scheduleType === "monthly" && (
                <label>
                  Ngày trong tháng
                  <input
                    type="number"
                    min={1}
                    max={31}
                    required
                    value={form.dayOfMonth}
                    onChange={(e) => set("dayOfMonth", e.target.value)}
                  />
                </label>
              )}
            </div>
          )}
          {form.scheduleType === "weekly" && (
            <div className="wf-chip-row" role="group" aria-label="Ngày trong tuần">
              {WEEKDAYS.map(([day, label]) => (
                <button
                  key={day}
                  type="button"
                  className={`wf-sched-day${form.weekdays.includes(day) ? " active" : ""}`}
                  onClick={() => toggleWeekday(day)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {form.scheduleType === "interval" && (
            <div className="wf-sched-row">
              <label>
                Lặp lại mỗi
                <input
                  type="number"
                  min={1}
                  required
                  value={form.every}
                  onChange={(e) => set("every", e.target.value)}
                />
              </label>
              <label>
                Đơn vị
                <select
                  value={form.unit}
                  onChange={(e) => set("unit", e.target.value)}
                >
                  <option value="minutes">Phút</option>
                  <option value="hours">Giờ</option>
                </select>
              </label>
            </div>
          )}
          {form.scheduleType === "cron" && (
            <label>
              Biểu thức cron (5 trường: phút giờ ngày tháng thứ)
              <input
                required
                maxLength={120}
                value={form.cron}
                onChange={(e) => set("cron", e.target.value)}
                placeholder="0 8 * * 1-5"
              />
            </label>
          )}

          <div className="wf-sched-row">
            <label>
              Nếu lần trước chưa chạy xong
              <select
                value={form.concurrency}
                onChange={(e) => set("concurrency", e.target.value)}
              >
                <option value="skip">Bỏ qua lần mới</option>
                <option value="queue">Xếp hàng chờ</option>
                <option value="allow_parallel">Cho chạy song song</option>
              </select>
            </label>
            <label>
              Số lần chạy tối đa (trống = không giới hạn)
              <input
                type="number"
                min={1}
                value={form.maxRuns}
                onChange={(e) => set("maxRuns", e.target.value)}
              />
            </label>
          </div>
          <div className="wf-sched-checks">
            <label>
              <input
                type="checkbox"
                checked={form.notifySuccess}
                onChange={(e) => set("notifySuccess", e.target.checked)}
              />{" "}
              Thông báo khi chạy thành công
            </label>
            <label>
              <input
                type="checkbox"
                checked={form.notifyFailure}
                onChange={(e) => set("notifyFailure", e.target.checked)}
              />{" "}
              Thông báo khi chạy thất bại
            </label>
          </div>

          <div className="wf-actions">
            <button
              type="button"
              className="wf-btn"
              onClick={runPreview}
              disabled={previewBusy}
            >
              <Eye size={16} /> {previewBusy ? "Đang tính…" : "Xem trước lịch chạy"}
            </button>
            <button type="submit" className="wf-btn primary" disabled={busy}>
              {form.id ? "Lưu thay đổi" : "Tạo lịch"}
            </button>
            <button
              type="button"
              className="wf-btn"
              onClick={() => setForm(null)}
            >
              Hủy
            </button>
          </div>
          {preview && (
            <div className="wf-sched-preview">
              <strong>{preview.description_text}</strong>
              <ul>
                {preview.next_runs.map((run) => (
                  <li key={run}>{formatTime(run)}</li>
                ))}
              </ul>
              {preview.warnings?.map((warning) => (
                <p key={warning} className="wf-sched-warning">
                  {warning}
                </p>
              ))}
            </div>
          )}
        </form>
      )}

      {loading ? (
        <p className="wf-empty">Đang tải…</p>
      ) : !items.length ? (
        <p className="wf-empty">
          Chưa có lịch chạy nào. Bấm “Tạo lịch” để đặt lịch đầu tiên.
        </p>
      ) : (
        <div className="wf-sched-list">
          {items.map((schedule) => (
            <article key={schedule.id} className="wf-card wf-sched-card">
              <div className="wf-sched-card-head">
                <h2>{schedule.name}</h2>
                <span
                  className={`wf-badge wf-sched-status ${schedule.status}`}
                >
                  {STATUS_LABEL[schedule.status] || schedule.status}
                </span>
              </div>
              {schedule.description && <p>{schedule.description}</p>}
              <p className="wf-sched-desc">{schedule.description_text}</p>
              <dl className="wf-sched-meta">
                <div>
                  <dt>Lần chạy tiếp theo</dt>
                  <dd>{formatTime(schedule.next_run_at)}</dd>
                </div>
                <div>
                  <dt>Lần chạy gần nhất</dt>
                  <dd>{formatTime(schedule.last_run_at)}</dd>
                </div>
                <div>
                  <dt>Đã chạy</dt>
                  <dd>{schedule.run_count} lần</dd>
                </div>
              </dl>
              {schedule.target?.kind === "n8n_workflow" ? (
                <p className="wf-sched-req">
                  Đích: workflow “
                  {workflows.find((w) => w.id === schedule.target.workflow_id)
                    ?.name || schedule.target.workflow_id}
                  ”
                </p>
              ) : (
                <p className="wf-sched-req">
                  Yêu cầu: {schedule.factory_request?.requirement}
                </p>
              )}
              <div className="wf-actions">
                {schedule.status === "active" && (
                  <button
                    type="button"
                    className="wf-btn"
                    disabled={busy}
                    onClick={() => togglePause(schedule)}
                  >
                    <Pause size={15} /> Tạm dừng
                  </button>
                )}
                {schedule.status === "paused" && (
                  <button
                    type="button"
                    className="wf-btn"
                    disabled={busy}
                    onClick={() => togglePause(schedule)}
                  >
                    <Play size={15} /> Kích hoạt lại
                  </button>
                )}
                {schedule.status !== "completed" && (
                  <button
                    type="button"
                    className="wf-btn"
                    disabled={busy}
                    onClick={() => runNow(schedule)}
                  >
                    <Zap size={15} /> Chạy ngay
                  </button>
                )}
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => toggleHistory(schedule)}
                >
                  <History size={15} /> Lịch sử
                </button>
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => {
                    setForm(formFromSchedule(schedule));
                    setFormError("");
                    setPreview(null);
                  }}
                >
                  <Pencil size={15} /> Sửa
                </button>
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => setDeletion(schedule)}
                >
                  <Trash2 size={15} /> Xóa
                </button>
              </div>
              {historyId === schedule.id && (
                <div className="wf-sched-history">
                  {historyLoading ? (
                    <p className="wf-empty">Đang tải lịch sử…</p>
                  ) : !executions.length ? (
                    <p className="wf-empty">Chưa có lượt chạy nào.</p>
                  ) : (
                    <ul>
                      {executions.map((execution) => (
                        <li key={execution.id}>
                          <span>
                            {formatTime(execution.started_at)} ·{" "}
                            {execution.trigger_type === "manual"
                              ? "Chạy thủ công"
                              : "Theo lịch"}
                          </span>
                          <span
                            className={`wf-badge wf-sched-status ${execution.status}`}
                          >
                            {EXECUTION_STATUS[execution.status] ||
                              execution.status}
                          </span>
                          {execution.error && (
                            <span className="wf-sched-history-error">
                              {execution.error}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(deletion)}
        title="Xóa lịch chạy này?"
        busy={busy}
        onClose={() => setDeletion(null)}
        onConfirm={confirmDeletion}
        confirmLabel="Xóa lịch"
      >
        Lịch “{deletion?.name}” sẽ bị xóa. Workflow gốc và lịch sử các lượt
        chạy đã tạo không bị ảnh hưởng.
      </ConfirmDialog>
    </div>
  );
}
