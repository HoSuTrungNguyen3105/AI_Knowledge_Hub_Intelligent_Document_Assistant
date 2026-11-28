"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { codeAnalyzerService, getCodeError } from "../../services/code-analyzer";
import { providerService } from "../../services/providers";
import { ModelSelect } from "../model-select";
import ArchitectureMap from "./architecture-map";

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

/* ------------------------------------------------------------ workspace */
export default function CodeAnalyzerWorkspace() {
  const [view, setView] = useState("list");
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [detail, setDetail] = useState(null);
  const [archMap, setArchMap] = useState(null);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [dataQuery, setDataQuery] = useState("");
  const [dataSort, setDataSort] = useState("imported");
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
      try {
        setArchMap(await codeAnalyzerService.architecture(id));
      } catch {
        /* the map is an extra view; the detail below still works */
        setArchMap(null);
      }
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

  function enterProject(id) {
    setProjectId(id);
    setView("detail");
    openProject(id);
  }

  function backToList() {
    setView("list");
    setDetail(null);
    setArchMap(null);
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

  function onDownloadCsv() {
    if (!detail) return;
    const esc = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const header = [
      "file_path", "language", "role_tag", "module_group",
      "imports", "imported_by", "ai_summary",
    ];
    const lines = dataRows.map((f) =>
      [
        f.file_path,
        f.language,
        f.role_tag,
        f.module_group,
        (f.imports || []).map((i) => i.target_file).join("; "),
        (f.imported_by || []).join("; "),
        f.ai_summary || "",
      ]
        .map(esc)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(detail.name || "codebase").replace(/[^\w-]+/g, "-")}-du-lieu.csv`;
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

  const dataRows = useMemo(() => {
    const all = [...(detail?.files || [])];
    const q = dataQuery.trim().toLowerCase();
    const filtered = q
      ? all.filter((f) =>
          [f.file_path, f.language, f.role_tag, f.module_group]
            .join(" ")
            .toLowerCase()
            .includes(q),
        )
      : all;
    if (dataSort === "path") {
      filtered.sort((a, b) => a.file_path.localeCompare(b.file_path));
    } else if (dataSort === "imports") {
      filtered.sort(
        (a, b) => (b.import_count || 0) - (a.import_count || 0),
      );
    } else {
      filtered.sort(
        (a, b) => (b.imported_by_count || 0) - (a.imported_by_count || 0),
      );
    }
    return filtered;
  }, [detail, dataQuery, dataSort]);

  const project = projects.find((p) => p.id === projectId);
  const selectedFile = (detail?.files || []).find((f) => f.id === selectedId);

  return (
    <div className="ca-shell">
      <header className="ca-head">
        <div>
          <h2>Codebase Architecture Analyzer</h2>
          <p>
            Upload file ZIP mã nguồn: hệ thống dựng bản đồ kiến trúc theo
            tầng (đếm file theo ngôn ngữ, sơ đồ các lớp, đường đọc code),
            cây thư mục, bảng dữ liệu và một báo cáo Markdown tổng.
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
          <ModelSelect
            models={models}
            value={modelId}
            onChange={setModelId}
            ariaLabel="Model AI"
            disabled={!providerId || models.length === 0}
          />
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

      {view === "data" && detail ? (
        <div className="ca-detail">
          <div className="ca-detail-head">
            <button
              type="button"
              className="wf-btn"
              onClick={() => setView("detail")}
            >
              ← Về chi tiết dự án
            </button>
            <h3 className="ca-detail-name">Dữ liệu dự án — {detail.name}</h3>
            <span className="ca-detail-meta">
              {detail.files?.length ?? 0} file ·{" "}
              {(detail.files || []).reduce(
                (sum, f) => sum + (f.import_count || 0),
                0,
              )}{" "}
              quan hệ import
            </span>
            <button type="button" className="wf-btn" onClick={onDownloadCsv}>
              Tải CSV
            </button>
          </div>
          <div className="ca-data-tools">
            <input
              className="ca-search"
              placeholder="Lọc theo đường dẫn, ngôn ngữ, vai trò, nhóm..."
              value={dataQuery}
              onChange={(e) => setDataQuery(e.target.value)}
              aria-label="Lọc bảng dữ liệu"
            />
            <select
              value={dataSort}
              onChange={(e) => setDataSort(e.target.value)}
              aria-label="Sắp xếp bảng dữ liệu"
            >
              <option value="imported">Được import nhiều nhất</option>
              <option value="imports">Import nhiều nhất</option>
              <option value="path">Đường dẫn A–Z</option>
            </select>
            <span className="ca-detail-meta">
              Hiện {dataRows.length} / {detail.files?.length ?? 0} file — bấm
              vào một dòng để xem file đó trên sơ đồ.
            </span>
          </div>
          <div className="ca-table-wrap">
            <table className="ca-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Đường dẫn file</th>
                  <th>Ngôn ngữ</th>
                  <th>Vai trò</th>
                  <th>Nhóm</th>
                  <th>Import các file</th>
                  <th>Được import bởi</th>
                  <th>Tóm tắt AI</th>
                </tr>
              </thead>
              <tbody>
                {dataRows.map((f, index) => (
                  <tr
                    key={f.id}
                    onClick={() => {
                      setSelectedId(f.id);
                      setView("detail");
                    }}
                  >
                    <td>{index + 1}</td>
                    <td className="ca-path">{f.file_path}</td>
                    <td>{f.language || "—"}</td>
                    <td>{f.role_tag || "—"}</td>
                    <td>{f.module_group || "—"}</td>
                    <td>
                      {(f.imports || []).length ? (
                        <div className="ca-cell-list">
                          {(f.imports || []).map((imp, i) => (
                            <div key={i}>{imp.target_file}</div>
                          ))}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {(f.imported_by || []).length ? (
                        <div className="ca-cell-list">
                          {(f.imported_by || []).map((path, i) => (
                            <div key={i}>{path}</div>
                          ))}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="ca-summary">{f.ai_summary || "—"}</td>
                  </tr>
                ))}
                {dataRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="ca-note">
                      Không có file nào khớp bộ lọc.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
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
            <button
              type="button"
              className="wf-btn"
              onClick={() => setView("data")}
            >
              Bảng dữ liệu đầy đủ
            </button>
          </div>

          {archMap ? <ArchitectureMap map={archMap} /> : null}

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

          <h3 className="ca-section-title">Cây thư mục & chi tiết file</h3>
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
            <section className="ca-pane ca-file-info">
              {selectedFile ? (
                <div>
                  <p className="ca-file-path">{selectedFile.file_path}</p>
                  <div className="ca-file-tags">
                    {selectedFile.language ? (
                      <span className="wf-chip">{selectedFile.language}</span>
                    ) : null}
                    {selectedFile.role_tag ? (
                      <span className="wf-chip">{selectedFile.role_tag}</span>
                    ) : null}
                    {selectedFile.module_group ? (
                      <span className="wf-chip">{selectedFile.module_group}</span>
                    ) : null}
                  </div>
                  {selectedFile.ai_summary ? (
                    <p className="ca-file-summary">{selectedFile.ai_summary}</p>
                  ) : (
                    <p className="ca-note">
                      File này chưa có tóm tắt AI.
                    </p>
                  )}
                  <h4 className="ca-file-h">Import các file</h4>
                  {(selectedFile.imports || []).length ? (
                    <ul className="ca-file-list">
                      {(selectedFile.imports || []).map((imp, i) => (
                        <li key={i}>{imp.target_file}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="ca-note">Không import file nào trong dự án.</p>
                  )}
                  <h4 className="ca-file-h">Được import bởi</h4>
                  {(selectedFile.imported_by || []).length ? (
                    <ul className="ca-file-list">
                      {(selectedFile.imported_by || []).map((path, i) => (
                        <li key={i}>{path}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="ca-note">Chưa có file nào import file này.</p>
                  )}
                </div>
              ) : (
                <p className="ca-note">
                  Chọn một file ở cây bên trái để xem vai trò, tóm tắt AI và
                  các quan hệ import của file đó. Sơ đồ tổng thể nằm ở bản
                  đồ kiến trúc phía trên; bảng dữ liệu đầy đủ có nút riêng
                  ở đầu trang.
                </p>
              )}
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}
