"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Braces,
  ExternalLink,
  FileJson,
  Loader2,
  Network,
  Plus,
  Power,
  RefreshCw,
  Save,
  SlidersHorizontal,
  Workflow as WorkflowIcon,
  X,
} from "lucide-react";

const SAMPLE_WORKFLOW_JSON = `{
  "name": "Workflow mẫu từ MindFlow",
  "nodes": [
    {
      "parameters": { "path": "xin-chao", "httpMethod": "POST" },
      "id": "11111111-1111-4111-8111-111111111111",
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "22222222-2222-4222-8222-222222222222"
    },
    {
      "parameters": { "jsCode": "return [{ json: { message: 'Xin chào từ MindFlow' } }];" },
      "id": "33333333-3333-4333-8333-333333333333",
      "name": "Trả lời",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [260, 0]
    }
  ],
  "connections": {
    "Webhook": { "main": [[{ "node": "Trả lời", "type": "main", "index": 0 }]] }
  },
  "settings": {}
}`;
import {
  getN8nPlatformError,
  getN8nStatusText,
  n8nPlatformService,
} from "../../services/n8n-platform";

const TRIGGER_LABELS = {
  webhook: "Webhook",
  schedule: "Theo lịch",
  form: "Form",
  manual: "Thủ công",
  "sub-workflow": "Workflow con",
};

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN");
}

