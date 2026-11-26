"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  FileJson,
  Loader2,
  MousePointer2,
  Plus,
  Save,
  Trash2,
  Workflow,
} from "lucide-react";
import { n8nPlatformService } from "../../services/n8n-platform";
import {
  getWorkflowStudioError,
  workflowStudioService,
} from "../../services/workflow-studio";
import { workflowTemplatesService } from "../../services/workflow-templates";

const CARD_W = 176;
const CARD_H = 58;
let idCounter = 0;

function nextId() {
  idCounter += 1;
  return `studio-${Date.now()}-${idCounter}`;
}

export function WorkflowStudio() {
  const [catalog, setCatalog] = useState([]);
  const [name, setName] = useState("Workflow mới");
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [connectFrom, setConnectFrom] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templatePick, setTemplatePick] = useState("");
  const [pasteJson, setPasteJson] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [paramTexts, setParamTexts] = useState({});
  const canvasRef = useRef(null);
  const dragRef = useRef(null);

  useEffect(() => {
    workflowStudioService
      .getCatalog()
      .then((data) => setCatalog(data.node_types || []))
      .catch(() => setCatalog([]));
    workflowTemplatesService
      .listTemplates({ limit: 100 })
      .then((data) => setTemplates(data.items || []))
      .catch(() => setTemplates([]));
  }, []);

  const selected = nodes.find((node) => node.id === selectedId) || null;
  const specOf = useCallback(
    (type) => catalog.find((item) => item.type === type) || null,
    [catalog],
  );

  function uniqueName(base) {
    let candidate = base;
    let counter = 2;
    const taken = new Set(nodes.map((node) => node.name));
    while (taken.has(candidate)) {
      candidate = `${base} ${counter}`;
      counter += 1;
    }
    return candidate;
  }

  function addNode(spec) {
    const defaults = {};
    for (const param of spec.parameters || []) {
      if (param.default !== null && param.default !== undefined) {
        defaults[param.name] = param.default;
      }
    }
    const node = {
      id: nextId(),
      name: uniqueName(spec.display_name),
      type: spec.type,
      position: [60 + (nodes.length % 5) * 40, 60 + (nodes.length % 4) * 40],
      parameters: defaults,
      supported: true,
      raw: null,
    };
    setNodes((current) => [...current, node]);
    setSelectedId(node.id);
  }

  function removeNode(node) {
    setNodes((current) => current.filter((item) => item.id !== node.id));
    setEdges((current) =>
      current.filter((edge) => edge.from_node !== node.name && edge.to_node !== node.name),
    );
    if (selectedId === node.id) setSelectedId(null);
  }

  function renameNode(node, newName) {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === node.name) return;
    if (nodes.some((item) => item.id !== node.id && item.name === trimmed)) {
      setError(`Đã có node tên "${trimmed}". Tên node phải khác nhau.`);
      return;
    }
    setEdges((current) =>
      current.map((edge) => ({
        ...edge,
        from_node: edge.from_node === node.name ? trimmed : edge.from_node,
        to_node: edge.to_node === node.name ? trimmed : edge.to_node,
      })),
    );
    setNodes((current) =>
      current.map((item) => (item.id === node.id ? { ...item, name: trimmed } : item)),
    );
  }

  function onNodeClick(node) {
    if (connectFrom && connectFrom !== node.name) {
      const exists = edges.some(
        (edge) => edge.from_node === connectFrom && edge.to_node === node.name,
      );
      if (!exists) {
        setEdges((current) => [
          ...current,
          { from_node: connectFrom, to_node: node.name, output_index: 0 },
        ]);
      }
      setConnectFrom(null);
      return;
    }
    setSelectedId(node.id);
  }

  function onPointerDown(event, node) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = {
      id: node.id,
      dx: event.clientX - rect.left - node.position[0],
      dy: event.clientY - rect.top - node.position[1],
      moved: false,
    };
  }

  function onPointerMove(event) {
    const drag = dragRef.current;
    if (!drag) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    drag.moved = true;
    const x = Math.max(0, event.clientX - rect.left - drag.dx);
    const y = Math.max(0, event.clientY - rect.top - drag.dy);
    setNodes((current) =>
      current.map((node) => (node.id === drag.id ? { ...node, position: [x, y] } : node)),
    );
  }

  function graphPayload() {
    return {
      name,
      nodes: nodes.map((node) => ({
        id: node.id,
        name: node.name,
        type: node.type,
        position: node.position,
        parameters: node.parameters || {},
        raw: node.raw || null,
      })),
      edges,
    };
  }

  async function convert() {
    setBusy("convert");
    setError("");
    try {
      const data = await workflowStudioService.convert(graphPayload());
      setPreview(data);
      return data;
    } catch (err) {
      setError(getWorkflowStudioError(err, "Chuyển đổi thất bại. Hãy kiểm tra lại đồ thị."));
      return null;
    } finally {
      setBusy("");
    }
  }

  async function saveToN8n() {
    const data = await convert();
    if (!data) return;
    setBusy("save");
    try {
      const workflow = data.workflow_json;
      const created = await n8nPlatformService.createWorkflow({
        name: workflow.name,
        nodes: workflow.nodes,
        connections: workflow.connections,
        settings: workflow.settings || {},
      });
      setNote(
        `Đã lưu "${created.name}" vào n8n (id ${created.id}, đang tắt). Mở tab n8n Platform để gắn credential và Bật.`,
      );
    } catch (err) {
      setError(getWorkflowStudioError(err, "Lưu vào n8n thất bại. Hãy thử lại."));
    } finally {
      setBusy("");
    }
  }

  async function loadGraph(workflowJson, label) {
    setBusy("parse");
    setError("");
    try {
      const graph = await workflowStudioService.parse(workflowJson);
      setName(graph.name || label || "Workflow");
      setNodes(
        graph.nodes.map((node) => ({
          id: node.id || nextId(),
          name: node.name,
          type: node.type,
          position: node.position || [60, 60],
          parameters: node.parameters || {},
          supported: node.supported,
          raw: node.raw || null,
        })),
      );
      setEdges(graph.edges || []);
      setSelectedId(null);
      setPreview(null);
      setNote(
        graph.unsupported.length
          ? `Đã nạp ${label || "workflow"}: ${graph.unsupported.length} node chưa có adapter (${graph.unsupported.join(", ")}) — các node này được giữ nguyên JSON gốc khi lưu.`
          : `Đã nạp ${label || "workflow"} vào Studio.`,
      );
    } catch (err) {
      setError(getWorkflowStudioError(err, "Không nạp được workflow vào Studio."));
    } finally {
      setBusy("");
    }
  }

  async function openTemplate() {
    if (!templatePick) return;
    setBusy("parse");
    try {
      const detail = await workflowTemplatesService.getTemplate(templatePick);
      await loadGraph(detail.workflow_json, `template "${detail.name}"`);
    } catch (err) {
      setError(getWorkflowStudioError(err, "Không mở được template trong Studio."));
      setBusy("");
    }
  }

  function openPasted() {
    let parsed;
    try {
      parsed = JSON.parse(pasteJson);
    } catch {
      setError("JSON dán vào chưa hợp lệ.");
      return;
    }
    loadGraph(parsed, "workflow từ JSON");
  }

  function setParam(node, param, value) {
    setNodes((current) =>
      current.map((item) =>
        item.id === node.id
          ? { ...item, parameters: { ...(item.parameters || {}), [param.name]: value } }
          : item,
      ),
    );
  }

  const byName = {};
  for (const node of nodes) byName[node.name] = node;
  const categories = [...new Set(catalog.map((item) => item.category))];

  return (
    <div className="fx-page">
      <section className="fx-card">
        <h2>
          <Workflow size={17} /> Workflow Studio — dựng workflow ngay trong MindFlow
        </h2>
        <p className="fx-run-meta">
          Kéo thả node trên canvas, nối các node, cấu hình tham số rồi Lưu vào n8n — n8n vẫn là
          engine chạy thật. Chỉ các node có trong catalog mới có form cấu hình; node lạ mở từ
          template/JSON được giữ nguyên dữ liệu và gắn cờ rõ ràng, không bao giờ bị âm thầm xóa.
        </p>
        {error ? (
          <p className="fx-alert" role="alert">
            {error}
          </p>
        ) : null}
        {note ? <p className="fx-run-meta">{note}</p> : null}
        <div className="tpl-filters">
          <label className="fx-field">
            Tên workflow
            <input
              className="fx-input"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="fx-field">
            Mở từ template trong thư viện
            <select
              className="fx-input"
              value={templatePick}
              onChange={(event) => setTemplatePick(event.target.value)}
            >
              <option value="">Chọn template…</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <div className="fx-actions">
            <button type="button" className="fx-btn" onClick={openTemplate} disabled={!templatePick || busy === "parse"}>
              Mở template
            </button>
            <button
              type="button"
              className="fx-btn"
              onClick={() => {
                setNodes([]);
                setEdges([]);
                setPreview(null);
                setSelectedId(null);
                setName("Workflow mới");
              }}
            >
              Tạo mới
            </button>
          </div>
        </div>
        <label className="fx-field">
          Hoặc dán JSON workflow (xuất từ n8n) để mở
          <textarea
            className="fx-input tpl-json-input"
            rows={3}
            value={pasteJson}
            onChange={(event) => setPasteJson(event.target.value)}
            placeholder='{"name": "...", "nodes": [...], "connections": {...}}'
          />
        </label>
        <div className="fx-actions">
          <button type="button" className="fx-btn" onClick={openPasted} disabled={!pasteJson.trim() || busy === "parse"}>
            Nạp JSON vào Studio
          </button>
          <button type="button" className="fx-btn" onClick={convert} disabled={busy === "convert" || nodes.length === 0}>
            {busy === "convert" ? <Loader2 size={15} className="spin" /> : <FileJson size={15} />} Kiểm tra & xem JSON
          </button>
          <button type="button" className="fx-btn primary" onClick={saveToN8n} disabled={busy === "save" || nodes.length === 0}>
            {busy === "save" ? <Loader2 size={15} className="spin" /> : <Save size={15} />} Lưu vào n8n
          </button>
        </div>
        {preview ? (
          <div>
            {preview.warnings?.length ? (
              <p className="fx-run-meta">
                <AlertTriangle size={13} /> {preview.warnings.join(" ")}
              </p>
            ) : null}
            <details open>
              <summary>JSON n8n sẽ được lưu</summary>
              <pre className="tpl-json">{JSON.stringify(preview.workflow_json, null, 2)}</pre>
            </details>
          </div>
        ) : null}
      </section>

      <section className="fx-card">
        <div className="studio-layout">
          <div className="studio-palette">
            <h3>Node catalog</h3>
            {categories.map((category) => (
              <div key={category}>
                <p className="fx-run-meta">
                  <strong>{category}</strong>
                </p>
                {catalog
                  .filter((item) => item.category === category)
                  .map((spec) => (
                    <button
                      key={spec.type}
                      type="button"
                      className="fx-btn studio-palette-btn"
                      onClick={() => addNode(spec)}
                    >
                      <Plus size={13} /> {spec.display_name}
                    </button>
                  ))}
              </div>
            ))}
            <p className="fx-run-meta">
              <MousePointer2 size={12} /> Kéo thẻ node để di chuyển. Bấm nút "Nối" trên một node
              rồi bấm node đích để tạo kết nối.
            </p>
            {connectFrom ? (
              <p className="fx-run-meta">
                Đang nối từ <strong>{connectFrom}</strong> — bấm node đích trên canvas (bấm lại
                nút Nối để hủy).
              </p>
            ) : null}
          </div>
          <div
            className="studio-canvas"
            ref={canvasRef}
            onPointerMove={onPointerMove}
            onPointerUp={() => {
              dragRef.current = null;
            }}
          >
            <svg className="studio-edges">
              <defs>
                <marker id="studio-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                  <path d="M0,0 L7,3 L0,6 Z" fill="currentColor" />
                </marker>
              </defs>
              {edges.map((edge, index) => {
                const from = byName[edge.from_node];
                const to = byName[edge.to_node];
                if (!from || !to) return null;
                return (
                  <line
                    key={index}
                    x1={from.position[0] + CARD_W}
                    y1={from.position[1] + CARD_H / 2}
                    x2={to.position[0]}
                    y2={to.position[1] + CARD_H / 2}
                    stroke="currentColor"
                    strokeWidth="1.6"
                    markerEnd="url(#studio-arrow)"
                  />
                );
              })}
            </svg>
            {nodes.length === 0 ? (
              <p className="fx-run-meta studio-empty">
                Canvas trống — thêm node từ catalog bên trái, hoặc mở một template.
              </p>
            ) : null}
            {nodes.map((node) => (
              <div
                key={node.id}
                className={`studio-node${selectedId === node.id ? " selected" : ""}${node.supported ? "" : " unsupported"}`}
                style={{ left: node.position[0], top: node.position[1], width: CARD_W }}
                onPointerDown={(event) => onPointerDown(event, node)}
                onClick={() => onNodeClick(node)}
              >
                <strong>{node.name}</strong>
                <span>{specOf(node.type)?.display_name || node.type}</span>
                {!node.supported ? <span className="studio-flag">Chưa hỗ trợ — giữ nguyên</span> : null}
                <button
                  type="button"
                  className="studio-connect"
                  onClick={(event) => {
                    event.stopPropagation();
                    setConnectFrom(connectFrom === node.name ? null : node.name);
                  }}
                >
                  Nối
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {selected ? (
        <section className="fx-card">
          <h2>
            Cấu hình node: {selected.name}
            <span style={{ marginLeft: "auto" }}>
              <button type="button" className="fx-btn" onClick={() => removeNode(selected)}>
                <Trash2 size={14} /> Xóa node
              </button>
            </span>
          </h2>
          <label className="fx-field">
            Tên node
            <input
              className="fx-input"
              type="text"
              defaultValue={selected.name}
              key={selected.id + selected.name}
              onBlur={(event) => renameNode(selected, event.target.value)}
            />
          </label>
          {!selected.supported ? (
            <p className="fx-run-meta">
              <AlertTriangle size={13} /> Node này chưa có adapter trong Studio nên không sửa tham
              số ở đây được. Nó vẫn được giữ nguyên JSON gốc khi lưu vào n8n.
            </p>
          ) : (
            <div className="tpl-filters">
              {(specOf(selected.type)?.parameters || []).map((param) => {
                const value = (selected.parameters || {})[param.name];
                const textKey = `${selected.id}:${param.name}`;
                if (param.type === "options") {
                  return (
                    <label key={param.name} className="fx-field">
                      {param.label}
                      {param.required ? " *" : ""}
                      <select
                        className="fx-input"
                        value={value ?? param.default ?? ""}
                        onChange={(event) => setParam(selected, param, event.target.value)}
                      >
                        {(param.options || []).map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                }
                if (param.type === "boolean") {
                  return (
                    <label key={param.name} className="fx-field tpl-check">
                      <input
                        type="checkbox"
                        checked={Boolean(value)}
                        onChange={(event) => setParam(selected, param, event.target.checked)}
                      />
                      {param.label}
                    </label>
                  );
                }
                if (param.type === "json") {
                  return (
                    <label key={param.name} className="fx-field">
                      {param.label}
                      {param.required ? " *" : ""}
                      <textarea
                        className="fx-input tpl-json-input"
                        rows={4}
                        value={
                          paramTexts[textKey] ??
                          JSON.stringify(value ?? param.default ?? {}, null, 2)
                        }
                        onChange={(event) => {
                          const text = event.target.value;
                          setParamTexts((current) => ({ ...current, [textKey]: text }));
                          try {
                            setParam(selected, param, JSON.parse(text));
                          } catch {
                            // Keep typing; validation happens on convert.
                          }
                        }}
                      />
                    </label>
                  );
                }
                return (
                  <label key={param.name} className="fx-field">
                    {param.label}
                    {param.required ? " *" : ""}
                    <input
                      className="fx-input"
                      type={param.type === "number" ? "number" : "text"}
                      value={value ?? ""}
                      onChange={(event) =>
                        setParam(
                          selected,
                          param,
                          param.type === "number"
                            ? Number(event.target.value)
                            : event.target.value,
                        )
                      }
                    />
                  </label>
                );
              })}
            </div>
          )}
          {edges.filter((edge) => edge.from_node === selected.name || edge.to_node === selected.name).length ? (
            <p className="fx-run-meta">
              Kết nối:{" "}
              {edges
                .filter((edge) => edge.from_node === selected.name || edge.to_node === selected.name)
                .map((edge) => `${edge.from_node} → ${edge.to_node}`)
                .join(" · ")}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
