"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import {
  getWorkflowTemplatesError,
  workflowTemplatesService,
} from "../../services/workflow-templates";

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
          Template được duyệt mới dùng để đồng bộ vào tài khoản (Phase 3). Muốn nhập thêm template,
          dùng mục Nguồn template ở tab n8n Platform.
        </p>
        {error ? (
          <p className="fx-alert" role="alert">
            {error}
          </p>
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
          <details>
            <summary>Xem JSON workflow</summary>
            <pre className="tpl-json">{JSON.stringify(detail.workflow_json, null, 2)}</pre>
          </details>
          <div className="fx-actions">
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
