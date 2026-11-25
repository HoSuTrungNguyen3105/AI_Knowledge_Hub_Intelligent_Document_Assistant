"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowRight, Bot, Braces, Check, CircleAlert, Clock3, Coins,
  FileText, LibraryBig, ListChecks, MessagesSquare, RefreshCw, ShieldCheck,
} from "lucide-react";
import { useDashboard } from "../hooks/use-dashboard";
import { useSession } from "../stores/session";
import { analyticsService } from "../services/analytics";
import { getErrorMessage } from "../services/api";
import { formatActivity, formatCount, formatDate } from "../utils/format";
import { APP_STAGE } from "../utils/app-config";

const percent = (rate) =>
  rate === null || rate === undefined ? "—" : `${Math.round(rate * 100)}%`;
const money = (value) =>
  value === null || value === undefined ? "Chưa có giá" : `$${value.toFixed(4)}`;
const latency = (value) => {
  if (value === null || value === undefined) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(".", ",")} giây`;
  return `${Math.round(value)} ms`;
};
const dayLabel = (iso) => {
  const [, month, day] = String(iso).split("-");
  return `${day}/${month}`;
};
const DONUT_COLORS = ["#7c3aed", "#06b6d4", "#f59e0b", "#94a3b8"];

/* -------------------------------------------------- usage line chart */
function UsageChart({ series, range, onRange }) {
  const points = useMemo(
    () => (series || []).slice(-range),
    [series, range],
  );
  const total = points.reduce((sum, p) => sum + (p.requests || 0), 0);
  const peak = points.reduce(
    (best, p) => ((p.requests || 0) > (best?.requests || 0) ? p : best),
    null,
  );
  const W = 720;
  const H = 230;
  const padL = 36;
  const padR = 12;
  const padT = 14;
  const padB = 26;
  const max = Math.max(1, ...points.map((p) => p.requests || 0));
  const stepX = points.length > 1 ? (W - padL - padR) / (points.length - 1) : 0;
  const coords = points.map((p, i) => ({
    x: padL + i * stepX,
    y: padT + (1 - (p.requests || 0) / max) * (H - padT - padB),
    p,
  }));
  const line = coords.map((c) => `${c.x},${c.y}`).join(" ");
  const area = coords.length
    ? `M ${coords[0].x},${H - padB} L ${coords
        .map((c) => `${c.x},${c.y}`)
        .join(" L ")} L ${coords[coords.length - 1].x},${H - padB} Z`
    : "";
  const ticks = [0, 0.33, 0.66, 1];
  return (
    <section className="dash2-card">
      <div className="dash2-card-head">
        <h2>Nhịp sử dụng AI</h2>
        <div className="dash2-tabs" role="tablist" aria-label="Khoảng ngày">
          {[7, 14].map((days) => (
            <button
              key={days}
              type="button"
              role="tab"
              aria-selected={range === days}
              className={range === days ? "active" : ""}
              onClick={() => onRange(days)}
            >
              {days} ngày
            </button>
          ))}
        </div>
      </div>
      {series === null ? (
        <div className="skeleton dash2-chart-skeleton" />
      ) : points.length === 0 || total === 0 ? (
        <p className="muted dash2-empty">
          Chưa có lượt gọi AI nào trong {range} ngày qua — biểu đồ sẽ hiện
          khi bạn bắt đầu trò chuyện, so sánh hoặc chạy Agent.
        </p>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="dash2-chart"
            role="img"
            aria-label={`Lượt gọi AI theo ngày, tổng ${total} lượt`}
          >
            {ticks.map((t) => {
              const y = padT + (1 - t) * (H - padT - padB);
              return (
                <g key={t}>
                  <line x1={padL} y1={y} x2={W - padR} y2={y} className="dash2-grid-line" />
                  <text x={padL - 8} y={y + 4} className="dash2-axis" textAnchor="end">
                    {Math.round(max * t)}
                  </text>
                </g>
              );
            })}
            {area ? <path d={area} className="dash2-area" /> : null}
            <polyline points={line} className="dash2-line" />
            {coords.map((c) => (
              <circle key={c.p.date} cx={c.x} cy={c.y} r="3.2" className="dash2-dot-point" />
            ))}
            {coords.map((c, i) =>
              i % 2 === 0 || i === coords.length - 1 ? (
                <text
                  key={`label-${c.p.date}`}
                  x={c.x}
                  y={H - 8}
                  className="dash2-axis"
                  textAnchor="middle"
                >
                  {dayLabel(c.p.date)}
                </text>
              ) : null,
            )}
          </svg>
          <p className="dash2-chart-foot">
            <span className="dash2-legend-dot" /> Lượt gọi AI · Tổng {formatCount(total)} lượt
            {peak ? ` · Cao nhất ${formatCount(peak.requests)} lượt vào ${dayLabel(peak.date)}` : ""}
          </p>
        </>
      )}
    </section>
  );
}

/* -------------------------------------------------- model donut */
function ModelDonut({ models }) {
  const sorted = useMemo(
    () => [...(models || [])].sort((a, b) => b.requests - a.requests),
    [models],
  );
  const total = sorted.reduce((sum, m) => sum + (m.requests || 0), 0);
  const slices = useMemo(() => {
    if (!total) return [];
    const top = sorted.slice(0, 3).map((m) => ({
      name: `${m.provider}/${m.model}`,
      requests: m.requests,
    }));
    const rest = sorted.slice(3).reduce((sum, m) => sum + m.requests, 0);
    if (rest > 0) top.push({ name: "Khác", requests: rest });
    return top;
  }, [sorted, total]);
  const R = 64;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <section className="dash2-card">
      <div className="dash2-card-head">
        <h2>Lượt gọi theo model</h2>
        <span className="muted dash2-card-sub">30 ngày</span>
      </div>
      {models === null ? (
        <div className="skeleton dash2-chart-skeleton" />
      ) : total === 0 ? (
        <p className="muted dash2-empty">Chưa có lượt gọi AI nào trong 30 ngày qua.</p>
      ) : (
        <div className="dash2-donut-wrap">
          <svg viewBox="0 0 168 168" className="dash2-donut" role="img" aria-label="Phân bổ lượt gọi theo model">
            <circle cx="84" cy="84" r={R} className="dash2-donut-bg" />
            {slices.map((slice, i) => {
              const frac = slice.requests / total;
              const dash = `${Math.max(frac * C - 2, 0)} ${C}`;
              const current = offset;
              offset += frac * C;
              return (
                <circle
                  key={slice.name}
                  cx="84"
                  cy="84"
                  r={R}
                  fill="none"
                  stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
                  strokeWidth="22"
                  strokeDasharray={dash}
                  strokeDashoffset={-current}
                  transform="rotate(-90 84 84)"
                />
              );
            })}
            <text x="84" y="80" className="dash2-donut-total" textAnchor="middle">
              {formatCount(total)}
            </text>
            <text x="84" y="100" className="dash2-donut-label" textAnchor="middle">
              lượt gọi
            </text>
          </svg>
          <ul className="dash2-legend">
            {slices.map((slice, i) => (
              <li key={slice.name}>
                <span
                  className="dash2-legend-dot"
                  style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }}
                />
                <span className="dash2-legend-name" title={slice.name}>{slice.name}</span>
                <strong>{formatCount(slice.requests)}</strong>
                <span className="muted">{Math.round((slice.requests / total) * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------- dashboard */
export function Dashboard() {
  const user = useSession((state) => state.user);
  const { data, loading, error, retry } = useDashboard();
  const [ana, setAna] = useState(null);
  const [range, setRange] = useState(14);
  const firstName = user?.name?.trim().split(/\s+/).at(-1) || "bạn";

  useEffect(() => {
    const controller = new AbortController();
    analyticsService
      .overview(controller.signal)
      .then((result) => setAna(result))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const usage30 = ana?.usage_30d;
  const stats = [
    {
      label: "Tài liệu", icon: FileText, ready: !loading && data,
      value: data ? formatCount(data.total_documents) : "",
      caption: "Trong không gian của bạn",
    },
    {
      label: "Kho kiến thức", icon: LibraryBig, ready: !loading && data,
      value: data ? formatCount(data.total_knowledge_bases) : "",
      caption: "Các bộ sưu tập tài liệu",
    },
    {
      label: "Cuộc hội thoại", icon: MessagesSquare, ready: !loading && data,
      value: data ? formatCount(data.total_conversations) : "",
      caption: "Lịch sử trò chuyện với AI",
    },
    {
      label: "Lượt gọi AI · 30 ngày", icon: Activity, ready: Boolean(usage30),
      value: usage30 ? formatCount(usage30.requests) : "",
      caption: usage30
        ? `${formatCount(usage30.successful)} thành công · ${formatCount(usage30.failed)} lỗi`
        : "Đang tải từ analytics",
    },
    {
      label: "Token đã dùng · 30 ngày", icon: Coins, ready: Boolean(usage30),
      value: usage30
        ? formatCount((usage30.input_tokens || 0) + (usage30.output_tokens || 0))
        : "",
      caption: usage30 ? `Chi phí ước tính ${money(usage30.cost_estimate)}` : "Đang tải từ analytics",
    },
    {
      label: "Agent", icon: Bot, ready: Boolean(ana),
      value: ana ? formatCount(ana.agents_total) : "",
      caption: ana ? `${formatCount(ana.teams_total)} nhóm phối hợp` : "Đang tải từ analytics",
    },
  ];

  const todos = [];
  if (ana) {
    const wfFailed = ana.workflows?.by_status?.failed || 0;
    if (wfFailed > 0) {
      todos.push({ label: `${wfFailed} workflow thất bại cần xem lại`, href: "/agents/workflows" });
    }
    const fxFailed = ana.factory_runs?.by_status?.failed || 0;
    if (fxFailed > 0) {
      todos.push({ label: `${fxFailed} lượt chạy AI Factory lỗi`, href: "/agents/workflows?tab=factory" });
    }
    if ((ana.usage_7d?.failed || 0) > 0) {
      todos.push({ label: `${ana.usage_7d.failed} lượt gọi AI lỗi trong 7 ngày`, href: "/compare" });
    }
    const openTasks =
      (ana.tasks?.by_status?.pending || 0) +
      (ana.tasks?.by_status?.in_progress || 0) +
      (ana.tasks?.by_status?.running || 0);
    if (openTasks > 0) {
      todos.push({ label: `${openTasks} nhiệm vụ Agent đang chờ hoặc đang chạy`, href: "/agents/workflows" });
    }
  }

  return (
    <div className="dash2">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Không gian của riêng bạn</p>
          <h1>Xin chào, {firstName}.</h1>
          <p className="muted">Mọi tri thức quan trọng, cùng một nơi.</p>
        </div>
        <div className="dash2-head-actions">
          <span className="phase-badge"><span className="status-dot" />{APP_STAGE}</span>
          <Link className="button primary" href="/code-analyzer">
            <Braces size={16} /> Phân tích codebase
          </Link>
        </div>
      </div>

      {error ? (
        <div className="error-panel" role="alert">
          <CircleAlert size={24} />
          <div>
            <h2>Chưa tải được dữ liệu</h2>
            <p>{getErrorMessage(error)}</p>
          </div>
          <button className="button secondary" onClick={retry}>
            <RefreshCw size={16} />Thử lại
          </button>
        </div>
      ) : (
        <>
          <section className="dash2-stats" aria-label="Thống kê tài khoản">
            {stats.map(({ label, icon: Icon, ready, value, caption }) => (
              <article className="dash2-card dash2-stat" key={label}>
                <div className="dash2-stat-top">
                  <span>{label}</span>
                  <Icon size={19} strokeWidth={1.7} />
                </div>
                {ready ? <strong>{value}</strong> : <span className="skeleton dash2-stat-skeleton" />}
                <p>{caption}</p>
              </article>
            ))}
          </section>

          <div className="dash2-grid">
            <div className="dash2-main">
              <UsageChart
                series={ana ? ana.daily_14d : null}
                range={range}
                onRange={setRange}
              />
              <div className="dash2-subgrid">
                <ModelDonut models={ana ? ana.models_30d : null} />
                <section className="dash2-card">
                  <div className="dash2-card-head">
                    <h2>Hoạt động gần đây</h2>
                    <button
                      className="icon-button"
                      onClick={retry}
                      disabled={loading}
                      aria-label="Làm mới hoạt động"
                    >
                      <RefreshCw size={16} className={loading ? "spin" : ""} />
                    </button>
                  </div>
                  {loading || !data ? (
                    <div className="activity-loading" role="status" aria-label="Đang tải hoạt động">
                      {[1, 2, 3].map((i) => <div key={i} className="skeleton activity-skeleton" />)}
                    </div>
                  ) : data.recent_activity.length > 0 ? (
                    <ul className="activity-list">
                      {data.recent_activity.slice(0, 6).map((item) => (
                        <li key={item.id}>
                          <span className="activity-symbol"><ShieldCheck size={17} /></span>
                          <div>
                            <p>{formatActivity(item)}</p>
                            <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="empty-state">
                      <Clock3 size={28} />
                      <p>Chưa có hoạt động nào.</p>
                      <small>Các hoạt động của bạn sẽ xuất hiện ở đây.</small>
                    </div>
                  )}
                </section>
              </div>
            </div>

            <aside className="dash2-rail">
              <section className="dash2-card">
                <div className="dash2-card-head">
                  <h2 className="dash2-panel-title">
                    <ListChecks size={18} /> Việc cần làm
                  </h2>
                  {ana && todos.length > 0 ? (
                    <span className="dash2-count">{todos.length}</span>
                  ) : null}
                </div>
                {ana === null ? (
                  <div className="skeleton dash2-chart-skeleton" />
                ) : todos.length > 0 ? (
                  <div className="dash2-todos">
                    {todos.map((todo) => (
                      <Link key={todo.label} href={todo.href} className="dash2-todo">
                        <span>{todo.label}</span>
                        <ArrowRight size={15} />
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="muted dash2-empty">
                    Không có việc nào cần xử lý — mọi workflow và lượt gọi AI
                    gần đây đều ổn.
                  </p>
                )}
              </section>

              <section className="dash2-card">
                <div className="dash2-card-head">
                  <h2>Thao tác nhanh</h2>
                </div>
                <div className="dash2-quick">
                  <Link className="button primary dash2-quick-main" href="/code-analyzer">
                    <Braces size={17} /> Phân tích codebase
                  </Link>
                  <Link className="button secondary" href="/chat">
                    <MessagesSquare size={16} /> Trò chuyện AI
                  </Link>
                  <Link className="button secondary" href="/agents">
                    <Bot size={16} /> Agent Studio
                  </Link>
                </div>
              </section>

              <section className="dash2-card">
                <div className="dash2-card-head">
                  <h2>Trạng thái</h2>
                </div>
                <div className="dash2-status">
                  <div>
                    <span>API dữ liệu</span>
                    <strong className="dash2-ok">
                      <span className="dash2-dot" /> Đang hoạt động
                    </strong>
                  </div>
                  <div>
                    <span>Giai đoạn</span>
                    <strong>{APP_STAGE}</strong>
                  </div>
                  <div>
                    <span>Tỉ lệ workflow thành công</span>
                    <strong>{percent(ana?.workflows?.success_rate)}</strong>
                  </div>
                  <div>
                    <span>Độ trễ TB · 30 ngày</span>
                    <strong>{latency(usage30?.avg_latency_ms)}</strong>
                  </div>
                  <div>
                    <span>Chi phí ước tính · 30 ngày</span>
                    <strong>{money(usage30?.cost_estimate)}</strong>
                  </div>
                </div>
                <div className="dash2-foundation">
                  <p><span className="check-icon"><Check size={13} /></span>Tài khoản cá nhân — đã đăng nhập và xác thực</p>
                  <p><span className="check-icon"><Check size={13} /></span>Không gian riêng tư — dữ liệu phân quyền theo tài khoản</p>
                  <p><span className="check-icon"><Check size={13} /></span>Chat, Compare và Agent Studio — đã sẵn sàng</p>
                </div>
              </section>
            </aside>
          </div>

          <p className="data-note">
            <ShieldCheck size={14} />
            Số liệu được lấy trực tiếp từ cơ sở dữ liệu của tài khoản, không sử dụng dữ liệu mẫu.
          </p>
        </>
      )}
    </div>
  );
}
