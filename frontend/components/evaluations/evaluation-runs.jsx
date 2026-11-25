"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { ConfirmDialog } from "../confirm-dialog";
import { agentsService } from "../../services/agents";
import { evaluationsService, getEvalError } from "../../services/evaluations";
import { providerService } from "../../services/providers";

export function fmtNum(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
}

export function fmtMs(value) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value)} ms`;
}

export function fmtCost(value) {
  if (value === null || value === undefined) return "—";
  return `$${Number(value).toFixed(4)}`;
}

export function fmtTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("vi-VN");
}

function download(filename, content, type = "application/json") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function reportJson(run) {
  const failed = run.results.filter((r) => !r.passed);
  return JSON.stringify(
    {
      report: "MindFlow Evaluation Report",
      generated_at: new Date().toISOString(),
      run: {
        id: run.id, name: run.name, kind: run.kind, status: run.status,
        dataset: run.dataset_name, dataset_version: run.dataset_version,
        targets: run.targets, agent: run.agent_name || undefined,
        prompt: run.prompt_name || undefined,
        prompt_version: run.prompt_version || undefined,
        created_at: run.created_at, finished_at: run.finished_at,
      },
      summaries: run.summaries,
      failed_cases: failed,
      results: run.results,
    },
    null,
    2,
  );
}

export function reportCsv(run) {
  const head = "case_index,target,passed,score,judge_score,latency_ms,input_tokens,output_tokens,cost,status,error_code";
  const rows = run.results.map((r) =>
    [
      r.case_index, `"${r.target_key}"`, r.passed, r.score ?? "", r.judge_score ?? "",
      r.latency_ms ?? "", r.input_tokens ?? "", r.output_tokens ?? "",
      r.estimated_cost ?? "", r.status, r.error_code ?? "",
    ].join(","),
  );
  return [head, ...rows].join("\n");
}

/* ------------------------------------------------------------------ detail */
export function RunDetail({ run }) {
  const [open, setOpen] = useState(null);
  if (!run) return null;
  return (
    <div className="eval-detail">
      <div className="wf-section-head">
        <h3>{run.name}</h3>
        <span className={`run-status ${run.status === "completed" ? "success" : ""}`}>
          {run.status}
        </span>
      </div>
      <p className="eval-note">
        Dataset: {run.dataset_name} (v{run.dataset_version})
        {run.agent_name ? ` · Agent: ${run.agent_name}` : ""}
        {run.prompt_name ? ` · Prompt: ${run.prompt_name} v{run.prompt_version}` : ""}
        {" "}· Tiến độ {run.progress_done}/{run.progress_total} · {fmtTime(run.created_at)}
      </p>
      <table className="eval-table">
        <thead>
          <tr>
            <th>Target</th><th>Pass rate</th><th>Accuracy</th><th>Latency TB</th>
            <th>Token TB</th><th>Chi phí</th><th>Lỗi</th>
          </tr>
        </thead>
        <tbody>
          {run.summaries.map((s) => (
            <tr key={s.target_key}>
              <td>{s.target_key}</td>
              <td>{fmtNum(s.pass_rate * 100, 1)}%</td>
              <td>{s.accuracy === null ? "—" : fmtNum(s.accuracy, 3)}</td>
              <td>{fmtMs(s.avg_latency_ms)}</td>
              <td>{s.avg_tokens === null ? "—" : Math.round(s.avg_tokens)}</td>
              <td>{fmtCost(s.total_cost)}</td>
              <td>{s.errors}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="eval-table">
        <thead>
          <tr>
            <th>#</th><th>Target</th><th>Kết quả</th><th>Điểm</th>
            <th>Judge</th><th>Latency</th><th></th>
          </tr>
        </thead>
        <tbody>
          {run.results.map((r, i) => (
            <Fragment key={`${r.case_id}-${r.target_key}-${i}`}>
              <tr>
                <td>{r.case_index + 1}</td>
                <td>{r.target_key}</td>
                <td>
                  <span className={`run-status ${r.passed ? "success" : "error"}`}>
                    {r.status === "error" ? (r.error_code || "error") : r.passed ? "Pass" : "Fail"}
                  </span>
                </td>
                <td>{r.score === null ? "—" : fmtNum(r.score, 3)}</td>
                <td>{r.judge_score === null ? "—" : fmtNum(r.judge_score, 2)}</td>
                <td>{fmtMs(r.latency_ms)}</td>
                <td>
                  <button type="button" className="button small" onClick={() => setOpen(open === i ? null : i)}>
                    {open === i ? "Đóng" : "Chi tiết"}
                  </button>
                </td>
              </tr>
              {open === i ? (
                <tr>
                  <td colSpan={7}>
                    <div className="eval-case-detail">
                      <strong>Output</strong>
                      <pre>{r.output || "(rỗng)"}</pre>
                      {r.scores?.length ? (
                        <p>
                          Tiêu chí:{" "}
                          {r.scores.map((s) => `${s.type}: ${fmtNum(s.score, 2)} (${s.passed ? "đạt" : "chưa đạt"})`).join(" · ")}
                        </p>
                      ) : null}
                      {r.judge_reason ? <p>Judge: {r.judge_reason}</p> : null}
                      {r.trace?.tool_calls?.length ? (
                        <p>
                          Tool calls:{" "}
                          {r.trace.tool_calls.map((t) => `${t.tool_name} (${t.status}, ${fmtMs(t.latency_ms)})`).join(" · ")}
                        </p>
                      ) : null}
                      {r.trace?.execution_id ? (
                        <p>Execution: {r.trace.execution_id} · {r.trace.step_count ?? 0} bước</p>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      <div className="wf-actions">
        <button type="button" className="button small" onClick={() => download(`eval-report-${run.id}.json`, reportJson(run))}>
          Xuất báo cáo JSON
        </button>
        <button type="button" className="button small" onClick={() => download(`eval-report-${run.id}.csv`, reportCsv(run), "text/csv")}>
          Xuất CSV
        </button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- datasets */
const CASE_TEMPLATE = JSON.stringify(
  [
    {
      input: "Câu hỏi hoặc nhiệm vụ kiểm thử",
      expected_output: "Đáp án kỳ vọng",
      criteria: [{ type: "similarity", value: "", threshold: 0.6 }],
    },
  ],
  null,
  2,
);

export function DatasetsPanel({ onChanged }) {
  const [datasets, setDatasets] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("general");
  const [casesText, setCasesText] = useState(CASE_TEMPLATE);
  const [importFormat, setImportFormat] = useState("json");
  const [importText, setImportText] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setDatasets(await evaluationsService.listDatasets());
    } catch (err) {
      setError(getEvalError(err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const cases = JSON.parse(casesText);
      await evaluationsService.createDataset({ name, category, cases });
      setName("");
      setNotice("Đã tạo dataset.");
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof SyntaxError ? "Phần cases chưa phải JSON hợp lệ." : getEvalError(err));
    } finally {
      setBusy(false);
    }
  }

  async function doImport(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await evaluationsService.importDataset({ format: importFormat, content: importText, name });
      setImportText("");
      setNotice("Đã import dataset.");
      await load();
      onChanged?.();
    } catch (err) {
      setError(getEvalError(err));
    } finally {
      setBusy(false);
    }
  }

  async function doExport(dataset) {
    try {
      const data = await evaluationsService.exportDataset(dataset.id);
      download(data.filename, data.content);
    } catch (err) {
      setError(getEvalError(err));
    }
  }

  return (
    <div className="eval-panel">
      {error ? <p className="wf-error">{error}</p> : null}
      {notice ? <p className="wf-success">{notice}</p> : null}
      <div className="eval-list">
        {datasets.length === 0 ? (
          <p className="eval-note">Chưa có dataset nào. Tạo dataset đầu tiên ở form bên dưới.</p>
        ) : (
          datasets.map((d) => (
            <article className="eval-row" key={d.id}>
              <div>
                <strong>{d.name}</strong>
                <span>{d.category} · v{d.version} · {d.case_count} test case · {fmtTime(d.updated_at)}</span>
              </div>
              <div className="wf-actions">
                <button type="button" className="button small" onClick={() => doExport(d)}>Export</button>
                <button type="button" className="button small danger" onClick={() => setDeleting(d)}>Xoá</button>
              </div>
            </article>
          ))
        )}
      </div>
      <form className="eval-form" onSubmit={create}>
        <h3>Tạo dataset</h3>
        <div className="wf-form-grid">
          <label className="wf-field">
            <span>Tên dataset</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
          </label>
          <label className="wf-field">
            <span>Loại</span>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {["general", "qa", "coding", "rag", "tool_calling", "multi_agent", "workflow", "support", "structured", "vietnamese"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="wf-field">
          <span>Test cases (JSON) — mỗi case: input, expected_output, criteria (exact/contains/regex/json_valid/similarity)</span>
          <textarea rows={10} value={casesText} onChange={(e) => setCasesText(e.target.value)} />
        </label>
        <button type="submit" className="button" disabled={busy}>Tạo dataset</button>
      </form>
      <form className="eval-form" onSubmit={doImport}>
        <h3>Import dataset</h3>
        <div className="wf-form-grid">
          <label className="wf-field">
            <span>Định dạng</span>
            <select value={importFormat} onChange={(e) => setImportFormat(e.target.value)}>
              <option value="json">JSON</option>
              <option value="csv">CSV (cột input, expected_output, tags)</option>
            </select>
          </label>
        </div>
        <label className="wf-field">
          <span>Nội dung file</span>
          <textarea rows={6} value={importText} onChange={(e) => setImportText(e.target.value)} required />
        </label>
        <button type="submit" className="button" disabled={busy}>Import</button>
      </form>
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xoá dataset?"
        busy={busy}
        confirmLabel="Xoá dataset"
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          setBusy(true);
          try {
            await evaluationsService.removeDataset(deleting.id);
            setDeleting(null);
            await load();
            onChanged?.();
          } catch (err) {
            setError(getEvalError(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        Dataset {deleting?.name} sẽ bị xoá. Các lượt đánh giá đã chạy vẫn giữ nguyên kết quả.
      </ConfirmDialog>
    </div>
  );
}

/* -------------------------------------------------------------------- runs */
export function RunPanel({ datasets, prompts, onDone }) {
  const [kind, setKind] = useState("model");
  const [datasetId, setDatasetId] = useState("");
  const [targets, setTargets] = useState([]);
  const [selected, setSelected] = useState([]);
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState("");
  const [promptId, setPromptId] = useState("");
  const [judge, setJudge] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [run, setRun] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await providerService.list();
        const ready = (data.providers || []).filter(
          (p) => p.implemented && p.configured && p.enabled,
        );
        const options = [];
        for (const provider of ready) {
          const modelsData = await providerService.models(provider.id);
          for (const model of modelsData.models || []) {
            if (model.capabilities?.chat !== false) {
              options.push({ provider: provider.id, model: model.id });
            }
          }
        }
        if (!cancelled) setTargets(options);
      } catch { /* danh sách trống -> form báo chưa cấu hình */ }
      try {
        const list = await agentsService.list();
        if (!cancelled) setAgents(list || []);
      } catch { /* bỏ qua */ }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!datasetId && datasets.length) setDatasetId(datasets[0].id);
  }, [datasets, datasetId]);

  function toggleTarget(key) {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev.slice(-4), key],
    );
  }

  async function submit(event) {
    event.preventDefault();
    setRunning(true);
    setError("");
    setRun(null);
    try {
      const payload = { dataset_id: datasetId, kind };
      if (kind === "agent") {
        payload.agent_id = agentId;
      } else {
        payload.targets = selected.map((key) => {
          const [provider, ...rest] = key.split("/");
          return { provider, model: rest.join("/") };
        });
      }
      if (kind === "prompt") payload.prompt_id = promptId;
      if (judge) {
        const [provider, ...rest] = judge.split("/");
        payload.judge = { provider, model: rest.join("/") };
      }
      const result = await evaluationsService.createRun(payload);
      setRun(result);
      onDone?.();
    } catch (err) {
      setError(getEvalError(err));
    } finally {
      setRunning(false);
    }
  }

  const promptSet = prompts.find((p) => p.id === promptId);

  return (
    <div className="eval-panel">
      {error ? <p className="wf-error">{error}</p> : null}
      <form className="eval-form" onSubmit={submit}>
        <div className="wf-form-grid">
          <label className="wf-field">
            <span>Dataset</span>
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} required>
              <option value="">— Chọn dataset —</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>{d.name} ({d.case_count} case)</option>
              ))}
            </select>
          </label>
          <label className="wf-field">
            <span>Loại đánh giá</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="model">Model</option>
              <option value="agent">Agent</option>
              <option value="prompt">Prompt</option>
            </select>
          </label>
        </div>
        {kind !== "agent" ? (
          <div className="wf-field">
            <span>Model targets (tối đa 5)</span>
            {targets.length === 0 ? (
              <p className="eval-note">Chưa có provider/model nào sẵn sàng. Hãy cấu hình ở trang Providers trước.</p>
            ) : (
              <div className="eval-targets">
                {targets.map((t) => {
                  const key = `${t.provider}/${t.model}`;
                  return (
                    <label key={key} className="eval-check">
                      <input
                        type="checkbox"
                        checked={selected.includes(key)}
                        onChange={() => toggleTarget(key)}
                      />
                      {key}
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <label className="wf-field">
            <span>Agent</span>
            <select value={agentId} onChange={(e) => setAgentId(e.target.value)} required>
              <option value="">— Chọn Agent —</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name} ({a.provider}/{a.model})</option>
              ))}
            </select>
          </label>
        )}
        {kind === "prompt" ? (
          <label className="wf-field">
            <span>Prompt set (chạy phiên bản mới nhất)</span>
            <select value={promptId} onChange={(e) => setPromptId(e.target.value)} required>
              <option value="">— Chọn prompt —</option>
              {prompts.map((p) => (
                <option key={p.id} value={p.id}>{p.name} (v{p.versions.length})</option>
              ))}
            </select>
            {promptSet ? (
              <small className="eval-note">{promptSet.versions[promptSet.versions.length - 1]?.template}</small>
            ) : null}
          </label>
        ) : null}
        {kind !== "agent" ? (
          <label className="wf-field">
            <span>LLM Judge (tuỳ chọn — điểm giám khảo, không phải ground truth)</span>
            <select value={judge} onChange={(e) => setJudge(e.target.value)}>
              <option value="">Không dùng judge</option>
              {targets.map((t) => {
                const key = `${t.provider}/${t.model}`;
                return <option key={key} value={key}>{key}</option>;
              })}
            </select>
          </label>
        ) : null}
        <button type="submit" className="button" disabled={running || !datasetId}>
          {running ? "Đang chạy đánh giá..." : "Chạy đánh giá"}
        </button>
        {running ? (
          <p className="eval-note">Engine chạy lần lượt từng case và lưu tiến độ; dataset lớn có thể mất vài phút.</p>
        ) : null}
      </form>
      {run ? <RunDetail run={run} /> : null}
    </div>
  );
}

/* ----------------------------------------------------------------- history */
export function HistoryPanel({ onSelectRun }) {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [currentId, setCurrentId] = useState("");
  const [comparison, setComparison] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setRuns(await evaluationsService.listRuns({}));
    } catch (err) {
      setError(getEvalError(err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function doCompare() {
    setBusy(true);
    setError("");
    try {
      setComparison(await evaluationsService.compareRuns(baselineId, currentId));
    } catch (err) {
      setError(getEvalError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="eval-panel">
      {error ? <p className="wf-error">{error}</p> : null}
      {runs.length === 0 ? (
        <p className="eval-note">Chưa có lượt đánh giá nào. Hãy chạy lượt đầu tiên ở tab Chạy đánh giá.</p>
      ) : (
        <table className="eval-table">
          <thead>
            <tr>
              <th>Tên</th><th>Loại</th><th>Dataset</th><th>Trạng thái</th>
              <th>Pass rate</th><th>Accuracy</th><th>Thời gian</th><th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>{r.name}{r.is_baseline ? " · Baseline" : ""}</td>
                <td>{r.kind}</td>
                <td>{r.dataset_name}</td>
                <td>{r.status}</td>
                <td>{r.pass_rate === null ? "—" : `${fmtNum(r.pass_rate * 100, 1)}%`}</td>
                <td>{r.accuracy === null ? "—" : fmtNum(r.accuracy, 3)}</td>
                <td>{fmtTime(r.created_at)}</td>
                <td>
                  <div className="wf-actions">
                    <button type="button" className="button small" onClick={() => onSelectRun(r.id)}>Xem</button>
                    <button
                      type="button"
                      className="button small"
                      onClick={async () => {
                        await evaluationsService.setBaseline(r.id);
                        await load();
                      }}
                    >
                      Đặt baseline
                    </button>
                    {r.status === "running" ? (
                      <button
                        type="button"
                        className="button small danger"
                        onClick={async () => {
                          await evaluationsService.cancelRun(r.id);
                          await load();
                        }}
                      >
                        Huỷ
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="eval-form">
        <h3>So sánh regression</h3>
        <div className="wf-form-grid">
          <label className="wf-field">
            <span>Baseline</span>
            <select value={baselineId} onChange={(e) => setBaselineId(e.target.value)}>
              <option value="">— Chọn run —</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>{r.name} · {fmtTime(r.created_at)}</option>
              ))}
            </select>
          </label>
          <label className="wf-field">
            <span>Lượt hiện tại</span>
            <select value={currentId} onChange={(e) => setCurrentId(e.target.value)}>
              <option value="">— Chọn run —</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>{r.name} · {fmtTime(r.created_at)}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" className="button" disabled={busy || !baselineId || !currentId} onClick={doCompare}>
          So sánh
        </button>
        {comparison ? (
          <div className="eval-compare">
            {comparison.regression_detected ? (
              <p className="wf-error">Phát hiện regression so với baseline.</p>
            ) : (
              <p className="wf-success">Không phát hiện regression đáng kể.</p>
            )}
            <p>
              Accuracy Δ {comparison.accuracy_delta === null ? "—" : fmtNum(comparison.accuracy_delta, 3)} ·
              Pass rate Δ {comparison.pass_rate_delta === null ? "—" : fmtNum(comparison.pass_rate_delta, 3)} ·
              Latency Δ {comparison.latency_delta_ms === null ? "—" : fmtMs(comparison.latency_delta_ms)} ·
              Cost Δ {comparison.cost_delta === null ? "—" : fmtCost(comparison.cost_delta)}
            </p>
            {comparison.affected_cases.length ? (
              <ul>
                {comparison.affected_cases.map((a, i) => (
                  <li key={i}>
                    Case #{a.case_index + 1} ({a.target_key}): {a.change}
                    {a.baseline_score !== null && a.current_score !== null
                      ? ` — điểm ${fmtNum(a.baseline_score, 2)} → ${fmtNum(a.current_score, 2)}`
                      : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="eval-note">Không có case nào đổi trạng thái pass/fail.</p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
