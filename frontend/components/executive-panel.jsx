"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart3, Bot, CheckCircle2, Coins, RefreshCw, Workflow } from "lucide-react";
import { analyticsService } from "../services/analytics";
import { getErrorMessage } from "../services/api";
import { formatCount } from "../utils/format";

const percent = (rate) => (rate === null || rate === undefined ? "—" : `${Math.round(rate * 100)}%`);
const money = (value) => (value === null || value === undefined ? "Chưa có giá" : `$${value.toFixed(4)}`);
const dayLabel = (iso) => {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
};

// Executive overview (NEXORA Module 01). Loads independently from the
// account dashboard above it: a failure here never hides the base stats,
// and every number comes from the caller's real records.
export function ExecutivePanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async (signal) => {
    try {
      setData(await analyticsService.overview(signal));
      setError("");
    } catch (e) {
      if (e?.name !== "AbortError") setError(getErrorMessage(e));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (error) {
    return <section className="activity-panel" style={{ marginTop: 16 }}>
      <div className="section-heading"><h2>Tổng quan điều hành</h2></div>
      <p className="muted">{error}</p>
      <button className="icon-button" onClick={() => load()} aria-label="Thử lại tổng quan điều hành"><RefreshCw size={16} /></button>
    </section>;
  }
  if (!data) {
    return <section className="activity-panel" style={{ marginTop: 16 }} aria-busy="true">
      <div className="section-heading"><h2>Tổng quan điều hành</h2></div>
      <div className="activity-loading" role="status" aria-label="Đang tải tổng quan điều hành">
        {[1, 2].map((i) => <div key={i} className="skeleton activity-skeleton" />)}
      </div>
    </section>;
  }

  const tokens30 = data.usage_30d.input_tokens + data.usage_30d.output_tokens;
  const maxDay = Math.max(1, ...data.daily_14d.map((d) => d.input_tokens + d.output_tokens));
  const cards = [
    {
      label: "Workflow hoàn thành", icon: Workflow,
      value: `${data.workflows.by_status.completed || 0}/${data.workflows.total}`,
      caption: `Tỉ lệ thành công ${percent(data.workflows.success_rate)} · Thất bại ${data.workflows.by_status.failed || 0}`,
    },
    {
      label: "Task hoàn thành", icon: CheckCircle2,
      value: `${data.tasks.by_status.completed || 0}/${data.tasks.total}`,
      caption: `Tỉ lệ hoàn thành ${percent(data.tasks.completion_rate)}`,
    },
    {
      label: "Token 30 ngày", icon: Bot,
      value: formatCount(tokens30),
      caption: `${formatCount(data.usage_30d.requests)} lượt gọi AI · 7 ngày: ${formatCount(data.usage_7d.requests)} lượt`,
    },
    {
      label: "Chi phí ước tính 30 ngày", icon: Coins,
      value: money(data.usage_30d.cost_estimate),
      caption: data.usage_30d.unpriced_requests
        ? `${data.usage_30d.unpriced_requests} lượt chưa có giá model để tính`
        : "Tính từ giá model bạn đã đồng bộ",
    },
  ];

  return <>
    <div className="section-heading" style={{ marginTop: 22 }}>
      <h2><BarChart3 size={19} /> Tổng quan điều hành</h2>
      <span className="muted" style={{ fontSize: 12.5 }}>
        {data.agents_total} Agent ({data.agents_demo} demo) · {data.teams_total} nhóm ({data.teams_demo} demo) · AI Factory: {data.factory_runs.total} lượt chạy
      </span>
    </div>
    <section className="metrics-grid" aria-label="Tổng quan điều hành">
      {cards.map(({ label, icon: Icon, value, caption }) => <article className="metric" key={label}>
        <div className="metric-top"><span>{label}</span><Icon size={20} strokeWidth={1.6} /></div>
        <strong>{value}</strong><p>{caption}</p>
      </article>)}
    </section>
    <div className="dashboard-columns">
      <section className="activity-panel">
        <div className="section-heading"><h2>Theo model (30 ngày)</h2></div>
        {data.models_30d.length ? <ul className="activity-list">
          {data.models_30d.map((m) => <li key={`${m.provider}/${m.model}`}>
            <div><p>{m.provider} / {m.model}</p>
              <small className="muted">{formatCount(m.requests)} lượt · {formatCount(m.input_tokens + m.output_tokens)} token · {money(m.cost_estimate)}</small></div>
          </li>)}
        </ul> : <div className="empty-state"><p>Chưa có lượt gọi AI nào trong 30 ngày.</p></div>}
      </section>
      <section className="activity-panel">
        <div className="section-heading"><h2>Token 14 ngày gần nhất</h2></div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 110, padding: "6px 2px 0" }} role="img"
          aria-label="Biểu đồ token theo ngày trong 14 ngày gần nhất">
          {data.daily_14d.map((d) => {
            const total = d.input_tokens + d.output_tokens;
            return <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
              title={`${d.date}: ${formatCount(total)} token, ${d.requests} lượt`}>
              <div style={{ width: "100%", maxWidth: 22, height: `${Math.max(2, Math.round((total / maxDay) * 76))}px`, background: "var(--accent, #7c3aed)", borderRadius: 4, opacity: total ? 1 : 0.25 }} />
              <small className="muted" style={{ fontSize: 9.5 }}>{dayLabel(d.date)}</small>
            </div>;
          })}
        </div>
        <p className="muted" style={{ fontSize: 12 }}>Ngày tính theo UTC. Số liệu lấy từ usage provider ghi nhận thật.</p>
      </section>
    </div>
  </>;
}
