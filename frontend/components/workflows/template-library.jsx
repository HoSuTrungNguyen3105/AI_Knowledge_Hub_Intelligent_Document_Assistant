"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
import {
  getWorkflowTemplatesError,
  workflowTemplatesService,
} from "../../services/workflow-templates";
import { providerService } from "../../services/providers";
import { ModelSelect } from "../model-select";

const PAGE_SIZE = 24;

const REVIEW_TEXT = {
  pending_review: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã loại",
};
const COMPLEXITY_TEXT = { simple: "Đơn giản", medium: "Trung bình", complex: "Phức tạp" };

export function TemplateLibrary() {
  const [stats, setStats] = useState(null);
  const [sources, setSources] = useState([]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [mine, setMine] = useState([]);
  const [candidates, setCandidates] = useState({ available: [], updates: [] });
  const [syncOpen, setSyncOpen] = useState(false);
  const [selected, setSelected] = useState({});
  const [syncBusy, setSyncBusy] = useState("");
  const [syncNote, setSyncNote] = useState("");
  const [versions, setVersions] = useState([]);
  const [diffResult, setDiffResult] = useState(null);
  const [versionBusy, setVersionBusy] = useState("");
  const [contributeOpen, setContributeOpen] = useState(false);
  const [contributeForm, setContributeForm] = useState({ name: "", category: "Community", json: "" });
  const [contributeBusy, setContributeBusy] = useState(false);
  const [assistantBusy, setAssistantBusy] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState(null);
  const [assistantNode, setAssistantNode] = useState("");
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantProviders, setAssistantProviders] = useState([]);
  const [assistantProviderId, setAssistantProviderId] = useState("");
  const [assistantModels, setAssistantModels] = useState([]);
  const [assistantModelId, setAssistantModelId] = useState("");

  useEffect(() => {
    let cancelled = false;
    providerService
      .list()
      .then((data) => {
        if (cancelled) return;
        const ready = (data.providers || []).filter(
          (provider) => provider.implemented && provider.configured && provider.enabled,
        );
        setAssistantProviders(ready);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!assistantProviderId) {
      setAssistantModels([]);
      setAssistantModelId("");
      return;
    }
    let cancelled = false;
    providerService
      .models(assistantProviderId)
      .then((data) => {
        if (cancelled) return;
        const chatModels = (data.models || []).filter(
          (model) => model.capabilities?.chat !== false,
        );
        setAssistantModels(chatModels);
        const provider = assistantProviders.find((item) => item.id === assistantProviderId);
        setAssistantModelId(
          chatModels.some((model) => model.id === provider?.default_model)
            ? provider.default_model
            : chatModels[0]?.id || "",
        );
      })
      .catch(() => {
        if (!cancelled) setAssistantModels([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assistantProviderId]);

  async function askAssistant(task) {
    if (!detail) return;
    setAssistantBusy(task);
    setError("");
    try {
      const data = await workflowTemplatesService.askAssistant(detail.id, {
        task,
        node_name: task === "explain_node" ? assistantNode || null : null,
        prompt: task === "customize" ? assistantPrompt : null,
        provider: assistantProviderId || null,
        model: assistantProviderId ? assistantModelId || null : null,
      });
      setAssistantAnswer(data);
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Trợ lý AI không trả lời được. Hãy thử lại."));
    } finally {
      setAssistantBusy("");
    }
  }

  async function applyProposal() {
    if (!detail || !assistantAnswer?.proposal) return;
    setAssistantBusy("apply");
    setError("");
    try {
      const installed = await workflowTemplatesService.applyAssistant(detail.id, {
        workflow_json: assistantAnswer.proposal,
      });
      setSyncNote(
        `Đã áp dụng bản tùy chỉnh "${installed.template_name}" vào tài khoản — workflow đang tắt trong n8n, mở tab n8n Platform để cấu hình và Bật.`,
      );
      setAssistantAnswer(null);
      loadSync();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Áp dụng đề xuất thất bại. Hãy thử lại."));
    } finally {
      setAssistantBusy("");
    }
  }

  useEffect(() => {
    if (!detail) {
      setVersions([]);
      setDiffResult(null);
      return;
    }
    workflowTemplatesService
      .listVersions(detail.id)
      .then((data) => setVersions(data || []))
      .catch(() => setVersions([]));
  }, [detail?.id, detail?.version]);

  async function showDiff(fromVersion) {
    if (!detail) return;
    setVersionBusy(`diff-${fromVersion}`);
    setError("");
    try {
      const data = await workflowTemplatesService.diffVersions(detail.id, fromVersion, detail.version);
      setDiffResult(data);
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không so sánh được hai phiên bản."));
    } finally {
      setVersionBusy("");
    }
  }

  async function restore(version) {
    if (!detail) return;
    setVersionBusy(`restore-${version}`);
    setError("");
    try {
      const updated = await workflowTemplatesService.restoreVersion(detail.id, version);
      setDetail(updated);
      setDiffResult(null);
      setSyncNote(`Đã khôi phục nội dung phiên bản ${version} thành phiên bản mới v${updated.version}.`);
      load();
      loadStats();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Khôi phục thất bại. Hãy thử lại."));
    } finally {
      setVersionBusy("");
    }
  }

  async function submitContribute() {
    let workflowJson;
    try {
      workflowJson = JSON.parse(contributeForm.json);
    } catch {
      setError("JSON đóng góp chưa hợp lệ — hãy kiểm tra lại cú pháp JSON.");
      return;
    }
    if (!contributeForm.name.trim()) {
      setError("Hãy đặt tên cho template đóng góp.");
      return;
    }
    setContributeBusy(true);
    setError("");
    try {
      const created = await workflowTemplatesService.contribute({
        name: contributeForm.name.trim(),
        category: contributeForm.category.trim() || "Community",
        workflow_json: workflowJson,
      });
      setSyncNote(`Đã đóng góp template "${created.name}" — đang ở trạng thái Chờ duyệt trong thư viện.`);
      setContributeForm({ name: "", category: "Community", json: "" });
      setContributeOpen(false);
      load();
      loadStats();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Đóng góp thất bại. Hãy thử lại."));
    } finally {
      setContributeBusy(false);
    }
  }

  const loadSync = useCallback(async () => {
    try {
      const [mineList, candidateData] = await Promise.all([
        workflowTemplatesService.listMine(),
        workflowTemplatesService.syncCandidates(),
      ]);
      setMine(mineList || []);
      setCandidates(candidateData || { available: [], updates: [] });
    } catch {
      // Sync sections degrade gracefully.
    }
  }, []);

  useEffect(() => {
    loadSync();
  }, [loadSync]);

  const installedByTemplate = {};
  for (const item of mine) installedByTemplate[item.template_id] = item;

  async function installSelected() {
    const ids = Object.keys(selected).filter((id) => selected[id]);
    if (!ids.length) return;
    setSyncBusy("install");
    setSyncNote("");
    setError("");
    try {
      const data = await workflowTemplatesService.install(ids);
      const installed = data.results.filter((r) => r.status === "installed").length;
      const already = data.results.filter((r) => r.status === "already_installed").length;
      const failed = data.results.filter((r) => r.status === "failed");
      setSyncNote(
        `Đã cài ${installed} workflow vào n8n (đang tắt — mở tab n8n Platform để gắn credential và Bật).` +
          (already ? ` ${already} template đã cài từ trước.` : "") +
          (failed.length
            ? ` ${failed.length} template cài lỗi: ${failed.map((r) => `${r.template_name || r.template_id} (${r.error || "?"})`).join(", ")}.`
            : ""),
      );
      setSelected({});
      loadSync();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Cài template thất bại. Hãy thử lại."));
    } finally {
      setSyncBusy("");
    }
  }

  async function installOne(template) {
    setSyncBusy(template.id);
    setError("");
    try {
      const data = await workflowTemplatesService.install([template.id]);
      const result = data.results[0];
      if (result?.status === "failed") {
        setError(
          getWorkflowTemplatesError(
            { response: { data: { detail: { code: result.error } } } },
            "Cài template thất bại.",
          ),
        );
      } else {
        setSyncNote(`Đã cài "${template.name}" vào n8n (đang tắt).`);
        loadSync();
      }
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Cài template thất bại. Hãy thử lại."));
    } finally {
      setSyncBusy("");
    }
  }

  async function updateInstall(item) {
    setSyncBusy(item.id);
    setError("");
    try {
      await workflowTemplatesService.updateMine(item.id);
      setSyncNote(`Đã cập nhật "${item.template_name}" lên bản mới nhất.`);
      loadSync();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Cập nhật thất bại. Hãy thử lại."));
    } finally {
      setSyncBusy("");
    }
  }

  async function removeInstall(item) {
    setSyncBusy(item.id);
    setError("");
    try {
      await workflowTemplatesService.removeMine(item.id);
      setSyncNote(
        `Đã gỡ "${item.template_name}" khỏi tài khoản và xóa bản sao trong n8n. Bản gốc vẫn còn trong thư viện.`,
      );
      loadSync();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Gỡ thất bại. Hãy thử lại."));
    } finally {
      setSyncBusy("");
    }
  }
  const [filters, setFilters] = useState({
    q: "",
    category: "",
    source_id: "",
    service: "",
    complexity: "",
    compatibility: "",
    review_status: "",
    sort: "name",
  });
  const searchTimer = useRef(null);

  const loadStats = useCallback(async () => {
    try {
      const [statsData, sourceList] = await Promise.all([
        workflowTemplatesService.getStats(),
        workflowTemplatesService.listSources(),
      ]);
      setStats(statsData);
      setSources(sourceList || []);
    } catch {
      // Filters degrade gracefully without stats.
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE, sort: filters.sort };
      for (const key of ["q", "category", "source_id", "service", "complexity", "compatibility", "review_status"]) {
        if (filters[key]) params[key] = filters[key];
      }
      const data = await workflowTemplatesService.listTemplates(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không tải được thư viện mẫu."));
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    load();
  }, [load]);

  function setFilter(key, value) {
    setPage(0);
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function onSearch(value) {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setFilter("q", value), 300);
  }

  async function openDetail(item) {
    setDetailLoading(true);
    setError("");
    try {
      const data = await workflowTemplatesService.getTemplate(item.id);
      setDetail(data);
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không mở được chi tiết template."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function review(status) {
    if (!detail) return;
    setReviewBusy(true);
    setError("");
    try {
      const updated = await workflowTemplatesService.reviewTemplate(detail.id, status);
      setDetail({ ...detail, review_status: updated.review_status });
      load();
      loadStats();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không cập nhật được trạng thái duyệt."));
    } finally {
      setReviewBusy(false);
    }
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const categories = stats ? Object.keys(stats.by_category || {}) : [];
  const services = stats?.services || [];

  return (
    <div className="fx-page">
      <section className="fx-card">
        <h2>
          <BookOpen size={17} /> Thư viện Workflow mẫu
        </h2>
        <p className="fx-run-meta">
          {stats
            ? `${stats.total} template · ${stats.by_review_status?.pending_review || 0} chờ duyệt · ${stats.by_review_status?.approved || 0} đã duyệt · ${stats.by_compatibility?.needs_community_nodes || 0} cần community node.`
            : "Đang tải thống kê…"}{" "}
          Chỉ template đã duyệt mới cài được vào tài khoản. Muốn nhập thêm template, dùng mục
          Nguồn template ở tab n8n Platform.
        </p>
        {error ? (
          <p className="fx-alert" role="alert">
            {error}
          </p>
        ) : null}
        {syncNote ? <p className="fx-run-meta">{syncNote}</p> : null}
        <div className="fx-actions">
          <button
            type="button"
            className="fx-btn primary"
            onClick={() => setSyncOpen(!syncOpen)}
          >
            <RefreshCw size={15} /> Đồng bộ Workflow
            {candidates.available.length
              ? ` (${candidates.available.length} mẫu mới)`
              : ""}
            {candidates.updates.length ? ` · ${candidates.updates.length} có bản mới` : ""}
          </button>
        </div>
        {syncOpen ? (
          <div className="n8n-node">
            <h3>Chọn template muốn thêm vào tài khoản</h3>
            {candidates.available.length === 0 ? (
              <p className="fx-run-meta">
                Không có template mới nào đang chờ — mọi template đã duyệt đều đã được cài, hoặc
                chưa có template nào được duyệt.
              </p>
            ) : (
              candidates.available.map((template) => (
                <label key={template.id} className="tpl-check">
                  <input
                    type="checkbox"
                    checked={Boolean(selected[template.id])}
                    onChange={(event) =>
                      setSelected((current) => ({
                        ...current,
                        [template.id]: event.target.checked,
                      }))
                    }
                  />
                  <span>
                    <strong>{template.name}</strong> · {template.category} · {template.node_count}{" "}
                    node · v{template.version}
                    {template.compatibility === "needs_community_nodes"
                      ? " · Cần community node"
                      : ""}
                    {template.security_flag ? " · Nghi ngờ secret" : ""}
                  </span>
                </label>
              ))
            )}
            <div className="fx-actions">
              <button
                type="button"
                className="fx-btn primary"
                onClick={installSelected}
                disabled={syncBusy === "install" || !Object.values(selected).some(Boolean)}
              >
                {syncBusy === "install" ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Download size={15} />
                )}
                Cài đã chọn vào n8n
              </button>
            </div>
            {candidates.updates.length ? (
              <>
                <h3>Đã cài nhưng có phiên bản mới</h3>
                {candidates.updates.map((item) => (
                  <p key={item.id} className="fx-run-meta tpl-check">
                    <span>
                      <strong>{item.template_name}</strong> · đang v{item.installed_version} → mới
                      v{item.latest_version}
                    </span>
                    <button
                      type="button"
                      className="fx-btn"
                      onClick={() => updateInstall(item)}
                      disabled={syncBusy === item.id}
                    >
                      Cập nhật
                    </button>
                  </p>
                ))}
              </>
            ) : null}
          </div>
        ) : null}
        {mine.length ? (
          <div className="n8n-node">
            <h3>Đã cài của tôi ({mine.length})</h3>
            {mine.map((item) => (
              <p key={item.id} className="fx-run-meta tpl-check">
                <span>
                  <strong>{item.template_name}</strong> · {item.category} · v
                  {item.installed_version}
                  {item.update_available ? ` · Có bản mới v${item.latest_version}` : ""}
                </span>
                <span className="fx-actions">
                  {item.update_available ? (
                    <button
                      type="button"
                      className="fx-btn"
                      onClick={() => updateInstall(item)}
                      disabled={syncBusy === item.id}
                    >
                      Cập nhật
                    </button>
                  ) : null}
                  <a className="fx-btn" href="/agents/workflows?tab=n8n">
                    Mở trong n8n Platform
                  </a>
                  <button
                    type="button"
                    className="fx-btn"
                    onClick={() => removeInstall(item)}
                    disabled={syncBusy === item.id}
                  >
                    <Trash2 size={14} /> Gỡ
                  </button>
                </span>
              </p>
            ))}
          </div>
        ) : null}
        <div className="fx-actions">
          <button
            type="button"
            className="fx-btn"
            onClick={() => setContributeOpen(!contributeOpen)}
          >
            Đóng góp template của bạn
          </button>
        </div>
        {contributeOpen ? (
          <div className="n8n-node">
            <h3>Đóng góp template vào thư viện chung</h3>
            <p className="fx-run-meta">
              Template đóng góp sẽ vào thư viện ở trạng thái Chờ duyệt, mang nhãn Community. Dán
              JSON workflow xuất từ n8n — hệ thống kiểm tra cấu trúc và quét secret giống template
              nhập từ GitHub.
            </p>
            <div className="tpl-filters">
              <label className="fx-field">
                Tên template
                <input
                  className="fx-input"
                  type="text"
                  value={contributeForm.name}
                  onChange={(event) =>
                    setContributeForm((c) => ({ ...c, name: event.target.value }))
                  }
                />
              </label>
              <label className="fx-field">
                Danh mục
                <input
                  className="fx-input"
                  type="text"
                  value={contributeForm.category}
                  onChange={(event) =>
                    setContributeForm((c) => ({ ...c, category: event.target.value }))
                  }
                />
              </label>
            </div>
            <label className="fx-field">
              JSON workflow
              <textarea
                className="fx-input tpl-json-input"
                rows={8}
                value={contributeForm.json}
                onChange={(event) =>
                  setContributeForm((c) => ({ ...c, json: event.target.value }))
                }
                placeholder='{"name": "...", "nodes": [...], "connections": {...}}'
              />
            </label>
            <div className="fx-actions">
              <button
                type="button"
                className="fx-btn primary"
                onClick={submitContribute}
                disabled={contributeBusy}
              >
                {contributeBusy ? <Loader2 size={15} className="spin" /> : null} Gửi đóng góp
              </button>
            </div>
          </div>
        ) : null}
        <div className="tpl-filters">
          <label className="fx-field tpl-search">
            <Search size={14} /> Tìm theo tên
            <input
              className="fx-input"
              type="text"
              placeholder="Ví dụ: Telegram report…"
              onChange={(event) => onSearch(event.target.value)}
            />
          </label>
          <label className="fx-field">
            Danh mục
            <select
              className="fx-input"
              value={filters.category}
              onChange={(event) => setFilter("category", event.target.value)}
            >
              <option value="">Tất cả</option>
              {categories.map((category) => (
                <option key={category} value={category}>
                  {category} ({stats.by_category[category]})
                </option>
              ))}
            </select>
          </label>
          <label className="fx-field">
            Nguồn
            <select
              className="fx-input"
              value={filters.source_id}
              onChange={(event) => setFilter("source_id", event.target.value)}
            >
              <option value="">Tất cả</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label className="fx-field">
            Dịch vụ tích hợp
            <select
              className="fx-input"
              value={filters.service}
              onChange={(event) => setFilter("service", event.target.value)}
            >
              <option value="">Tất cả</option>
              {services.map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </select>
          </label>
          <label className="fx-field">
            Phức tạp
            <select
              className="fx-input"
              value={filters.complexity}
              onChange={(event) => setFilter("complexity", event.target.value)}
            >
              <option value="">Tất cả</option>
              <option value="simple">Đơn giản</option>
              <option value="medium">Trung bình</option>
              <option value="complex">Phức tạp</option>
            </select>
          </label>
          <label className="fx-field">
            Tương thích
            <select
              className="fx-input"
              value={filters.compatibility}
              onChange={(event) => setFilter("compatibility", event.target.value)}
            >
              <option value="">Tất cả</option>
              <option value="compatible">Chạy được ngay</option>
              <option value="needs_community_nodes">Cần community node</option>
            </select>
          </label>
          <label className="fx-field">
            Trạng thái duyệt
            <select
              className="fx-input"
              value={filters.review_status}
              onChange={(event) => setFilter("review_status", event.target.value)}
            >
              <option value="">Tất cả</option>
              <option value="pending_review">Chờ duyệt</option>
              <option value="approved">Đã duyệt</option>
              <option value="rejected">Đã loại</option>
            </select>
          </label>
          <label className="fx-field">
            Sắp xếp
            <select
              className="fx-input"
              value={filters.sort}
              onChange={(event) => setFilter("sort", event.target.value)}
            >
              <option value="name">Tên A–Z</option>
              <option value="newest">Mới cập nhật</option>
              <option value="nodes">Nhiều node nhất</option>
            </select>
          </label>
        </div>
      </section>

      {detail ? (
        <section className="fx-card">
          <h2>
            {detail.name}
            <span style={{ marginLeft: "auto" }}>
              <button type="button" className="fx-btn" onClick={() => setDetail(null)}>
                <X size={15} /> Đóng
              </button>
            </span>
          </h2>
          <p className="fx-run-meta">
            {detail.category} · {detail.node_count} node ·{" "}
            {COMPLEXITY_TEXT[detail.complexity] || detail.complexity} · Phiên bản {detail.version}{" "}
            · {REVIEW_TEXT[detail.review_status] || detail.review_status}
            {detail.compatibility === "needs_community_nodes"
              ? " · Cần community node: " + detail.community_nodes.join(", ")
              : " · Tương thích n8n chuẩn"}
          </p>
          {detail.security_flag ? (
            <p className="fx-alert" role="alert">
              <ShieldAlert size={14} /> Nghi ngờ có secret hardcode trong tham số — cần kiểm tra kỹ
              trước khi dùng.
            </p>
          ) : null}
          {detail.risk_flags?.length ? (
            <p className="fx-run-meta">
              <AlertTriangle size={13} /> Cờ rủi ro: {detail.risk_flags.join(", ")}
              {detail.http_urls?.length ? ` · URL đích: ${detail.http_urls.join(", ")}` : ""}
            </p>
          ) : null}
          <p className="fx-run-meta">
            <strong>Node:</strong> {detail.node_types.join(", ") || "—"}
          </p>
          <p className="fx-run-meta">
            <strong>Credential cần tự tạo trong n8n:</strong>{" "}
            {detail.credential_types.length
              ? detail.credential_types.join(", ")
              : "Không cần credential nào."}
          </p>
          {detail.attribution ? (
            <p className="fx-run-meta">
              {detail.attribution}
              {detail.source_url ? (
                <>
                  {" "}
                  <a href={detail.source_url} target="_blank" rel="noreferrer">
                    File gốc <ExternalLink size={12} />
                  </a>
                </>
              ) : null}
            </p>
          ) : null}
          <div className="n8n-node">
            <h3>Trợ lý AI cho template này</h3>
            <p className="fx-run-meta">
              AI dùng provider bạn đã cấu hình ở trang Providers. Đề xuất tùy chỉnh không bao giờ
              tự lưu — bạn xem trước rồi mới bấm Áp dụng, và bản áp dụng chỉ vào tài khoản của
              bạn, bản gốc trong thư viện không đổi.
            </p>
            <div className="tpl-filters">
              <label className="fx-field">
                Provider AI
                <select
                  className="fx-input"
                  value={assistantProviderId}
                  onChange={(event) => setAssistantProviderId(event.target.value)}
                  aria-label="Provider AI cho Trợ lý"
                >
                  <option value="">Tự động chọn</option>
                  {assistantProviders.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name || provider.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fx-field">
                Model
                <ModelSelect
                  models={assistantModels}
                  value={assistantModelId}
                  onChange={setAssistantModelId}
                  ariaLabel="Model AI cho Trợ lý"
                  disabled={!assistantProviderId || assistantModels.length === 0}
                  placeholder={assistantProviderId ? "Chọn model…" : "Tự động (chọn provider trước nếu muốn chỉ định)"}
                />
              </label>
            </div>
            <div className="fx-actions">
              <button type="button" className="fx-btn" onClick={() => askAssistant("explain")} disabled={Boolean(assistantBusy)}>
                {assistantBusy === "explain" ? <Loader2 size={14} className="spin" /> : null} Giải thích workflow
              </button>
              <button type="button" className="fx-btn" onClick={() => askAssistant("setup_guide")} disabled={Boolean(assistantBusy)}>
                {assistantBusy === "setup_guide" ? <Loader2 size={14} className="spin" /> : null} Hướng dẫn cấu hình
              </button>
              <button type="button" className="fx-btn" onClick={() => askAssistant("api_keys")} disabled={Boolean(assistantBusy)}>
                {assistantBusy === "api_keys" ? <Loader2 size={14} className="spin" /> : null} API key cần thiết
              </button>
            </div>
            <div className="tpl-filters">
              <label className="fx-field">
                Giải thích một node
                <select
                  className="fx-input"
                  value={assistantNode}
                  onChange={(event) => setAssistantNode(event.target.value)}
                >
                  <option value="">Chọn node…</option>
                  {(detail.workflow_json?.nodes || []).map((node) => (
                    <option key={node.name} value={node.name}>
                      {node.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="fx-actions">
                <button
                  type="button"
                  className="fx-btn"
                  onClick={() => askAssistant("explain_node")}
                  disabled={Boolean(assistantBusy) || !assistantNode}
                >
                  {assistantBusy === "explain_node" ? <Loader2 size={14} className="spin" /> : null} Giải thích node đã chọn
                </button>
              </div>
            </div>
            <label className="fx-field">
              Tùy chỉnh bằng yêu cầu tự nhiên (ví dụ: thay Telegram bằng Discord)
              <input
                className="fx-input"
                type="text"
                value={assistantPrompt}
                onChange={(event) => setAssistantPrompt(event.target.value)}
                placeholder="Mô tả thay đổi bạn muốn…"
              />
            </label>
            <div className="fx-actions">
              <button
                type="button"
                className="fx-btn primary"
                onClick={() => askAssistant("customize")}
                disabled={Boolean(assistantBusy) || !assistantPrompt.trim()}
              >
                {assistantBusy === "customize" ? <Loader2 size={14} className="spin" /> : null} Tạo đề xuất tùy chỉnh
              </button>
            </div>
            {assistantAnswer ? (
              <div>
                <p className="fx-run-meta">
                  {assistantAnswer.provider} · {assistantAnswer.model}
                </p>
                <pre className="tpl-json">{assistantAnswer.answer}</pre>
                {assistantAnswer.proposal ? (
                  <>
                    <details>
                      <summary>Xem JSON đề xuất</summary>
                      <pre className="tpl-json">{JSON.stringify(assistantAnswer.proposal, null, 2)}</pre>
                    </details>
                    <div className="fx-actions">
                      <button
                        type="button"
                        className="fx-btn primary"
                        onClick={applyProposal}
                        disabled={assistantBusy === "apply"}
                      >
                        {assistantBusy === "apply" ? <Loader2 size={14} className="spin" /> : <Download size={14} />} Áp dụng vào tài khoản của tôi
                      </button>
                      <button type="button" className="fx-btn" onClick={() => setAssistantAnswer(null)}>
                        Bỏ đề xuất
                      </button>
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
          {versions.length ? (
            <div className="n8n-node">
              <h3>Lịch sử phiên bản ({versions.length})</h3>
              {versions.map((v) => (
                <p key={v.version} className="fx-run-meta tpl-check">
                  <span>
                    <strong>v{v.version}</strong> · {v.node_count} node ·{" "}
                    {v.created_at ? new Date(v.created_at).toLocaleString("vi-VN") : ""}
                    {v.version === detail.version ? " · Bản hiện tại" : ""}
                  </span>
                  <span className="fx-actions">
                    {v.version !== detail.version ? (
                      <>
                        <button
                          type="button"
                          className="fx-btn"
                          onClick={() => showDiff(v.version)}
                          disabled={versionBusy === `diff-${v.version}`}
                        >
                          So với bản hiện tại
                        </button>
                        <button
                          type="button"
                          className="fx-btn"
                          onClick={() => restore(v.version)}
                          disabled={versionBusy === `restore-${v.version}`}
                        >
                          Khôi phục
                        </button>
                      </>
                    ) : null}
                  </span>
                </p>
              ))}
              {diffResult ? (
                <div>
                  <p className="fx-run-meta">
                    Khác biệt v{diffResult.from_version} → v{diffResult.to_version}:
                  </p>
                  <p className="fx-run-meta">
                    Node thêm: {diffResult.nodes_added.join(", ") || "không có"} · Node xóa:{" "}
                    {diffResult.nodes_removed.join(", ") || "không có"} · Kết nối{" "}
                    {diffResult.connections_changed ? "có thay đổi" : "không đổi"}
                  </p>
                  {diffResult.nodes_changed.map((change) => (
                    <p key={change.name} className="fx-run-meta">
                      Node sửa: <strong>{change.name}</strong> — {change.changed_fields.join(", ")}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <details>
            <summary>Xem JSON workflow</summary>
            <pre className="tpl-json">{JSON.stringify(detail.workflow_json, null, 2)}</pre>
          </details>
          <div className="fx-actions">
            {detail.review_status === "approved" && !installedByTemplate[detail.id] ? (
              <button
                type="button"
                className="fx-btn primary"
                onClick={() => installOne(detail)}
                disabled={syncBusy === detail.id}
              >
                {syncBusy === detail.id ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Download size={15} />
                )}
                Thêm vào tài khoản
              </button>
            ) : null}
            {installedByTemplate[detail.id] ? (
              <span className="fx-run-meta">
                Đã cài vào tài khoản (v{installedByTemplate[detail.id].installed_version})
                {installedByTemplate[detail.id].update_available
                  ? ` · Có bản mới v${installedByTemplate[detail.id].latest_version} — cập nhật ở mục Đã cài của tôi.`
                  : ""}
              </span>
            ) : null}
            <button
              type="button"
              className="fx-btn primary"
              onClick={() => review("approved")}
              disabled={reviewBusy || detail.review_status === "approved"}
            >
              <Check size={15} /> Duyệt vào thư viện
            </button>
            <button
              type="button"
              className="fx-btn"
              onClick={() => review("rejected")}
              disabled={reviewBusy || detail.review_status === "rejected"}
            >
              <X size={15} /> Loại template này
            </button>
            {detail.review_status !== "pending_review" ? (
              <button
                type="button"
                className="fx-btn"
                onClick={() => review("pending_review")}
                disabled={reviewBusy}
              >
                Đưa về chờ duyệt
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="fx-card">
        {loading ? (
          <p className="fx-run-meta">
            <Loader2 size={14} className="spin" /> Đang tải thư viện…
          </p>
        ) : items.length === 0 ? (
          <p className="fx-run-meta">
            Không có template nào khớp bộ lọc. Nếu thư viện đang trống, hãy nhập template từ mục
            Nguồn template ở tab n8n Platform trước.
          </p>
        ) : (
          <>
            <div className="tpl-grid">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="tpl-card"
                  onClick={() => openDetail(item)}
                >
                  <strong>{item.name}</strong>
                  <span className="fx-run-meta">
                    {item.category} · {item.node_count} node ·{" "}
                    {COMPLEXITY_TEXT[item.complexity] || item.complexity} · v{item.version}
                  </span>
                  <span className="tpl-badges">
                    <span className={`n8n-run-status ${item.review_status === "approved" ? "success" : item.review_status === "rejected" ? "error" : "running"}`}>
                      {REVIEW_TEXT[item.review_status] || item.review_status}
                    </span>
                    {item.compatibility === "needs_community_nodes" ? (
                      <span className="n8n-run-status stopped">Cần community node</span>
                    ) : null}
                    {item.security_flag ? (
                      <span className="n8n-run-status error">Nghi ngờ secret</span>
                    ) : null}
                  </span>
                  {item.credential_types.length ? (
                    <span className="fx-run-meta">
                      Credential: {item.credential_types.slice(0, 3).join(", ")}
                      {item.credential_types.length > 3 ? ` +${item.credential_types.length - 3}` : ""}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
            <div className="fx-actions" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="fx-btn"
                onClick={() => setPage((value) => Math.max(0, value - 1))}
                disabled={page === 0}
              >
                <ChevronLeft size={15} /> Trước
              </button>
              <span className="fx-run-meta">
                Trang {page + 1}/{pages} · {total} template
                {detailLoading ? " · Đang mở chi tiết…" : ""}
              </span>
              <button
                type="button"
                className="fx-btn"
                onClick={() => setPage((value) => Math.min(pages - 1, value + 1))}
                disabled={page >= pages - 1}
              >
                Sau <ChevronRight size={15} />
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