// Phase 1 of the n8n Platform: connection status + the instance's workflow
// list, mirrored from the n8n REST API by the backend. Editing a workflow
// still happens in n8n itself (the editor is not embedded) — every row and
// the status card link out to it.
export function N8nPlatformWorkspace() {
  const [status, setStatus] = useState(null);
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [toggling, setToggling] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [edits, setEdits] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [jsonNote, setJsonNote] = useState("");
  const [createName, setCreateName] = useState("");
  const [createJson, setCreateJson] = useState("");
  const [creating, setCreating] = useState(false);
  const [createNote, setCreateNote] = useState("");
  const abortRef = useRef(null);

  // Fill the parameter form from a pasted JSON object shaped
  // { "Node name": { "param.path": value, ... }, ... }. Only parameters
  // that already exist (and match the kind) are filled; the rest are
  // reported as skipped so nothing is silently dropped.
  function applyJsonToForm() {
    if (!detail) return;
    setJsonNote("");
    setError("");
    let parsed;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setJsonNote("JSON không hợp lệ — hãy kiểm tra lại cú pháp.");
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setJsonNote('JSON phải là một object dạng { "Tên node": { "đường.tham.số": giá trị } }.');
      return;
    }
    const next = { ...edits };
    let applied = 0;
    const skipped = [];
    for (const [nodeName, params] of Object.entries(parsed)) {
      const node = detail.nodes.find((item) => item.name === nodeName);
      if (!node || !params || typeof params !== "object" || Array.isArray(params)) {
        skipped.push(nodeName);
        continue;
      }
      for (const [paramPath, rawValue] of Object.entries(params)) {
        const param = node.parameters.find((item) => item.path === paramPath);
        if (!param) {
          skipped.push(`${nodeName}.${paramPath}`);
          continue;
        }
        if (param.kind === "boolean") {
          if (typeof rawValue !== "boolean") {
            skipped.push(`${nodeName}.${paramPath}`);
            continue;
          }
          next[editKey(nodeName, paramPath)] = rawValue;
        } else if (param.kind === "number") {
          const num = typeof rawValue === "number" ? rawValue : Number(rawValue);
          if (typeof rawValue === "boolean" || Number.isNaN(num)) {
            skipped.push(`${nodeName}.${paramPath}`);
            continue;
          }
          next[editKey(nodeName, paramPath)] = String(num);
        } else {
          if (typeof rawValue !== "string") {
            skipped.push(`${nodeName}.${paramPath}`);
            continue;
          }
          next[editKey(nodeName, paramPath)] = rawValue;
        }
        applied += 1;
      }
    }
    setEdits(next);
    setJsonNote(
      `Đã đổ ${applied} tham số vào form.` +
        (skipped.length
          ? ` Bỏ qua ${skipped.length} mục không khớp node/tham số/kiểu: ${skipped.join(", ")}`
          : "") +
        " Kiểm tra lại rồi bấm Cập nhật sang n8n.",
    );
  }

  // Export the form's current values as the same JSON shape, so the user
  // can copy, tweak in an editor and paste back.
  function exportFormToJson() {
    if (!detail) return;
    const out = {};
    for (const node of detail.nodes) {
      const params = {};
      for (const param of node.parameters) {
        const value = edits[editKey(node.name, param.path)];
        if (value === undefined) continue;
        params[param.path] =
          param.kind === "number" ? Number(value) : param.kind === "boolean" ? Boolean(value) : value;
      }
      if (Object.keys(params).length) out[node.name] = params;
    }
    setJsonText(JSON.stringify(out, null, 2));
    setJsonNote("Đã xuất giá trị hiện tại của form vào ô JSON.");
  }

  async function createWorkflow() {
    setCreateNote("");
    setError("");
    let parsed;
    try {
      parsed = JSON.parse(createJson);
    } catch {
      setCreateNote("JSON không hợp lệ — hãy kiểm tra lại cú pháp.");
      return;
    }
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.nodes)) {
      setCreateNote("JSON cần có mảng nodes (định dạng workflow của n8n). Hãy bấm Chèn JSON mẫu để xem khuôn.");
      return;
    }
    const name = createName.trim() || (typeof parsed.name === "string" ? parsed.name : "");
    if (!name) {
      setCreateNote("Hãy nhập tên workflow (hoặc để field name trong JSON).");
      return;
    }
    setCreating(true);
    try {
      const created = await n8nPlatformService.createWorkflow({
        name,
        nodes: parsed.nodes,
        connections: parsed.connections || {},
        settings: parsed.settings || {},
      });
      setCreateNote(
        `Đã tạo workflow "${created.name}" trong n8n (đang tắt). Mở n8n để gắn credential và Publish khi sẵn sàng.`,
      );
      setCreateName("");
      setCreateJson("");
      load();
    } catch (err) {
      setError(getN8nPlatformError(err, "Không tạo được workflow. Hãy thử lại."));
    } finally {
      setCreating(false);
    }
  }

  function editKey(nodeName, paramPath) {
    return `${nodeName}::${paramPath}`;
  }

  async function openEditor(workflow) {
    setDetailLoading(true);
    setSaveNote("");
    setJsonText("");
    setJsonNote("");
    setError("");
    try {
      const data = await n8nPlatformService.getWorkflow(workflow.id);
      const initial = {};
      for (const node of data.nodes) {
        for (const param of node.parameters) {
          initial[editKey(node.name, param.path)] =
            param.kind === "boolean" ? Boolean(param.value) : String(param.value ?? "");
        }
      }
      setEdits(initial);
      setDetail(data);
    } catch (err) {
      setError(getN8nPlatformError(err, "Không tải được cấu hình workflow. Hãy thử lại."));
    } finally {
      setDetailLoading(false);
    }
  }

  function closeEditor() {
    setDetail(null);
    setEdits({});
    setSaveNote("");
    setJsonText("");
    setJsonNote("");
  }

  async function saveEditor() {
    if (!detail) return;
    const updates = [];
    for (const node of detail.nodes) {
      for (const param of node.parameters) {
        const key = editKey(node.name, param.path);
        const edited = edits[key];
        if (edited === undefined) continue;
        const original = param.kind === "boolean" ? Boolean(param.value) : String(param.value ?? "");
        if (edited === original) continue;
        let value = edited;
        if (param.kind === "number") {
          value = Number(edited);
          if (Number.isNaN(value)) {
            setError(`Tham số ${param.path} của node ${node.name} phải là số.`);
            return;
          }
        }
        updates.push({ node: node.name, path: param.path, value });
      }
    }
    if (updates.length === 0) {
      setSaveNote("Chưa có thay đổi nào.");
      return;
    }
    setSaving(true);
    setError("");
    setSaveNote("");
    try {
      const data = await n8nPlatformService.updateParameters(detail.id, updates);
      const initial = {};
      for (const node of data.nodes) {
        for (const param of node.parameters) {
          initial[editKey(node.name, param.path)] =
            param.kind === "boolean" ? Boolean(param.value) : String(param.value ?? "");
        }
      }
      setEdits(initial);
      setDetail(data);
      setSaveNote(`Đã cập nhật ${updates.length} tham số sang n8n.`);
      load();
    } catch (err) {
      setError(getN8nPlatformError(err, "Không cập nhật được tham số. Hãy thử lại."));
    } finally {
      setSaving(false);
    }
  }

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const [statusData, listData] = await Promise.all([
        n8nPlatformService.getStatus(controller.signal),
        n8nPlatformService.listWorkflows(controller.signal),
      ]);
      setStatus(statusData);
      setListing(listData);
    } catch (err) {
      if (err?.name !== "CanceledError" && err?.name !== "AbortError") {
        setError(getN8nPlatformError(err, "Không tải được thông tin n8n. Hãy thử lại."));
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  async function toggle(workflow) {
    setToggling(workflow.id);
    setError("");
    try {
      const updated = await n8nPlatformService.setActive(workflow.id, !workflow.active);
      setListing((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) => (item.id === updated.id ? updated : item)),
            }
          : current,
      );
    } catch (err) {
      setError(getN8nPlatformError(err, "Không đổi được trạng thái workflow. Hãy thử lại."));
    } finally {
      setToggling("");
    }
  }

  const healthy = status?.configured && status?.reachable && status?.authenticated;
  const statusError = status?.error || listing?.sync_error;

  return (
    <div className="fx-page">
      <section className="fx-card">
        <h2>
          <Network size={17} /> Kết nối n8n
          <span className={`n8n-dot${healthy ? " ok" : status ? " bad" : ""}`} aria-hidden="true" />
          <span className="fx-run-meta">
            {loading
              ? "Đang kiểm tra…"
              : healthy
                ? "Đã kết nối"
                : status
                  ? "Chưa kết nối được"
                  : ""}
          </span>
          <span style={{ marginLeft: "auto" }} className="fx-actions">
            <button type="button" className="fx-btn" onClick={load} disabled={loading}>
              {loading ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />} Làm mới
            </button>
            {status?.editor_url ? (
              <a className="fx-btn" href={status.editor_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> Mở n8n
              </a>
            ) : null}
          </span>
        </h2>
        {status ? (
          <div className="fx-chip-row">
            <span className="fx-chip">Địa chỉ: {status.api_base_url}</span>
            <span className="fx-chip">Số workflow đã đồng bộ: {listing ? listing.total : status.workflow_count}</span>
            <span className="fx-chip">Kiểm tra lúc: {formatTime(status.checked_at)}</span>
            {listing?.synced_at ? (
              <span className="fx-chip">Đồng bộ lúc: {formatTime(listing.synced_at)}</span>
            ) : null}
          </div>
        ) : null}
        {statusError ? (
          <div className="fx-error">{getN8nStatusText(statusError)}</div>
        ) : null}
        {error ? <div className="fx-error">{error}</div> : null}
        <p className="fx-run-meta">
          MindFlow quản lý n8n qua REST API bằng key đặt ở server — key không đi qua trình duyệt.
          Sửa nội dung workflow vẫn làm trong n8n (nút Mở ở từng dòng); tại đây bạn xem trạng thái và bật/tắt workflow.
        </p>
      </section>

      <section className="fx-card">
        <h2>
          <WorkflowIcon size={17} /> Workflow trong n8n
          {listing ? <span className="fx-run-meta">{listing.total} workflow</span> : null}
        </h2>
        {loading && !listing ? (
          <p className="fx-run-meta">
            <Loader2 size={14} className="spin" /> Đang tải danh sách…
          </p>
        ) : listing && listing.items.length === 0 ? (
          <p className="fx-run-meta">
            Chưa có workflow nào. Hãy import các workflow trong thư mục n8n-ai-factory/workflows vào n8n rồi bấm Làm mới.
          </p>
        ) : listing ? (
          <div className="n8n-rows">
            {listing.items.map((workflow) => (
              <div key={workflow.id} className="n8n-row">
                <div className="n8n-row-main">
                  <div className="fx-run-req">{workflow.name}</div>
                  <div className="fx-run-meta">
                    {workflow.node_count} node · Cập nhật: {formatTime(workflow.n8n_updated_at)}
                    {workflow.webhook_paths.length
                      ? ` · Webhook: ${workflow.webhook_paths.map((p) => `/webhook/${p}`).join(", ")}`
                      : ""}
                  </div>
                  <div className="fx-chip-row">
                    {workflow.triggers.map((trigger) => (
                      <span key={trigger} className="fx-chip">
                        {TRIGGER_LABELS[trigger] || trigger}
                      </span>
                    ))}
                    {workflow.tags.map((tag) => (
                      <span key={tag} className="fx-chip">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
                <span className={`fx-status ${workflow.active ? "completed" : "cancelled"}`}>
                  {workflow.active ? "Đang bật" : "Đang tắt"}
                </span>
                <span className="fx-actions">
                  <button
                    type="button"
                    className="fx-btn"
                    onClick={() => toggle(workflow)}
                    disabled={toggling === workflow.id || !healthy}
                    title={healthy ? "" : "Cần kết nối được n8n trước"}
                  >
                    {toggling === workflow.id ? (
                      <Loader2 size={15} className="spin" />
                    ) : (
                      <Power size={15} />
                    )}
                    {workflow.active ? "Tắt" : "Bật"}
                  </button>
                  <button
                    type="button"
                    className="fx-btn"
                    onClick={() => openEditor(workflow)}
                    disabled={!healthy || detailLoading}
                    title={healthy ? "Sửa nhanh tham số các node" : "Cần kết nối được n8n trước"}
                  >
                    <SlidersHorizontal size={15} /> Cấu hình
                  </button>
                  <a
                    className="fx-btn"
                    href={workflow.editor_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={15} /> Mở
                  </a>
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {detail ? (
        <section className="fx-card">
          <h2>
            <SlidersHorizontal size={17} /> Cấu hình nhanh — {detail.name}
            <span style={{ marginLeft: "auto" }} className="fx-actions">
              <button type="button" className="fx-btn" onClick={closeEditor} disabled={saving}>
                <X size={15} /> Đóng
              </button>
              <button
                type="button"
                className="fx-btn primary"
                onClick={saveEditor}
                disabled={saving}
              >
                {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
                Cập nhật sang n8n
              </button>
            </span>
          </h2>
          <p className="fx-run-meta">
            Chỉ sửa được giá trị tham số có sẵn (chuỗi, số, bật/tắt). Thêm/bớt node, nối dây và
            credential vẫn làm trong n8n. Bấm Cập nhật là backend ghi thẳng sang n8n qua REST API.
          </p>
          <div className="n8n-node">
            <h3>
              <Braces size={15} /> Nhập JSON để đổ nhanh vào form
              <span style={{ marginLeft: "auto" }} className="fx-actions">
                <button type="button" className="fx-btn" onClick={exportFormToJson}>
                  <FileJson size={15} /> Xuất JSON từ form
                </button>
                <button type="button" className="fx-btn" onClick={applyJsonToForm}>
                  <Braces size={15} /> Đổ JSON vào form
                </button>
              </span>
            </h3>
            <textarea
              className="fx-textarea n8n-json"
              rows={7}
              value={jsonText}
              onChange={(event) => setJsonText(event.target.value)}
              placeholder={'{\n  "Tên node": { "path": "ai-team/start", "options.timeout": 60 }\n}'}
              spellCheck={false}
            />
            {jsonNote ? <p className="fx-run-meta">{jsonNote}</p> : null}
          </div>
          {saveNote ? <div className="fx-chip-row"><span className="fx-chip">{saveNote}</span></div> : null}
          {detail.nodes.map((node) => (
            <div key={node.name} className="n8n-node">
              <h3>
                {node.name || "(node chưa đặt tên)"}
                <span className="fx-run-meta">{node.type}</span>
              </h3>
              {node.parameters.length === 0 ? (
                <p className="fx-run-meta">Node này không có tham số dạng giá trị đơn.</p>
              ) : (
                node.parameters.map((param) => {
                  const key = editKey(node.name, param.path);
                  const value = edits[key];
                  return (
                    <label key={param.path} className="n8n-param">
                      <span className="n8n-param-name">{param.path}</span>
                      {param.kind === "boolean" ? (
                        <input
                          type="checkbox"
                          checked={Boolean(value)}
                          onChange={(event) =>
                            setEdits((current) => ({ ...current, [key]: event.target.checked }))
                          }
                        />
                      ) : param.kind === "number" ? (
                        <input
                          className="fx-input"
                          type="number"
                          value={value ?? ""}
                          onChange={(event) =>
                            setEdits((current) => ({ ...current, [key]: event.target.value }))
                          }
                        />
                      ) : typeof value === "string" && (value.length > 100 || value.includes("\n")) ? (
                        <textarea
                          className="fx-textarea"
                          rows={4}
                          value={value ?? ""}
                          onChange={(event) =>
                            setEdits((current) => ({ ...current, [key]: event.target.value }))
                          }
                        />
                      ) : (
                        <input
                          className="fx-input"
                          type="text"
                          value={value ?? ""}
                          onChange={(event) =>
                            setEdits((current) => ({ ...current, [key]: event.target.value }))
                          }
                        />
                      )}
                    </label>
                  );
                })
              )}
            </div>
          ))}
        </section>
      ) : null}

      <section className="fx-card">
        <h2>
          <Plus size={17} /> Tạo workflow mới trong n8n
        </h2>
        <p className="fx-run-meta">
          Dán định dạng workflow của n8n (nodes + connections) hoặc sửa từ JSON mẫu. Workflow được
          tạo ở trạng thái tắt — gắn credential và Publish trong n8n khi sẵn sàng. Đừng dán key thật
          vào JSON; credential trong n8n được tham chiếu bằng id, không chứa key.
        </p>
        <label className="fx-field">
          Tên workflow
          <input
            className="fx-input"
            type="text"
            value={createName}
            onChange={(event) => setCreateName(event.target.value)}
            placeholder="Để trống sẽ lấy field name trong JSON"
          />
        </label>
        <textarea
          className="fx-textarea n8n-json"
          rows={10}
          value={createJson}
          onChange={(event) => setCreateJson(event.target.value)}
          placeholder="Dán JSON workflow tại đây…"
          spellCheck={false}
        />
        {createNote ? <p className="fx-run-meta">{createNote}</p> : null}
        <div className="fx-actions">
          <button
            type="button"
            className="fx-btn"
            onClick={() => setCreateJson(SAMPLE_WORKFLOW_JSON)}
          >
            <FileJson size={15} /> Chèn JSON mẫu
          </button>
          <button
            type="button"
            className="fx-btn primary"
            onClick={createWorkflow}
            disabled={creating || !healthy}
            title={healthy ? "" : "Cần kết nối được n8n trước"}
          >
            {creating ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
            Tạo workflow trong n8n
          </button>
        </div>
      </section>
    </div>
  );
}
