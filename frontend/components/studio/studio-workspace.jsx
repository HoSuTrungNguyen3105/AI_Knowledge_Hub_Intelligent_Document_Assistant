"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, ArrowDown, ArrowUp, Bot, CheckCircle2, Download, File,
  FilePlus2, Folder, FolderOpen, FolderSync, HardDrive, Link2, LoaderCircle,
  Play, Plus, RefreshCw, Save, Trash2, Unlink, Upload, X, XCircle,
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

// --- Local folder linking (File System Access API) ----------------------
// The project lives on the server so Agents can edit it; linking a local
// folder lets the page write the current files back into that folder on
// the user's own machine (Chrome/Edge on desktop). Directory handles are
// kept in IndexedDB per project; the browser still owns the permission,
// so a write only happens automatically while permission is "granted".
const SKIP_DIRS = new Set(["node_modules", ".git", "__MACOSX", ".next", ".venv", "__pycache__"]);
const MAX_IMPORT_FILES = 200;
const MAX_IMPORT_BYTES = 5 * 1024 * 1024;

function idbOpen() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("studio-local-links", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("handles");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idbSet(key, value) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("handles", "readwrite");
    tx.objectStore("handles").put(value, key);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function idbGet(key) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const request = db.transaction("handles").objectStore("handles").get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

async function idbDel(key) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("handles", "readwrite");
    tx.objectStore("handles").delete(key);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

// Read every editable text file under a directory handle (or a
// webkitdirectory File list) into [{path, content}], skipping junk
// directories and binaries, enforcing the backend's project limits.
async function collectFolderFiles(entries) {
  const files = [];
  let total = 0;
  for (const { path, file } of entries) {
    if (files.length >= MAX_IMPORT_FILES) break;
    if (file.size > 1024 * 1024) continue;
    const content = await file.text();
    if (content.includes("\u0000")) continue; // binary
    total += new Blob([content]).size;
    if (total > MAX_IMPORT_BYTES) {
      throw new Error(`Thư mục vượt giới hạn 5 MB (${files.length} file đã đọc). Bỏ bớt thư mục nặng (node_modules, ảnh…) rồi thử lại.`);
    }
    files.push({ path, content });
  }
  return files;
}

async function walkHandle(handle, prefix, out) {
  for await (const entry of handle.values()) {
    if (entry.kind === "directory") {
      if (SKIP_DIRS.has(entry.name)) continue;
      await walkHandle(entry, prefix ? `${prefix}/${entry.name}` : entry.name, out);
    } else {
      out.push({ path: prefix ? `${prefix}/${entry.name}` : entry.name, file: await entry.getFile() });
    }
  }
  return out;
}

async function writeFileToHandle(rootHandle, path, content) {
  const parts = path.split("/");
  let dir = rootHandle;
  for (let i = 0; i < parts.length - 1; i += 1) {
    dir = await dir.getDirectoryHandle(parts[i], { create: true });
  }
  const fileHandle = await dir.getFileHandle(parts[parts.length - 1], { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(content);
  await writable.close();
}

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
  const folderInputRef = useRef(null);
  const handleRef = useRef(null); // FileSystemDirectoryHandle, per project
  const [folderName, setFolderName] = useState("");
  const [folderGranted, setFolderGranted] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const canLinkFolder = typeof window !== "undefined" && !!window.showDirectoryPicker;

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
    // Clear the previous project's data immediately — otherwise its
    // file tree shows briefly under the new project's title while the
    // fresh data is still loading (seen in the 2026-11-27 live test).
    setFiles([]);
    setRuns([]);
    setChanges([]);
    loadProjectData(projectId).catch((err) => setError(getErrorMessage(err)));
  }, [projectId, loadProjectData]);

  // Restore this project's linked local folder (handle kept in
  // IndexedDB; the browser may still require a fresh permission grant).
  useEffect(() => {
    let cancelled = false;
    handleRef.current = null;
    setFolderName("");
    setFolderGranted(false);
    if (!projectId || !window.showDirectoryPicker) return undefined;
    (async () => {
      try {
        const handle = await idbGet(projectId);
        if (cancelled || !handle) return;
        handleRef.current = handle;
        setFolderName(handle.name || "");
        const permission = handle.queryPermission
          ? await handle.queryPermission({ mode: "readwrite" })
          : "granted";
        if (!cancelled) setFolderGranted(permission === "granted");
      } catch { /* linking is optional */ }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  const writeProjectToFolder = useCallback(async (id) => {
    const handle = handleRef.current;
    if (!handle || !id) return 0;
    try {
      const permission = handle.queryPermission
        ? await handle.queryPermission({ mode: "readwrite" })
        : "granted";
      if (permission !== "granted") return 0;
      const metas = await studioProjectsService.listFiles(id);
      let written = 0;
      for (const meta of metas) {
        const file = await studioProjectsService.getFile(id, meta.path);
        await writeFileToHandle(handle, meta.path, file.content);
        written += 1;
      }
      return written;
    } catch {
      return 0;
    }
  }, []);

  const linkHandle = useCallback(async (forProjectId, handle) => {
    handleRef.current = handle;
    setFolderName(handle.name || "");
    try { await idbSet(forProjectId, handle); } catch { /* non-fatal */ }
    const permission = handle.queryPermission
      ? await handle.queryPermission({ mode: "readwrite" }).catch(() => "prompt")
      : "granted";
    setFolderGranted(permission === "granted");
  }, []);

  const openFile = useCallback(async (path) => {
    if (!projectId) return;
    // Re-clicking the open file must not discard unsaved edits.
    if (path === activePath && contents[path] !== undefined && draft !== contents[path]) return;
    setOpenTabs((tabs) => (tabs.includes(path) ? tabs : [...tabs, path]));
    setActivePath(path);
    try {
      // Always read fresh from the server: the cache goes stale when an
      // Agent (or a folder sync) rewrites a file that is not open.
      const file = await studioProjectsService.getFile(projectId, path);
      setContents((map) => ({ ...map, [path]: file.content }));
      setDraft(file.content);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [projectId, activePath, contents, draft]);

  const switchTab = (path) => {
    setActivePath(path);
    if (contents[path] !== undefined) setDraft(contents[path]);
    else openFile(path);
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
      let message = `Đã lưu ${activePath}`;
      if (handleRef.current) {
        const permission = handleRef.current.queryPermission
          ? await handleRef.current.queryPermission({ mode: "readwrite" }).catch(() => "denied")
          : "granted";
        if (permission === "granted") {
          await writeFileToHandle(handleRef.current, activePath, saved.content).catch(() => {});
          message += " và ghi về thư mục máy.";
        }
      }
      setNotice(message);
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

  const importFolder = async () => {
    if (!window.showDirectoryPicker) {
      folderInputRef.current?.click();
      return;
    }
    try {
      const handle = await window.showDirectoryPicker();
      const entries = await walkHandle(handle, "", []);
      const files = await collectFolderFiles(entries);
      if (!files.length) {
        setError("Thư mục không có file văn bản nào đọc được (đã bỏ qua node_modules/.git và file nhị phân).");
        return;
      }
      const created = await studioProjectsService.create({
        name: handle.name || "Project từ thư mục",
        files,
      });
      await linkHandle(created.id, handle);
      await loadProjects(created.id);
      setProjectId(created.id);
      setNotice(`Đã import ${files.length} file từ thư mục "${handle.name}" và đã liên kết — sau mỗi lượt chạy AI và mỗi lần bạn lưu, bản mới tự ghi về thư mục này.`);
    } catch (err) {
      if (err?.name !== "AbortError") setError(err?.message || getErrorMessage(err));
    }
  };

  const importFolderFromInput = async (event) => {
    const picked = [...(event.target.files || [])];
    event.target.value = "";
    if (!picked.length) return;
    const entries = [];
    for (const file of picked) {
      const rel = (file.webkitRelativePath || file.name).split("/").slice(1).join("/");
      if (!rel) continue;
      if (rel.split("/").some((seg) => SKIP_DIRS.has(seg))) continue;
      entries.push({ path: rel, file });
    }
    try {
      const files = await collectFolderFiles(entries);
      if (!files.length) {
        setError("Thư mục không có file văn bản nào đọc được.");
        return;
      }
      const rootName = (picked[0].webkitRelativePath || "project").split("/")[0];
      const created = await studioProjectsService.create({ name: rootName, files });
      await loadProjects(created.id);
      setProjectId(created.id);
      setNotice(`Đã import ${files.length} file từ thư mục "${rootName}". Trình duyệt này không hỗ trợ ghi ngược về thư mục máy — mở bằng Chrome/Edge để liên kết ghi tự động.`);
    } catch (err) {
      setError(err?.message || getErrorMessage(err));
    }
  };

  const linkFolder = async () => {
    if (!projectId || !window.showDirectoryPicker) return;
    try {
      const handle = await window.showDirectoryPicker();
      const permission = await handle.requestPermission({ mode: "readwrite" });
      await linkHandle(projectId, handle);
      if (permission === "granted") {
        const written = await writeProjectToFolder(projectId);
        setNotice(`Đã liên kết thư mục "${handle.name}" và ghi ${written} file hiện tại về đó. Từ giờ AI sửa xong là thư mục này cập nhật theo.`);
      } else {
        setNotice(`Đã nhớ thư mục "${handle.name}" nhưng chưa được cấp quyền ghi.`);
      }
    } catch (err) {
      if (err?.name !== "AbortError") setError(getErrorMessage(err));
    }
  };

  const unlinkFolder = async () => {
    if (projectId) await idbDel(projectId).catch(() => {});
    handleRef.current = null;
    setFolderName("");
    setFolderGranted(false);
    setNotice("Đã huỷ liên kết thư mục máy cho project này.");
  };

  const syncDown = async () => {
    if (!projectId || !handleRef.current) return;
    setSyncing(true);
    try {
      const handle = handleRef.current;
      if (handle.queryPermission && (await handle.queryPermission({ mode: "readwrite" })) !== "granted") {
        await handle.requestPermission({ mode: "readwrite" });
      }
      const written = await writeProjectToFolder(projectId);
      if (written) {
        setFolderGranted(true);
        setNotice(`Đã ghi ${written} file về thư mục "${folderName}".`);
      } else {
        setNotice("Chưa ghi được file nào — kiểm tra quyền ghi của thư mục đã liên kết.");
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSyncing(false);
    }
  };

  const syncUp = async () => {
    const handle = handleRef.current;
    if (!handle || !projectId) return;
    setSyncing(true);
    try {
      if (handle.queryPermission && (await handle.queryPermission({ mode: "read" })) !== "granted") {
        await handle.requestPermission({ mode: "read" });
      }
      const entries = await walkHandle(handle, "", []);
      const files = await collectFolderFiles(entries);
      let count = 0;
      for (const file of files) {
        await studioProjectsService.saveFile(projectId, file.path, file.content);
        count += 1;
      }
      await loadProjectData(projectId);
      await loadProjects(projectId);
      if (activePath && contents[activePath] !== undefined) {
        const fresh = await studioProjectsService.getFile(projectId, activePath);
        setContents((map) => ({ ...map, [activePath]: fresh.content }));
        setDraft(fresh.content);
      }
      setNotice(`Đã đọc ${count} file từ thư mục "${folderName}" lên project.`);
    } catch (err) {
      setError(err?.message || getErrorMessage(err));
    } finally {
      setSyncing(false);
    }
  };

  const addFile = async () => {
    const path = (newFilePath || "").trim();
    if (!projectId || !path) return;
    try {
      await studioProjectsService.saveFile(projectId, path, "");
      setNewFilePath(null);
      await loadProjectData(projectId);
      await loadProjects(projectId);
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
      if (changedPaths.size) {
        // Invalidate cached contents of everything the Agents touched,
        // so a later tab switch never shows the pre-run version.
        setContents((map) => {
          const next = { ...map };
          for (const p of changedPaths) delete next[p];
          return next;
        });
      }
      if (activePath && changedPaths.has(activePath)) {
        const file = await studioProjectsService.getFile(projectId, activePath);
        setContents((map) => ({ ...map, [activePath]: file.content }));
        setDraft(file.content);
      }
      const failed = run.steps.filter((s) => s.status !== "completed").length;
      let message = failed
        ? `Lượt chạy xong: ${run.steps.length - failed}/${run.steps.length} Agent áp dụng được thay đổi, ${failed} Agent lỗi.`
        : `Lượt chạy xong: ${run.steps.length} Agent đã làm, file đã cập nhật ngay trên project.`;
      if (handleRef.current) {
        const written = await writeProjectToFolder(projectId);
        if (written) message += ` Đã ghi ${written} file về thư mục "${folderName}" trên máy.`;
      }
      setNotice(message);
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
          <button type="button" className="button secondary" onClick={importFolder}>
            <FolderOpen size={15} /> Import thư mục
          </button>
          <input
            ref={(el) => {
              folderInputRef.current = el;
              if (el) el.setAttribute("webkitdirectory", "");
            }}
            type="file"
            hidden
            onChange={importFolderFromInput}
          />
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
          <div className="st-linkbar">
            <HardDrive size={15} />
            {folderName ? (
              <>
                <span>
                  Thư mục máy: <strong>{folderName}</strong>
                  {folderGranted
                    ? " — đã cấp quyền ghi: AI sửa xong và mỗi lần bạn lưu đều tự ghi về thư mục này."
                    : " — chưa cấp quyền ghi (bấm Ghi về thư mục để cấp)."}
                </span>
                <button type="button" className="button secondary" onClick={syncDown} disabled={syncing}>
                  {syncing ? <LoaderCircle size={14} className="spin" /> : <FolderSync size={14} />} Ghi về thư mục
                </button>
                <button type="button" className="button secondary" onClick={syncUp} disabled={syncing}>
                  <RefreshCw size={14} /> Đọc lại từ thư mục
                </button>
                <button type="button" className="button secondary" onClick={unlinkFolder}>
                  <Unlink size={14} /> Huỷ liên kết
                </button>
              </>
            ) : (
              <>
                <span>Chưa liên kết thư mục trên máy — liên kết để file AI sửa tự ghi về đúng thư mục gốc của bạn (Chrome/Edge).</span>
                {canLinkFolder && (
                  <button type="button" className="button secondary" onClick={linkFolder}>
                    <Link2 size={14} /> Liên kết thư mục
                  </button>
                )}
              </>
            )}
          </div>

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
