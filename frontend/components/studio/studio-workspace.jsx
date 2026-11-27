"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, Bot, CheckCircle2, Download, File,
  FilePlus2, Folder, LoaderCircle, Play, Plus, RefreshCw, Save, Trash2,
  Upload, X, XCircle,
} from "lucide-react";
import { agentsService } from "../../services/agents";
import { studioProjectsService } from "../../services/studio-projects";
import { getErrorMessage } from "../../services/api";
import { ConfirmDialog } from "../confirm-dialog";

const timeLabel = (iso) =>
  new Date(iso).toLocaleString("vi-VN", {
    hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
  });

const ACTION_LABEL = { created: "tạo", updated: "sửa", deleted: "xoá" };

// Flat path list -> nested tree nodes for the file explorer.
function buildTree(files) {
  const root = { name: "", path: "", folders: new Map(), files: [] };
  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const key = parts.slice(0, i + 1).join("/");
      if (!node.folders.has(key)) {
        node.folders.set(key, { name: parts[i], path: key, folders: new Map(), files: [] });
      }
      node = node.folders.get(key);
    }
    node.files.push(file);
  }
  return root;
}

function TreeNode({ node, depth, activePath, onOpen }) {
  const folders = [...node.folders.values()].sort((a, b) => a.name.localeCompare(b.name));
  const files = [...node.files].sort((a, b) => a.path.localeCompare(b.path));
  return (
    <>
      {folders.map((folder) => (
        <div key={folder.path}>
          <div className="st-tree-row st-tree-folder" style={{ paddingLeft: 8 + depth * 14 }}>
            <Folder size={14} /> <span>{folder.name}</span>
          </div>
          <TreeNode node={folder} depth={depth + 1} activePath={activePath} onOpen={onOpen} />
        </div>
      ))}
      {files.map((file) => (
        <button
          key={file.path}
          type="button"
          className={`st-tree-row st-tree-file${file.path === activePath ? " active" : ""}`}
          style={{ paddingLeft: 8 + depth * 14 }}
          onClick={() => onOpen(file.path)}
          title={file.path}
        >
          <File size={14} /> <span>{file.path.split("/").pop()}</span>
        </button>
      ))}
    </>
  );
}

// Textarea editor with a synced line-number gutter (Monaco arrives in a
// later upgrade wave; this keeps the editor dependency-free).
function CodeEditor({ value, onChange, onSave }) {
  const areaRef = useRef(null);
  const gutterRef = useRef(null);
  const lines = useMemo(() => value.split("\n").length, [value]);
  return (
    <div className="st-editor">
      <div className="st-gutter" ref={gutterRef} aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <textarea
        ref={areaRef}
        className="st-code"
        value={value}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        onScroll={(event) => {
          if (gutterRef.current) gutterRef.current.scrollTop = event.target.scrollTop;
        }}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            onSave();
          }
          if (event.key === "Tab") {
            event.preventDefault();
            const el = event.target;
            const start = el.selectionStart;
            const next = `${value.slice(0, start)}  ${value.slice(el.selectionEnd)}`;
            onChange(next);
            requestAnimationFrame(() => {
              el.selectionStart = el.selectionEnd = start + 2;
            });
          }
        }}
      />
    </div>
  );
}

