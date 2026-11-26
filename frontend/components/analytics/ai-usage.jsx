"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { aiUsageService, getAiUsageError } from "../../services/ai-usage";
import "./ai-usage.css";

const PRESETS = [
  { id: "today", label: "Hôm nay" },
  { id: "7d", label: "7 ngày" },
  { id: "30d", label: "30 ngày" },
  { id: "month", label: "Tháng này" },
  { id: "last_month", label: "Tháng trước" },
];

function fmtNumber(value) {
  return new Intl.NumberFormat("vi-VN").format(value || 0);
}

function fmtCost(value) {
  if (value === null || value === undefined) return "Chưa có giá";
  return `$${value.toFixed(4)}`;
}

export function AiUsage() {
  const [preset, setPreset] = useState("30d");
  const [overview, setOverview] = useState(null);
  const [series, setSeries] = useState([]);
  const [chartMode, setChartMode] = useState("tokens");
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [modelSort, setModelSort] = useState("requests");
  const [agents, setAgents] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [history, setHistory] = useState({ items: [], total: 0 });
  const [historyOffset, setHistoryOffset] = useState(0);
  const [filterProvider, setFilterProvider] = useState("");
  const [filterModel, setFilterModel] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [pricing, setPricing] = useState([]);
  const [priceDrafts, setPriceDrafts] = useState({});
  const [budgets, setBudgets] = useState([]);
  const [budgetForm, setBudgetForm] = useState({ scope_type: "total", scope_id: "", monthly_limit_usd: "" });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const rangeParams = useMemo(() => ({ preset }), [preset]);

  const loadMain = useCallback(async () => {
    setBusy("main");
    setError("");
    try {
      const [ov, ts, pv, md, ag, wf] = await Promise.all([
        aiUsageService.overview(rangeParams),
        aiUsageService.timeseries(rangeParams),
        aiUsageService.providers(rangeParams),
        aiUsageService.models({ ...rangeParams, sort: modelSort }),
        aiUsageService.agents(rangeParams),
        aiUsageService.workflows(),
      ]);
      setOverview(ov);
      setSeries(ts);
      setProviders(pv);
      setModels(md);
      setAgents(ag);
      setWorkflows(wf);
    } catch (err) {
      setError(getAiUsageError(err, "Không tải được dữ liệu AI Usage. Hãy thử lại."));
    } finally {
      setBusy("");
    }
  }, [rangeParams, modelSort]);

  const loadHistory = useCallback(async () => {
    try {
      const data = await aiUsageService.history({
        ...rangeParams,
        provider: filterProvider || undefined,
        model: filterModel || undefined,
        status: filterStatus || undefined,
        limit: 20,
        offset: historyOffset,
      });
      setHistory(data);
    } catch (err) {
      setError(getAiUsageError(err, "Không tải được lịch sử sử dụng."));
    }
  }, [rangeParams, filterProvider, filterModel, filterStatus, historyOffset]);

  const loadPricingBudgets = useCallback(async () => {
    try {
      const [prices, budgetRows] = await Promise.all([
        aiUsageService.pricing(),
        aiUsageService.budgets(),
      ]);
      setPricing(prices);
      setBudgets(budgetRows);
    } catch (err) {
      setError(getAiUsageError(err, "Không tải được bảng giá / ngân sách."));
    }
  }, []);

  useEffect(() => {
    loadMain();
  }, [loadMain]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    loadPricingBudgets();
  }, [loadPricingBudgets]);

  useEffect(() => {
    setHistoryOffset(0);
  }, [preset, filterProvider, filterModel, filterStatus]);

  const chartMax = useMemo(() => {
    const values = series.map((point) =>
      chartMode === "tokens" ? point.total_tokens : point.cost_estimate || 0,
    );
    return Math.max(...values, 1);
  }, [series, chartMode]);

  async function downloadCsv() {
    try {
      const blob = await aiUsageService.exportCsv({
        ...rangeParams,
        provider: filterProvider || undefined,
        model: filterModel || undefined,
        status: filterStatus || undefined,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "ai-usage.csv";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getAiUsageError(err, "Không xuất được CSV."));
    }
  }

  async function savePrice(row) {
    const draft = priceDrafts[`${row.provider}:${row.model}`];
    if (!draft) return;
    setBusy(`price-${row.model}`);
    setError("");
    try {
      await aiUsageService.updatePricing({
        provider: row.provider,
        model: row.model,
        input_price_per_1m: Number(draft.input),
        output_price_per_1m: Number(draft.output),
      });
      setNote(`Đã lưu giá ghi đè cho ${row.model}. Chi phí từ nay tính theo giá mới (version tăng 1).`);
      await loadPricingBudgets();
      await loadMain();
    } catch (err) {
      setError(getAiUsageError(err, "Không lưu được giá."));
    } finally {
      setBusy("");
    }
  }

  async function saveBudget() {
    if (!budgetForm.monthly_limit_usd) return;
    setBusy("budget");
    setError("");
    try {
      await aiUsageService.upsertBudget({
        scope_type: budgetForm.scope_type,
        scope_id: budgetForm.scope_id.trim(),
        monthly_limit_usd: Number(budgetForm.monthly_limit_usd),
      });
      setNote("Đã lưu ngân sách. Cảnh báo 50/80/100% sẽ hiện ở chuông thông báo khi đạt mốc.");
      await loadPricingBudgets();
    } catch (err) {
      setError(getAiUsageError(err, "Không lưu được ngân sách."));
    } finally {
      setBusy("");
    }
  }

  const totals = overview?.totals;

  return (
    <section className="usage-page">
      <header className="usage-head">
        <div>
          <h2>AI Usage &amp; Analytics</h2>
          <p className="fx-run-meta">
            Số liệu thật từ các lượt gọi AI của chính tài khoản này (ai_requests + agent_executions).
            Chi phí là ước tính theo bảng giá của bạn; model chưa có giá sẽ ghi rõ “Chưa có giá”, không suy diễn.
          </p>
        </div>
        <button type="button" className="fx-btn" onClick={loadMain} disabled={busy === "main"}>
          {busy === "main" ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} Làm mới
        </button>
      </header>

      <div className="tpl-filters">
        {PRESETS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`fx-btn${preset === item.id ? " fx-btn-primary" : ""}`}
            onClick={() => setPreset(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <p className="fx-error">{error}</p> : null}
      {note ? <p className="fx-note">{note}</p> : null}

      {totals ? (
        <div className="usage-cards">
          <div className="usage-card"><span>Tổng token</span><strong>{fmtNumber(totals.total_tokens)}</strong></div>
          <div className="usage-card"><span>Token đầu vào</span><strong>{fmtNumber(totals.input_tokens)}</strong></div>
          <div className="usage-card"><span>Token đầu ra</span><strong>{fmtNumber(totals.output_tokens)}</strong></div>
          <div className="usage-card"><span>Chi phí ước tính</span><strong>{fmtCost(totals.cost_estimate)}</strong></div>
          <div className="usage-card"><span>Tổng request</span><strong>{fmtNumber(totals.requests)}</strong></div>
          <div className="usage-card"><span>Chi phí TB / request</span><strong>{fmtCost(totals.avg_cost_per_request)}</strong></div>
        </div>
      ) : null}
      {totals && totals.unpriced_requests > 0 ? (
        <p className="fx-run-meta">Có {totals.unpriced_requests} request thuộc model chưa có giá — chưa tính vào chi phí. Bổ sung giá ở mục Bảng giá bên dưới.</p>
      ) : null}

      <div className="n8n-node">
        <h3>
          Biểu đồ theo ngày{" "}
          <select className="fx-input usage-inline-select" value={chartMode} onChange={(event) => setChartMode(event.target.value)}>
            <option value="tokens">Token</option>
            <option value="cost">Chi phí</option>
          </select>
        </h3>
        {series.length ? (
          <div className="usage-chart">
            {series.map((point) => {
              const value = chartMode === "tokens" ? point.total_tokens : point.cost_estimate || 0;
              return (
                <div key={point.date} className="usage-bar-wrap" title={`${point.date}: ${chartMode === "tokens" ? `${fmtNumber(value)} token` : fmtCost(point.cost_estimate)} · ${point.requests} request`}>
                  <div className="usage-bar" style={{ height: `${Math.max(2, (value / chartMax) * 100)}%` }} />
                  <span>{point.date.slice(5)}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="fx-run-meta">Chưa có dữ liệu trong khoảng này.</p>
        )}
      </div>

      <div className="n8n-node">
        <h3>Theo nhà cung cấp</h3>
        {providers.length ? (
          <table className="usage-table">
            <thead><tr><th>Provider</th><th>Requests</th><th>Input</th><th>Output</th><th>Latency TB</th><th>Chi phí</th></tr></thead>
            <tbody>
              {providers.map((row) => (
                <tr key={row.provider}>
                  <td>{row.provider}</td><td>{fmtNumber(row.requests)}</td>
                  <td>{fmtNumber(row.input_tokens)}</td><td>{fmtNumber(row.output_tokens)}</td>
                  <td>{row.avg_latency_ms ? `${Math.round(row.avg_latency_ms)} ms` : "—"}</td>
                  <td>{fmtCost(row.cost_estimate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="fx-run-meta">Chưa có request nào trong khoảng này.</p>}
      </div>

      <div className="n8n-node">
        <h3>
          Theo model{" "}
          <select className="fx-input usage-inline-select" value={modelSort} onChange={(event) => setModelSort(event.target.value)}>
            <option value="requests">Nhiều request nhất</option>
            <option value="tokens">Nhiều token nhất</option>
            <option value="cost">Chi phí cao nhất</option>
            <option value="latency">Latency cao nhất</option>
          </select>
        </h3>
        {models.length ? (
          <table className="usage-table">
            <thead><tr><th>Model</th><th>Provider</th><th>Requests</th><th>Tổng token</th><th>Latency TB</th><th>Tỉ lệ thành công</th><th>Chi phí</th></tr></thead>
            <tbody>
              {models.map((row) => (
                <tr key={`${row.provider}:${row.model}`}>
                  <td>{row.model}</td><td>{row.provider}</td><td>{fmtNumber(row.requests)}</td>
                  <td>{fmtNumber(row.total_tokens)}</td>
                  <td>{row.avg_latency_ms ? `${Math.round(row.avg_latency_ms)} ms` : "—"}</td>
                  <td>{row.success_rate !== null ? `${Math.round(row.success_rate * 100)}%` : "—"}</td>
                  <td>{fmtCost(row.cost_estimate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="fx-run-meta">Chưa có dữ liệu model.</p>}
      </div>

      <div className="n8n-node">
        <h3>Theo AI Agent (từ agent_executions)</h3>
        {agents.length ? (
          <table className="usage-table">
            <thead><tr><th>Agent</th><th>Provider · Model</th><th>Lượt chạy</th><th>Tổng token</th><th>Chi phí</th><th>Thành công</th></tr></thead>
            <tbody>
              {agents.map((row) => (
                <tr key={`${row.agent_id}:${row.provider}:${row.model}`}>
                  <td>{row.agent_name || row.agent_id}</td>
                  <td>{row.provider} · {row.model}</td>
                  <td>{fmtNumber(row.executions)}</td>
                  <td>{fmtNumber(row.total_tokens)}</td>
                  <td>{fmtCost(row.estimated_cost)}</td>
                  <td>{row.success_rate !== null ? `${Math.round(row.success_rate * 100)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="fx-run-meta">Chưa có lượt chạy Agent nào trong khoảng này.</p>}
        {workflows.map((row) => (
          <p key={row.source} className="fx-run-meta">
            Workflow ({row.source}): {row.executions} lượt chạy — token/chi phí theo từng workflow chưa được ghi nhận ở tầng request (ai_requests không gắn workflow_id) nên không hiển thị số ước đoán.
          </p>
        ))}
      </div>

      <div className="n8n-node">
        <h3>Lịch sử gọi AI</h3>
        <div className="tpl-filters">
          <input className="fx-input" placeholder="Lọc provider (vd: groq)" value={filterProvider} onChange={(event) => setFilterProvider(event.target.value)} />
          <input className="fx-input" placeholder="Lọc model" value={filterModel} onChange={(event) => setFilterModel(event.target.value)} />
          <select className="fx-input" value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
            <option value="">Mọi trạng thái</option>
            <option value="success">Thành công</option>
            <option value="error">Thất bại</option>
          </select>
          <button type="button" className="fx-btn" onClick={downloadCsv}>
            <Download size={14} /> Xuất CSV
          </button>
        </div>
        {history.items.length ? (
          <table className="usage-table">
            <thead><tr><th>Thời gian</th><th>Provider</th><th>Model</th><th>Input</th><th>Output</th><th>Chi phí</th><th>Latency</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {history.items.map((row) => (
                <tr key={row.id}>
                  <td>{new Date(row.created_at).toLocaleString("vi-VN")}</td>
                  <td>{row.provider}</td><td>{row.model}</td>
                  <td>{row.input_tokens ?? "—"}</td><td>{row.output_tokens ?? "—"}</td>
                  <td>{fmtCost(row.cost_estimate)}</td>
                  <td>{row.latency_ms ? `${row.latency_ms} ms` : "—"}</td>
                  <td>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="fx-run-meta">Không có lượt gọi nào khớp bộ lọc.</p>}
        <div className="tpl-filters">
          <button type="button" className="fx-btn" disabled={historyOffset === 0} onClick={() => setHistoryOffset(Math.max(0, historyOffset - 20))}>Trang trước</button>
          <span className="fx-run-meta">{history.total} lượt · đang xem từ {historyOffset + 1}</span>
          <button type="button" className="fx-btn" disabled={historyOffset + 20 >= history.total} onClick={() => setHistoryOffset(historyOffset + 20)}>Trang sau</button>
        </div>
      </div>

      <div className="n8n-node">
        <h3>Bảng giá model (USD / 1M token)</h3>
        <p className="fx-run-meta">Giá “đồng bộ” lấy từ provider. Lưu giá mới sẽ tạo giá ghi đè của riêng bạn (tăng version mỗi lần sửa, không sửa code) và được ưu tiên khi tính chi phí.</p>
        {pricing.length ? (
          <table className="usage-table">
            <thead><tr><th>Provider</th><th>Model</th><th>Giá input / 1M</th><th>Giá output / 1M</th><th>Nguồn</th><th></th></tr></thead>
            <tbody>
              {pricing.map((row) => {
                const key = `${row.provider}:${row.model}`;
                const draft = priceDrafts[key] || {
                  input: row.input_price_per_1m ?? "",
                  output: row.output_price_per_1m ?? "",
                };
                return (
                  <tr key={key}>
                    <td>{row.provider}</td><td>{row.model}</td>
                    <td><input className="fx-input usage-price-input" type="number" min="0" step="0.01" value={draft.input} onChange={(event) => setPriceDrafts({ ...priceDrafts, [key]: { ...draft, input: event.target.value } })} /></td>
                    <td><input className="fx-input usage-price-input" type="number" min="0" step="0.01" value={draft.output} onChange={(event) => setPriceDrafts({ ...priceDrafts, [key]: { ...draft, output: event.target.value } })} /></td>
                    <td>{row.source === "override" ? `Ghi đè v${row.version}` : "Đồng bộ"}</td>
                    <td><button type="button" className="fx-btn" disabled={busy === `price-${row.model}`} onClick={() => savePrice(row)}>Lưu giá</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : <p className="fx-run-meta">Chưa có model nào được đồng bộ giá. Kết nối provider và đồng bộ model trước.</p>}
      </div>

      <div className="n8n-node">
        <h3>Ngân sách tháng &amp; cảnh báo</h3>
        {budgets.length ? (
          budgets.map((budget) => (
            <div key={budget.id} className="usage-budget">
              <p className="fx-run-meta">
                <strong>{budget.scope_type}{budget.scope_id ? ` · ${budget.scope_id}` : ""}</strong>:{" "}
                {budget.spent_usd === null ? "chưa tính được (thiếu giá)" : `${fmtCost(budget.spent_usd)} / $${budget.monthly_limit_usd}`} —{" "}
                {budget.percent_used !== null ? `đã dùng ${budget.percent_used.toFixed(0)}%, còn ${fmtCost(budget.remaining_usd)}` : ""}
                {budget.alert_level ? ` · ĐÃ ĐẠT MỐC ${budget.alert_level}%` : ""}
              </p>
              <div className="usage-progress"><div style={{ width: `${Math.min(100, budget.percent_used || 0)}%` }} /></div>
            </div>
          ))
        ) : <p className="fx-run-meta">Chưa đặt ngân sách nào.</p>}
        <div className="tpl-filters">
          <select className="fx-input" value={budgetForm.scope_type} onChange={(event) => setBudgetForm({ ...budgetForm, scope_type: event.target.value })}>
            <option value="total">Tổng toàn bộ</option>
            <option value="provider">Theo provider</option>
            <option value="agent">Theo Agent</option>
          </select>
          <input className="fx-input" placeholder="scope: tên provider hoặc ID agent (để trống nếu Tổng)" value={budgetForm.scope_id} onChange={(event) => setBudgetForm({ ...budgetForm, scope_id: event.target.value })} />
          <input className="fx-input" type="number" min="0" step="0.5" placeholder="Hạn mức USD / tháng" value={budgetForm.monthly_limit_usd} onChange={(event) => setBudgetForm({ ...budgetForm, monthly_limit_usd: event.target.value })} />
          <button type="button" className="fx-btn" disabled={busy === "budget"} onClick={saveBudget}>Lưu ngân sách</button>
        </div>
        <p className="fx-run-meta">Cảnh báo chỉ là thông báo ở chuông (50/80/100%), không tự ngắt API — đúng lưu ý trong đặc tả.</p>
      </div>
    </section>
  );
}
