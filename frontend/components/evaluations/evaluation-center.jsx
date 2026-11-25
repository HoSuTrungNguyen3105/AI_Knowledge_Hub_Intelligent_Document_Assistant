"use client";

import { useCallback, useEffect, useState } from "react";
import { CompareWorkspace } from "../compare/compare-workspace";
import { ConfirmDialog } from "../confirm-dialog";
import { evaluationsService, getEvalError } from "../../services/evaluations";
import {
  DatasetsPanel,
  HistoryPanel,
  RunDetail,
  RunPanel,
  fmtCost,
  fmtMs,
  fmtNum,
  fmtTime,
} from "./evaluation-runs";

const TABS = [
  ["compare", "So sánh nhanh"],
  ["overview", "Tổng quan"],
  ["datasets", "Datasets"],
  ["runs", "Chạy đánh giá"],
  ["history", "Lịch sử & Regression"],
  ["prompts", "Prompt Evaluation"],
];

function OverviewPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    evaluationsService
      .overview()
      .then((result) => { if (!cancelled) setData(result); })
      .catch((err) => { if (!cancelled) setError(getEvalError(err)); });
    return () => { cancelled = true; };
  }, []);

  if (error) return <p className="wf-error">{error}</p>;
  if (!data) return <p className="eval-note">Đang tải...</p>;
  const kpis = [
    ["Tổng lượt đánh giá", data.total_evaluations],
    ["Model đã test", data.total_models_tested],
    ["Agent đã đánh giá", data.total_agents_evaluated],
    ["Dataset", data.total_datasets],
    ["Accuracy trung bình", data.avg_accuracy === null ? "—" : fmtNum(data.avg_accuracy, 3)],
    ["Latency trung bình", fmtMs(data.avg_latency_ms)],
    ["Token trung bình / case", data.avg_tokens === null ? "—" : Math.round(data.avg_tokens)],
    ["Chi phí trung bình / lượt", fmtCost(data.avg_cost)],
    ["Pass rate", data.pass_rate === null ? "—" : `${fmtNum(data.pass_rate * 100, 1)}%`],
    ["Failure rate", data.failure_rate === null ? "—" : `${fmtNum(data.failure_rate * 100, 1)}%`],
    ["Lượt có regression", data.regression_runs],
  ];
  return (
    <div className="eval-panel">
      <div className="eval-kpis">
        {kpis.map(([label, value]) => (
          <div className="eval-kpi" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <h3 className="eval-subtitle">Chất lượng theo thời gian</h3>
      {data.series.length === 0 ? (
        <p className="eval-note">
          Chưa có dữ liệu. Các chỉ số chỉ xuất hiện sau khi có lượt đánh giá thật —
          hệ thống không hiển thị số liệu mẫu.
        </p>
      ) : (
        <table className="eval-table">
          <thead>
            <tr>
              <th>Lượt chạy</th><th>Loại</th><th>Thời gian</th>
              <th>Accuracy</th><th>Pass rate</th><th>Latency TB</th><th>Chi phí</th>
            </tr>
          </thead>
          <tbody>
            {[...data.series].reverse().map((point) => (
              <tr key={point.run_id}>
                <td>{point.name}</td>
                <td>{point.kind}</td>
                <td>{fmtTime(point.created_at)}</td>
                <td>{point.accuracy === null ? "—" : fmtNum(point.accuracy, 3)}</td>
                <td>{point.pass_rate === null ? "—" : `${fmtNum(point.pass_rate * 100, 1)}%`}</td>
                <td>{fmtMs(point.avg_latency_ms)}</td>
                <td>{fmtCost(point.total_cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PromptsPanel() {
  const [prompts, setPrompts] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("");
  const [newVersions, setNewVersions] = useState({});
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setPrompts(await evaluationsService.listPrompts());
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
      await evaluationsService.createPrompt({ name, template });
      setName("");
      setTemplate("");
      setNotice("Đã tạo prompt set.");
      await load();
    } catch (err) {
      setError(getEvalError(err));
    } finally {
      setBusy(false);
    }
  }

  async function addVersion(prompt) {
    const text = (newVersions[prompt.id] || "").trim();
    if (!text) return;
    setBusy(true);
    setError("");
    try {
      await evaluationsService.updatePrompt(prompt.id, { template: text });
      setNewVersions((prev) => ({ ...prev, [prompt.id]: "" }));
      setNotice(`Đã thêm phiên bản mới cho ${prompt.name}.`);
      await load();
    } catch (err) {
      setError(getEvalError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="eval-panel">
      {error ? <p className="wf-error">{error}</p> : null}
      {notice ? <p className="wf-success">{notice}</p> : null}
      <div className="eval-list">
        {prompts.length === 0 ? (
          <p className="eval-note">Chưa có prompt set nào.</p>
        ) : (
          prompts.map((prompt) => (
            <article className="eval-row eval-row-block" key={prompt.id}>
              <div>
                <strong>{prompt.name}</strong>
                <span>{prompt.versions.length} phiên bản</span>
                {prompt.versions.map((version) => (
                  <p className="eval-template" key={version.version}>
                    v{version.version}: {version.template}
                  </p>
                ))}
                <div className="eval-add-version">
                  <textarea
                    rows={3}
                    placeholder="Template phiên bản mới — phải chứa {input}"
                    value={newVersions[prompt.id] || ""}
                    onChange={(e) =>
                      setNewVersions((prev) => ({ ...prev, [prompt.id]: e.target.value }))
                    }
                  />
                  <div className="wf-actions">
                    <button type="button" className="button small" disabled={busy} onClick={() => addVersion(prompt)}>
                      Thêm phiên bản
                    </button>
                    <button type="button" className="button small danger" onClick={() => setDeleting(prompt)}>
                      Xoá
                    </button>
                  </div>
                </div>
              </div>
            </article>
          ))
        )}
      </div>
      <form className="eval-form" onSubmit={create}>
        <h3>Tạo prompt set</h3>
        <label className="wf-field">
          <span>Tên</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
        </label>
        <label className="wf-field">
          <span>Template (dùng {"{input}"} cho vị trí test case)</span>
          <textarea rows={4} value={template} onChange={(e) => setTemplate(e.target.value)} required />
        </label>
        <button type="submit" className="button" disabled={busy}>Tạo prompt set</button>
      </form>
      <ConfirmDialog
        open={Boolean(deleting)}
        title="Xoá prompt set?"
        busy={busy}
        confirmLabel="Xoá prompt set"
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          setBusy(true);
          try {
            await evaluationsService.removePrompt(deleting.id);
            setDeleting(null);
            await load();
          } catch (err) {
            setError(getEvalError(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        Prompt set {deleting?.name} và toàn bộ phiên bản của nó sẽ bị xoá.
      </ConfirmDialog>
    </div>
  );
}

export function EvaluationCenter() {
  const [tab, setTab] = useState("compare");
  const [datasets, setDatasets] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const reloadMeta = useCallback(async () => {
    try {
      setDatasets(await evaluationsService.listDatasets());
    } catch { /* panel tự báo lỗi */ }
    try {
      setPrompts(await evaluationsService.listPrompts());
    } catch { /* panel tự báo lỗi */ }
  }, []);

  useEffect(() => { reloadMeta(); }, [reloadMeta, refreshKey]);

  async function openRun(id) {
    try {
      setSelectedRun(await evaluationsService.getRun(id));
      setTab("history");
    } catch { /* bỏ qua */ }
  }

  return (
    <div className="eval-center">
      <header className="eval-head">
        <h2>AI Model &amp; Agent Evaluation Center</h2>
        <p>Đánh giá, so sánh và theo dõi chất lượng Model &amp; Agent bằng dữ liệu chạy thật.</p>
      </header>
      <nav className="eval-tabs" aria-label="Evaluation Center">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "compare" ? <CompareWorkspace /> : null}
      {tab === "overview" ? <OverviewPanel key={refreshKey} /> : null}
      {tab === "datasets" ? (
        <DatasetsPanel onChanged={() => setRefreshKey((k) => k + 1)} />
      ) : null}
      {tab === "runs" ? (
        <RunPanel
          datasets={datasets}
          prompts={prompts}
          onDone={() => setRefreshKey((k) => k + 1)}
        />
      ) : null}
      {tab === "history" ? (
        <div>
          <HistoryPanel key={refreshKey} onSelectRun={openRun} />
          {selectedRun ? <RunDetail run={selectedRun} /> : null}
        </div>
      ) : null}
      {tab === "prompts" ? <PromptsPanel /> : null}
    </div>
  );
}