export function StudioWorkspace() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [files, setFiles] = useState([]);
  const [agents, setAgents] = useState([]);
  const [runs, setRuns] = useState([]);
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [openTabs, setOpenTabs] = useState([]);
  const [activePath, setActivePath] = useState(null);
  const [contents, setContents] = useState({}); // path -> saved content
  const [draft, setDraft] = useState(""); // editor buffer for activePath
  const [saving, setSaving] = useState(false);

  const [selectedAgents, setSelectedAgents] = useState([]); // ordered ids
  const [instruction, setInstruction] = useState("");
  const [running, setRunning] = useState(false);

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newFilePath, setNewFilePath] = useState(null); // string when the add-file row is open
  const [confirmDelete, setConfirmDelete] = useState(null); // "project" | "file"
  const zipInputRef = useRef(null);

  const project = useMemo(
    () => projects.find((p) => p.id === projectId) || null,
    [projects, projectId],
  );
  const dirty = activePath !== null && contents[activePath] !== undefined && draft !== contents[activePath];
  const tree = useMemo(() => buildTree(files), [files]);
  const lastStepByAgent = useMemo(() => {
    const map = new Map();
    const latest = runs[0];
    if (latest) for (const step of latest.steps) map.set(step.agent_id, step);
    return map;
  }, [runs]);

  const loadProjects = useCallback(async (keepId) => {
    const list = await studioProjectsService.list();
    setProjects(list);
    setProjectId((current) => keepId || current || (list[0] ? list[0].id : null));
    return list;
  }, []);

  const loadProjectData = useCallback(async (id) => {
    if (!id) {
      setFiles([]); setRuns([]); setChanges([]);
      return;
    }
    const [fileList, runList, changeList] = await Promise.all([
      studioProjectsService.listFiles(id),
      studioProjectsService.listRuns(id).catch(() => []),
      studioProjectsService.listChanges(id).catch(() => []),
    ]);
    setFiles(fileList);
    setRuns(runList);
    setChanges(changeList);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [list, agentList] = await Promise.all([
          studioProjectsService.list(),
          agentsService.list().catch(() => []),
        ]);
        if (cancelled) return;
        setProjects(list);
        setAgents(agentList);
        if (list[0]) setProjectId(list[0].id);
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    setOpenTabs([]);
    setActivePath(null);
    setContents({});
    setDraft("");
    setSelectedAgents([]);
    loadProjectData(projectId).catch((err) => setError(getErrorMessage(err)));
  }, [projectId, loadProjectData]);

  const openFile = useCallback(async (path) => {
    if (!projectId) return;
    setOpenTabs((tabs) => (tabs.includes(path) ? tabs : [...tabs, path]));
    setActivePath(path);
    if (contents[path] === undefined) {
      try {
        const file = await studioProjectsService.getFile(projectId, path);
        setContents((map) => ({ ...map, [path]: file.content }));
        setDraft((current) => (activePath === path ? current : file.content));
        if (activePath !== path) setDraft(file.content);
      } catch (err) {
        setError(getErrorMessage(err));
      }
    } else {
      setDraft(contents[path]);
    }
  }, [projectId, contents, activePath]);

  const switchTab = (path) => {
    setActivePath(path);
    setDraft(contents[path] ?? "");
  };

  const closeTab = (path) => {
    setOpenTabs((tabs) => {
      const next = tabs.filter((t) => t !== path);
      if (activePath === path) {
        const fallback = next[next.length - 1] || null;
        setActivePath(fallback);
        setDraft(fallback ? contents[fallback] ?? "" : "");
      }
      return next;
    });
  };

  const saveFile = useCallback(async () => {
    if (!projectId || !activePath || saving) return;
    setSaving(true);
    try {
      const saved = await studioProjectsService.saveFile(projectId, activePath, draft);
      setContents((map) => ({ ...map, [activePath]: saved.content }));
      setNotice(`Đã lưu ${activePath}`);
      await loadProjectData(projectId);
      await loadProjects(projectId);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }, [projectId, activePath, draft, saving, loadProjectData, loadProjects]);

  const createProject = async () => {
    if (!newName.trim()) return;
    try {
      const created = await studioProjectsService.create({ name: newName.trim(), files: [] });
      setCreating(false);
      setNewName("");
      await loadProjects(created.id);
      setProjectId(created.id);
      setNotice("Đã tạo project trống — thêm file hoặc import ZIP để bắt đầu.");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const importZip = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const created = await studioProjectsService.importZip(file, file.name.replace(/\.zip$/i, ""));
      await loadProjects(created.id);
      setProjectId(created.id);
      setNotice(`Đã import ${created.file_count} file vào project "${created.name}".`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const addFile = async () => {
    const path = (newFilePath || "").trim();
    if (!projectId || !path) return;
    try {
      await studioProjectsService.saveFile(projectId, path, "");
      setNewFilePath(null);
      await loadProjectData(projectId);
      await openFile(path);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const deleteProject = async () => {
    if (!projectId) return;
    try {
      await studioProjectsService.remove(projectId);
      setConfirmDelete(null);
      setProjectId(null);
      await loadProjects(null);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const deleteFile = async () => {
    if (!projectId || !activePath) return;
    try {
      await studioProjectsService.removeFile(projectId, activePath);
      setConfirmDelete(null);
      closeTab(activePath);
      setContents((map) => {
        const next = { ...map };
        delete next[activePath];
        return next;
      });
      await loadProjectData(projectId);
      await loadProjects(projectId);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const exportZip = async () => {
    if (!projectId || !project) return;
    try {
      const blob = await studioProjectsService.exportZip(projectId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${project.name}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const toggleAgent = (id) =>
    setSelectedAgents((list) =>
      list.includes(id) ? list.filter((x) => x !== id) : [...list, id],
    );

  const moveAgent = (id, delta) =>
    setSelectedAgents((list) => {
      const index = list.indexOf(id);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= list.length) return list;
      const next = [...list];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  const runAgents = async () => {
    if (!projectId || !selectedAgents.length || !instruction.trim() || running) return;
    if (dirty && !window.confirm("File đang mở có thay đổi chưa lưu — Agent sẽ đọc bản ĐÃ LƯU. Vẫn chạy?")) return;
    setRunning(true);
    setError("");
    try {
      const run = await studioProjectsService.run(projectId, {
        agent_ids: selectedAgents,
        instruction: instruction.trim(),
      });
      const changedPaths = new Set(run.steps.flatMap((s) => s.files_changed));
      await loadProjectData(projectId);
      await loadProjects(projectId);
      if (activePath && changedPaths.has(activePath)) {
        const file = await studioProjectsService.getFile(projectId, activePath);
        setContents((map) => ({ ...map, [activePath]: file.content }));
        setDraft(file.content);
      }
      const failed = run.steps.filter((s) => s.status !== "completed").length;
      setNotice(
        failed
          ? `Lượt chạy xong: ${run.steps.length - failed}/${run.steps.length} Agent áp dụng được thay đổi, ${failed} Agent lỗi.`
          : `Lượt chạy xong: ${run.steps.length} Agent đã làm, file đã cập nhật ngay trên project.`,
      );
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="st-page">
        <p className="st-muted"><LoaderCircle size={16} className="spin" /> Đang tải…</p>
      </div>
    );
  }

  return (
    <div className="st-page">
      <header className="st-head">
        <div>
          <h1>Điều phối Project</h1>
          <p className="st-muted">Nhiều AI cùng làm trên một project có sẵn — sửa trực tiếp trên source, theo thứ tự bạn chỉ định.</p>
        </div>
        <div className="st-head-actions">
          <select
            className="st-select"
            value={projectId || ""}
            onChange={(event) => setProjectId(event.target.value || null)}
          >
            {projects.length === 0 && <option value="">Chưa có project</option>}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.file_count} file)</option>
            ))}
          </select>
          <button type="button" className="button secondary" onClick={() => setCreating((v) => !v)}>
            <Plus size={15} /> Project mới
          </button>
          <button type="button" className="button secondary" onClick={() => zipInputRef.current?.click()}>
            <Upload size={15} /> Import ZIP
          </button>
          <input ref={zipInputRef} type="file" accept=".zip" hidden onChange={importZip} />
          <button type="button" className="button secondary" disabled={!project} onClick={exportZip}>
            <Download size={15} /> Xuất ZIP
          </button>
          <button type="button" className="button danger" disabled={!project} onClick={() => setConfirmDelete("project")}>
            <Trash2 size={15} /> Xoá project
          </button>
        </div>
      </header>

      {creating && (
        <div className="st-inline-form">
          <input
            className="st-input"
            placeholder="Tên project mới"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && createProject()}
          />
          <button type="button" className="button" onClick={createProject}>Tạo</button>
          <button type="button" className="button secondary" onClick={() => setCreating(false)}>Huỷ</button>
        </div>
      )}
      {error && <p className="st-error"><AlertTriangle size={15} /> {error}</p>}
      {notice && <p className="st-notice">{notice}</p>}

      {!project ? (
        <div className="st-empty">
          <p>Chưa có project nào. Bấm <strong>Import ZIP</strong> để đưa project có sẵn vào, hoặc tạo project trống rồi thêm file.</p>
        </div>
      ) : (
        <>
          <section className="st-agent-strip">
            {agents.map((agent) => {
              const step = lastStepByAgent.get(agent.id);
              const order = selectedAgents.indexOf(agent.id);
              return (
                <button
                  key={agent.id}
                  type="button"
                  className={`st-agent-card${order >= 0 ? " picked" : ""}`}
                  onClick={() => toggleAgent(agent.id)}
                  title={`${agent.provider} · ${agent.model}`}
                >
                  <span className="st-agent-top">
                    <Bot size={16} />
                    <span className="st-agent-name">{agent.name}</span>
                    {order >= 0 && <span className="st-order">{order + 1}</span>}
                  </span>
                  <span className="st-agent-model">{agent.provider} · {agent.model}</span>
                  <span className="st-agent-status">
                    {step
                      ? step.status === "completed"
                        ? <><CheckCircle2 size={13} /> Đã sửa {step.files_changed.length} file</>
                        : <><XCircle size={13} /> Lỗi: {step.error_code || "không rõ"}</>
                      : "Chưa chạy"}
                  </span>
                </button>
              );
            })}
            {agents.length === 0 && <p className="st-muted">Chưa có Agent nào — tạo Agent ở Agent Studio trước.</p>}
          </section>

          <div className="st-main">
            <section className="st-code-panel">
              <div className="st-tree-head">
                <strong>{project.name}</strong>
                <span className="st-muted">{project.file_count} file · {Math.max(1, Math.round(project.total_bytes / 1024))} KB</span>
                <button type="button" className="st-icon-btn" title="Thêm file mới" onClick={() => setNewFilePath("")}>
                  <FilePlus2 size={15} />
                </button>
                <button type="button" className="st-icon-btn" title="Tải lại cây file" onClick={() => loadProjectData(projectId)}>
                  <RefreshCw size={15} />
                </button>
              </div>
              {newFilePath !== null && (
                <div className="st-inline-form">
                  <input
                    className="st-input"
                    placeholder="đường/dẫn/file.jsx"
                    value={newFilePath}
                    onChange={(event) => setNewFilePath(event.target.value)}
                    onKeyDown={(event) => event.key === "Enter" && addFile()}
                  />
                  <button type="button" className="button" onClick={addFile}>Tạo file</button>
                  <button type="button" className="button secondary" onClick={() => setNewFilePath(null)}>Huỷ</button>
                </div>
              )}
              <div className="st-workbench">
                <aside className="st-tree">
                  <TreeNode node={tree} depth={0} activePath={activePath} onOpen={openFile} />
                  {files.length === 0 && <p className="st-muted st-tree-empty">Project chưa có file nào.</p>}
                </aside>
                <div className="st-editor-wrap">
                  <div className="st-tabs">
                    {openTabs.map((path) => (
                      <span key={path} className={`st-tab${path === activePath ? " active" : ""}`}>
                        <button type="button" onClick={() => switchTab(path)}>
                          {path.split("/").pop()}{path === activePath && dirty ? " •" : ""}
                        </button>
                        <button type="button" className="st-tab-close" onClick={() => closeTab(path)} aria-label="Đóng tab">
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                    {activePath && (
                      <span className="st-editor-actions">
                        <button type="button" className="button secondary" onClick={saveFile} disabled={!dirty || saving}>
                          {saving ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />} Lưu (Ctrl+S)
                        </button>
                        <button type="button" className="button danger" onClick={() => setConfirmDelete("file")}>
                          <Trash2 size={14} /> Xoá file
                        </button>
                      </span>
                    )}
                  </div>
                  {activePath ? (
                    <CodeEditor value={draft} onChange={setDraft} onSave={saveFile} />
                  ) : (
                    <div className="st-empty">
                      <p>Chọn một file ở cây bên trái để xem và sửa, hoặc bấm <FilePlus2 size={14} /> để tạo file mới.</p>
                    </div>
                  )}
                </div>
              </div>
            </section>

            <aside className="st-side">
              <section className="st-card">
                <h2>Giao task cho AI</h2>
                <p className="st-muted">Thứ tự chạy = thứ tự chọn (số trên thẻ Agent). Agent sau đọc bản Agent trước vừa sửa.</p>
                <div className="st-picked">
                  {selectedAgents.map((id, index) => {
                    const agent = agents.find((a) => a.id === id);
                    if (!agent) return null;
                    return (
                      <span key={id} className="st-picked-row">
                        <span className="st-order">{index + 1}</span> {agent.name}
                        <button type="button" className="st-icon-btn" onClick={() => moveAgent(id, -1)} aria-label="Lên"><ArrowUp size={13} /></button>
                        <button type="button" className="st-icon-btn" onClick={() => moveAgent(id, 1)} aria-label="Xuống"><ArrowDown size={13} /></button>
                        <button type="button" className="st-icon-btn" onClick={() => toggleAgent(id)} aria-label="Bỏ chọn"><X size={13} /></button>
                      </span>
                    );
                  })}
                  {selectedAgents.length === 0 && <p className="st-muted">Bấm vào thẻ Agent ở trên để chọn người làm.</p>}
                </div>
                <textarea
                  className="st-input st-task"
                  rows={4}
                  placeholder="Ví dụ: Thêm trang Giỏ hàng dùng cartService hiện có, giữ nguyên style của Home…"
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                />
                <button
                  type="button"
                  className="button st-run"
                  disabled={running || !selectedAgents.length || !instruction.trim()}
                  onClick={runAgents}
                >
                  {running ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />}
                  {running ? "Đang chạy…" : "Chạy điều phối"}
                </button>
                {running && <p className="st-muted">Các Agent đang làm lần lượt — trang sẽ cập nhật khi xong cả lượt.</p>}
              </section>

              <section className="st-card">
                <h2>Lượt chạy gần đây</h2>
                {runs.length === 0 && <p className="st-muted">Chưa có lượt chạy nào.</p>}
                {runs.slice(0, 5).map((run) => (
                  <div key={run.id} className="st-run-item">
                    <p className="st-run-title">{run.instruction}</p>
                    <p className="st-muted">{timeLabel(run.created_at)} · {run.total_input_tokens + run.total_output_tokens} token</p>
                    {run.steps.map((step) => (
                      <p key={step.agent_id} className="st-step">
                        {step.status === "completed"
                          ? <CheckCircle2 size={13} className="ok" />
                          : <XCircle size={13} className="bad" />}
                        <strong>{step.agent_name}</strong>
                        <span>{step.status === "completed" ? `sửa ${step.files_changed.length} file` : `lỗi ${step.error_code || ""}`}</span>
                        {step.summary && <span className="st-step-summary">{step.summary}</span>}
                      </p>
                    ))}
                  </div>
                ))}
              </section>

              <section className="st-card">
                <h2>Nhật ký thay đổi</h2>
                {changes.length === 0 && <p className="st-muted">Chưa có thay đổi nào.</p>}
                {changes.slice(0, 30).map((change) => (
                  <p key={change.id} className="st-change">
                    <strong>{change.source === "agent" ? change.agent_name || "Agent" : "Bạn"}</strong>
                    {" "}{ACTION_LABEL[change.action] || change.action} <code>{change.path}</code>
                    <span className="st-muted"> · {timeLabel(change.created_at)}</span>
                  </p>
                ))}
              </section>
            </aside>
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title={confirmDelete === "file" ? "Xoá file này?" : "Xoá project này?"}
        busy={false}
        onClose={() => setConfirmDelete(null)}
        onConfirm={confirmDelete === "file" ? deleteFile : deleteProject}
        confirmLabel="Xoá"
      >
        {confirmDelete === "file"
          ? <>File <strong>{activePath}</strong> sẽ bị xoá khỏi project. Hành động này không hoàn tác được.</>
          : <>Project <strong>{project?.name}</strong> cùng toàn bộ file, lượt chạy và nhật ký sẽ bị xoá. Hành động này không hoàn tác được.</>}
      </ConfirmDialog>
    </div>
  );
}
