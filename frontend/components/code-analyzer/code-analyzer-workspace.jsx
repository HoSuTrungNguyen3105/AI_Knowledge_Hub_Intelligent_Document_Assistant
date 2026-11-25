"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { codeAnalyzerService, getCodeError } from "../../services/code-analyzer";
import { providerService } from "../../services/providers";

const STATUS_LABELS = {
  PROCESSING: "Đang xử lý",
  COMPLETED: "Hoàn tất",
  FAILED: "Thất bại",
};

const STATIC_NOTE =
  "Chưa có provider AI khả dụng (chưa cấu hình key hoặc AI gọi lỗi) nên dự án chỉ có dữ liệu tĩnh — cây file và đồ thị imports vẫn đầy đủ, chưa có báo cáo AI.";

/* ------------------------------------------------------------ file tree */
function buildTree(files) {
  const root = { name: "", folders: new Map(), files: [] };
  for (const file of files) {
    const parts = file.file_path.split("/");
    let node = root;
    for (const part of parts.slice(0, -1)) {
      if (!node.folders.has(part)) {
        node.folders.set(part, { name: part, folders: new Map(), files: [] });
      }
      node = node.folders.get(part);
    }
    node.files.push(file);
  }
  return root;
}

function TreeNode({ node, depth, selectedId, onSelect }) {
  const [open, setOpen] = useState(depth < 2);
  const folders = [...node.folders.values()].sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  const files = [...node.files].sort((a, b) =>
    a.file_name.localeCompare(b.file_name),
  );
  return (
    <div>
      {node.name ? (
        <button
          type="button"
          className="ca-tree-folder"
          style={{ paddingLeft: `${depth * 14 + 6}px` }}
          onClick={() => setOpen(!open)}
        >
          {open ? "▾" : "▸"} {node.name}
        </button>
      ) : null}
      {open ? (
        <div>
          {folders.map((folder) => (
            <TreeNode
              key={folder.name}
              node={folder}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              className={`ca-tree-file ${selectedId === file.id ? "active" : ""}`}
              style={{ paddingLeft: `${(depth + 1) * 14 + 6}px` }}
              onClick={() => onSelect(file.id)}
              title={file.file_path}
            >
              {file.file_name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------ graph layout */
const NODE_W = 168;
const NODE_H = 46;
const COL_GAP = 216;
const ROW_GAP = 64;

function layoutGraph(nodes, edges) {
  const ids = new Set(nodes.map((n) => n.id));
  const depth = new Map(nodes.map((n) => [n.id, 0]));
  for (let round = 0; round < nodes.length; round += 1) {
    let changed = false;
    for (const edge of edges) {
      if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
      const next = Math.min(depth.get(edge.source) + 1, 14);
      if (next > depth.get(edge.target)) {
        depth.set(edge.target, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const columns = new Map();
  for (const node of nodes) {
    const d = depth.get(node.id);
    if (!columns.has(d)) columns.set(d, []);
    columns.get(d).push(node);
  }
  const positions = new Map();
  let maxRows = 1;
  for (const [d, list] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
    list
      .sort((a, b) => a.label.localeCompare(b.label))
      .forEach((node, i) => {
        positions.set(node.id, { x: 12 + d * COL_GAP, y: 12 + i * ROW_GAP, node });
      });
    maxRows = Math.max(maxRows, list.length);
  }
  return {
    positions,
    width: columns.size * COL_GAP + 24,
    height: maxRows * ROW_GAP + 24,
  };
}

/* ------------------------------------------------------------ workspace */
export default function CodeAnalyzerWorkspace() {
  const [view, setView] = useState("list");
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [cluster, setCluster] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [providers, setProviders] = useState([]);
  const [providerId, setProviderId] = useState("");
  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState("");
  const fileInput = useRef(null);
  const seeded = useRef(false);

  const loadProjects = useCallback(async () => {
    const list = await codeAnalyzerService.list();
    setProjects(list);
    return list;
  }, []);

  const openProject = useCallback(async (id) => {
    if (!id) {
      setDetail(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await codeAnalyzerService.get(id);
      setDetail(data);
      setSelectedId("");
      setCluster(null);
    } catch (err) {
      setError(getCodeError(err));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let list = await loadProjects();
        if (!list.length && !seeded.current) {
          seeded.current = true;
          try {
            await codeAnalyzerService.seedDemo();
            list = await loadProjects();
          } catch {
            /* production: seeding disabled, show the empty state */
          }
        }
        if (!cancelled) setProjects(list);
      } catch (err) {
        if (!cancelled) setError(getCodeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadProjects]);

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

  const graph = useMemo(() => {
    if (!detail) return { nodes: [], edges: [] };
    const diagram = detail.diagram_data || {};
    if (diagram.mode === "clusters") {
      if (!cluster) return { nodes: diagram.nodes || [], edges: diagram.edges || [] };
      const members = (detail.files || []).filter(
        (f) => f.module_group === cluster,
      );
      const memberIds = new Set(members.map((f) => f.id));
      return {
        nodes: members.map((f) => ({
          id: f.id,
          label: f.file_name,
          group: f.module_group,
          role_tag: f.role_tag,
          kind: "file",
        })),
        edges: (diagram.file_edges || []).filter(
          (e) => memberIds.has(e.source) && memberIds.has(e.target),
        ),
      };
    }
    return { nodes: diagram.nodes || [], edges: diagram.edges || [] };
  }, [detail, cluster]);

  const layout = useMemo(
    () => layoutGraph(graph.nodes, graph.edges),
    [graph],
  );

  function onNodeClick(node) {
    if (node.kind === "cluster") {
      setCluster(node.label);
      return;
    }
    setSelectedId(node.id);
  }

  function enterProject(id) {
    setProjectId(id);
    setView("detail");
    openProject(id);
  }

  function backToList() {
    setView("list");
    setDetail(null);
    loadProjects().catch(() => {});
  }

  async function onUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await codeAnalyzerService.upload(file, providerId, modelId);
      setNotice(
        result.analysis_dispatch === "ai"
          ? `Đã phân tích xong "${result.project.name}" — AI đã viết báo cáo phân tích dựa trên ${result.ai_analyzed} file.`
          : `Đã phân tích xong "${result.project.name}". ${STATIC_NOTE}`,
      );
      await loadProjects();
      enterProject(result.project.id);
    } catch (err) {
      setError(getCodeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRegenerate() {
    if (!detail) return;
    setReportBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await codeAnalyzerService.regenerate(
        detail.id,
        providerId,
        modelId,
      );
      setNotice(
        result.analysis_dispatch === "ai"
          ? "Đã tạo lại báo cáo phân tích bằng AI."
          : STATIC_NOTE,
      );
      await openProject(detail.id);
      await loadProjects();
    } catch (err) {
      setError(getCodeError(err));
    } finally {
      setReportBusy(false);
    }
  }

  function onDownloadReport() {
    if (!detail?.report_markdown) return;
    const blob = new Blob([detail.report_markdown], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(detail.name || "codebase").replace(/[^\w-]+/g, "-")}-bao-cao.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const tree = useMemo(() => buildTree(detail?.files || []), [detail]);
  const visibleFiles = useMemo(() => {
    const all = detail?.files || [];
    if (!query.trim()) return null;
    const q = query.trim().toLowerCase();
    return all.filter((f) => f.file_path.toLowerCase().includes(q));
  }, [detail, query]);

  const project = projects.find((p) => p.id === projectId);

  return (
    <div className="ca-shell">
      <header className="ca-head">
        <div>
          <h2>Codebase Architecture Analyzer</h2>
          <p>
            Upload file ZIP mã nguồn: hệ thống dựng cây thư mục, sơ đồ
            kiến trúc và một báo cáo Markdown tổng — phần nào thuộc file
            nào, mỗi trang/tính năng gồm những file nào.
          </p>
        </div>
        <div className="ca-head-actions">
          <select
            value={providerId}
            onChange={(e) => setProviderId(e.target.value)}
            aria-label="Provider AI"
            title="Provider dùng để viết báo cáo AI (để trống = tự chọn)"
          >
            <option value="">AI: tự chọn</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name || provider.id}
              </option>
            ))}
          </select>
          <select
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            aria-label="Model AI"
            disabled={!providerId || models.length === 0}
          >
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name || model.id}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="wf-btn primary"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
          >
            Upload ZIP
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".zip"
            hidden
            onChange={onUpload}
          />
        </div>
      </header>
      {error ? <p className="wf-error">{error}</p> : null}
      {notice ? <p className="wf-success">{notice}</p> : null}

      {view === "list" ? (
        <section>
          <div className="ca-cards">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className="ca-card"
                onClick={() => enterProject(p.id)}
              >
                <span className="ca-card-top">
                  <strong>{p.name}</strong>
                  {p.is_public_demo ? <span className="wf-chip">Mẫu</span> : null}
                </span>
                <span className="ca-card-meta">
                  {p.stats?.analyzed_files ?? 0} file đã phân tích
                  {p.stats?.primary_language
                    ? ` · ${p.stats.primary_language}`
                    : ""}
                </span>
                <span className="ca-card-row">
                  <span className="wf-badge">
                    {STATUS_LABELS[p.status] || p.status}
                  </span>
                  {p.has_report ? (
                    <span className="ca-chip-ai">Đã có báo cáo AI</span>
                  ) : (
                    <span className="ca-chip-none">Chưa có báo cáo</span>
                  )}
                </span>
                <span className="ca-card-date">
                  Cập nhật {new Date(p.updated_at).toLocaleDateString("vi-VN")}
                </span>
              </button>
            ))}
          </div>
          {projects.length === 0 && !busy ? (
            <p className="ca-empty">
              Chưa có dự án nào. Hãy upload file ZIP mã nguồn để bắt đầu
              phân tích — dự án sẽ hiện ở đây, bấm vào để xem báo cáo.
            </p>
          ) : null}
        </section>
      ) : null}

      {view === "detail" && detail ? (
        <div className="ca-detail">
          <div className="ca-detail-head">
            <button type="button" className="wf-btn" onClick={backToList}>
              ← Tất cả dự án
            </button>
            <h3 className="ca-detail-name">{detail.name}</h3>
            {project ? (
              <span className="wf-badge">
                {STATUS_LABELS[project.status] || project.status}
              </span>
            ) : null}
            <span className="ca-detail-meta">
              {detail.stats?.analyzed_files ?? 0} file đã phân tích /{" "}
              {detail.stats?.total_raw_files ?? 0} file gốc
              {detail.stats?.primary_language
                ? ` · Ngôn ngữ chính: ${detail.stats.primary_language}`
                : ""}
            </span>
          </div>

          <section className="ca-report">
            <div className="ca-report-head">
              <h3>Báo cáo phân tích AI</h3>
              <div className="ca-report-actions">
                <button
                  type="button"
                  className="wf-btn"
                  disabled={reportBusy || busy}
                  onClick={onRegenerate}
                >
                  {reportBusy ? "Đang viết báo cáo..." : "Tạo lại báo cáo"}
                </button>
                {detail.report_markdown ? (
                  <button
                    type="button"
                    className="wf-btn"
                    onClick={onDownloadReport}
                  >
                    Tải file .md
                  </button>
                ) : null}
              </div>
            </div>
            {detail.report_markdown ? (
              <div className="ca-md">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {detail.report_markdown}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="ca-note">
                Dự án này chưa có báo cáo AI (được tạo trước khi có tính
                năng này, hoặc lần upload đó chưa có provider khả dụng).
                Bấm "Tạo lại báo cáo" để AI viết báo cáo tổng: phần nào
                thuộc file nào, mỗi trang/tính năng gồm những file nào.
              </p>
            )}
          </section>

          <h3 className="ca-section-title">Cấu trúc & sơ đồ kiến trúc</h3>
          <div className="ca-panes">
            <aside className="ca-pane ca-explorer">
              <input
                className="ca-search"
                placeholder="Tìm file..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Tìm file"
              />
              {visibleFiles ? (
                <div>
                  {visibleFiles.map((file) => (
                    <button
                      key={file.id}
                      type="button"
                      className={`ca-tree-file ${selectedId === file.id ? "active" : ""}`}
                      onClick={() => setSelectedId(file.id)}
                      title={file.file_path}
                    >
                      {file.file_path}
                    </button>
                  ))}
                  {visibleFiles.length === 0 ? (
                    <p className="ca-note">Không có file nào khớp.</p>
                  ) : null}
                </div>
              ) : (
                <TreeNode
                  node={tree}
                  depth={0}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              )}
            </aside>
            <section className="ca-pane ca-graph">
              {cluster ? (
                <button
                  type="button"
                  className="wf-btn"
                  onClick={() => setCluster(null)}
                >
                  ← Tất cả cụm thư mục
                </button>
              ) : null}
              {detail.diagram_data?.mode === "clusters" && !cluster ? (
                <p className="ca-note">
                  Repo lớn: đồ thị đang gom theo cụm thư mục, bấm vào một
                  cụm để mở rộng.
                </p>
              ) : null}
              <div className="ca-graph-scroll">
                <svg
                  width={layout.width}
                  height={layout.height}
                  className="ca-svg"
                  role="img"
                  aria-label="Sơ đồ kiến trúc"
                >
                  <defs>
                    <marker
                      id="ca-arrow"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="7"
                      markerHeight="7"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
                    </marker>
                  </defs>
                  {graph.edges.map((edge, i) => {
                    const from = layout.positions.get(edge.source);
                    const to = layout.positions.get(edge.target);
                    if (!from || !to) return null;
                    return (
                      <line
                        key={`${edge.source}-${edge.target}-${i}`}
                        x1={from.x + NODE_W}
                        y1={from.y + NODE_H / 2}
                        x2={to.x}
                        y2={to.y + NODE_H / 2}
                        className="ca-edge"
                        markerEnd="url(#ca-arrow)"
                      />
                    );
                  })}
                  {graph.nodes.map((node) => {
                    const pos = layout.positions.get(node.id);
                    if (!pos) return null;
                    const active = selectedId === node.id;
                    return (
                      <g
                        key={node.id}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        className={`ca-node ${active ? "active" : ""}`}
                        onClick={() => onNodeClick(node)}
                      >
                        <rect width={NODE_W} height={NODE_H} rx="8" />
                        <text x="10" y="20" className="ca-node-title">
                          {node.label.length > 22
                            ? `${node.label.slice(0, 21)}…`
                            : node.label}
                        </text>
                        <text x="10" y="36" className="ca-node-sub">
                          {node.kind === "cluster"
                            ? `${node.file_count} file`
                            : node.role_tag || node.group || ""}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
