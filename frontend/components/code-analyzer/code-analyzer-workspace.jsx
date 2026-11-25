"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { codeAnalyzerService, getCodeError } from "../../services/code-analyzer";

const STATUS_LABELS = {
  PROCESSING: "Đang xử lý",
  COMPLETED: "Hoàn tất",
  FAILED: "Thất bại",
};

const DISPATCH_NOTES = {
  sent: "Đã gửi các batch sang n8n — AI Insight sẽ được cập nhật khi workflow chạy xong.",
  skipped:
    "Chưa cấu hình webhook n8n nên dự án hoàn tất bằng phân tích tĩnh (chưa có AI summary).",
  failed:
    "Không gửi được sang n8n (webhook không phản hồi) — dự án vẫn hoàn tất bằng phân tích tĩnh.",
};

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
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail] = useState(null);
  const [fileDetail, setFileDetail] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [cluster, setCluster] = useState(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef(null);
  const seeded = useRef(false);

  const loadProjects = useCallback(async (keepSelection) => {
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
      setFileDetail(null);
      setSelectedEdge(null);
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
        if (!cancelled && list.length) {
          setProjectId(list[0].id);
          await openProject(list[0].id);
        }
      } catch (err) {
        if (!cancelled) setError(getCodeError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadProjects, openProject]);

  const filesById = useMemo(() => {
    const map = new Map();
    for (const file of detail?.files || []) map.set(file.id, file);
    return map;
  }, [detail]);

  const filesByPath = useMemo(() => {
    const map = new Map();
    for (const file of detail?.files || []) map.set(file.file_path, file);
    return map;
  }, [detail]);

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

  async function selectFile(id) {
    if (!detail) return;
    setSelectedEdge(null);
    try {
      setFileDetail(await codeAnalyzerService.getFile(detail.id, id));
    } catch (err) {
      setError(getCodeError(err));
    }
  }

  function onNodeClick(node) {
    if (node.kind === "cluster") {
      setCluster(node.label);
      setFileDetail(null);
      setSelectedEdge(null);
      return;
    }
    selectFile(node.id);
  }

  async function onUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await codeAnalyzerService.upload(file);
      setNotice(
        `Đã phân tích xong "${result.project.name}". ${
          DISPATCH_NOTES[result.analysis_dispatch] || ""
        }`,
      );
      await loadProjects();
      setProjectId(result.project.id);
      await openProject(result.project.id);
    } catch (err) {
      setError(getCodeError(err));
    } finally {
      setBusy(false);
    }
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
            Upload file ZIP mã nguồn để xem cây thư mục, sơ đồ kiến trúc và
            phân tích AI cho từng file.
          </p>
        </div>
        <div className="ca-head-actions">
          <select
            value={projectId}
            onChange={(e) => {
              setProjectId(e.target.value);
              openProject(e.target.value);
            }}
            aria-label="Chọn dự án"
          >
            <option value="">— Chọn dự án —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.is_public_demo ? " (mẫu)" : ""}
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
      {project ? (
        <p className="ca-stats">
          <span className="wf-badge">{STATUS_LABELS[project.status] || project.status}</span>
          {project.stats?.analyzed_files ?? 0} file đã phân tích /{" "}
          {project.stats?.total_raw_files ?? 0} file gốc
          {project.stats?.primary_language
            ? ` · Ngôn ngữ chính: ${project.stats.primary_language}`
            : ""}
          {detail?.diagram_data?.mode === "clusters" && !cluster
            ? " · Repo lớn: đồ thị đang gom theo cụm thư mục, bấm vào một cụm để mở rộng"
            : ""}
        </p>
      ) : null}
      {!detail && !busy ? (
        <p className="ca-empty">
          Chưa có dự án nào. Hãy upload file ZIP mã nguồn để bắt đầu phân tích.
        </p>
      ) : null}
      {detail ? (
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
                    className={`ca-tree-file ${fileDetail?.id === file.id ? "active" : ""}`}
                    onClick={() => selectFile(file.id)}
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
                selectedId={fileDetail?.id || ""}
                onSelect={selectFile}
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
                  const active =
                    selectedEdge &&
                    selectedEdge.source === edge.source &&
                    selectedEdge.target === edge.target;
                  return (
                    <line
                      key={`${edge.source}-${edge.target}-${i}`}
                      x1={from.x + NODE_W}
                      y1={from.y + NODE_H / 2}
                      x2={to.x}
                      y2={to.y + NODE_H / 2}
                      className={`ca-edge ${active ? "active" : ""}`}
                      markerEnd="url(#ca-arrow)"
                      onClick={() => {
                        setSelectedEdge(edge);
                        setFileDetail(null);
                      }}
                    />
                  );
                })}
                {graph.nodes.map((node) => {
                  const pos = layout.positions.get(node.id);
                  if (!pos) return null;
                  const active = fileDetail?.id === node.id;
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
          <aside className="ca-pane ca-insight">
            <h3>AI Code Insight</h3>
            {selectedEdge ? (
              <div>
                <p className="ca-insight-path">
                  {filesById.get(selectedEdge.source)?.file_path ||
                    selectedEdge.source}
                  {" → "}
                  {filesById.get(selectedEdge.target)?.file_path ||
                    selectedEdge.target}
                </p>
                <p>
                  {selectedEdge.label ||
                    "Chưa có nhãn quan hệ cho liên kết này — nhãn do AI điền sau khi workflow n8n phân tích xong."}
                </p>
              </div>
            ) : fileDetail ? (
              <div>
                <p className="ca-insight-path">{fileDetail.file_path}</p>
                <p className="ca-tags">
                  {fileDetail.role_tag ? (
                    <span className="wf-chip">{fileDetail.role_tag}</span>
                  ) : null}
                  {fileDetail.language ? (
                    <span className="wf-chip">{fileDetail.language}</span>
                  ) : null}
                </p>
                <h4>Tóm tắt chức năng</h4>
                <p>
                  {fileDetail.ai_summary ||
                    "Chưa có phân tích AI cho file này. Khi webhook n8n được cấu hình, summary sẽ tự động xuất hiện sau khi upload."}
                </p>
                <h4>File này import ({fileDetail.imports.length})</h4>
                {fileDetail.imports.length ? (
                  <ul className="ca-link-list">
                    {fileDetail.imports.map((imp, i) => (
                      <li key={i}>
                        <button
                          type="button"
                          className="ca-link"
                          disabled={!imp.target_id}
                          onClick={() => imp.target_id && selectFile(imp.target_id)}
                        >
                          {imp.target_file}
                        </button>
                        {imp.relation_label ? (
                          <span> — {imp.relation_label}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="ca-note">Không import file nào trong repo.</p>
                )}
                <h4>Được import bởi ({fileDetail.imported_by.length})</h4>
                {fileDetail.imported_by.length ? (
                  <ul className="ca-link-list">
                    {fileDetail.imported_by.map((path) => (
                      <li key={path}>
                        <button
                          type="button"
                          className="ca-link"
                          disabled={!filesByPath.get(path)}
                          onClick={() =>
                            filesByPath.get(path) &&
                            selectFile(filesByPath.get(path).id)
                          }
                        >
                          {path}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="ca-note">Chưa có file nào import file này.</p>
                )}
              </div>
            ) : (
              <p className="ca-note">
                Bấm vào một file trên sơ đồ hoặc trong cây thư mục để xem tóm
                tắt AI, các file phụ thuộc và mức độ ảnh hưởng. Bấm vào một
                đường nối để xem quan hệ giữa hai file.
              </p>
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
