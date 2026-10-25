import { useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { fetchPortfolioSimulation } from "../api";
import { comparisonPoints, simulationIsStale, simulationTradeHistory, simulationAnalysisHistory,
  simulationMoney as money, simulationPercent as percent,
  type PortfolioSimulationData, type SimulationDecision, type SimulationPosition } from "../portfolioSimulation";
import "../portfolioSimulation.css";
const dateLabel = (day: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(new Date(day));
const quantity = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(value);
const allocation = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value);
const headlineMoney = (value: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
const label = (value: string) => value.toLowerCase().replace(/_/g, " ");

function ComparisonChart({ data, onTradeSelect }: { data: PortfolioSimulationData; onTradeSelect: () => void }) {
  const points = comparisonPoints(data);
  const [selected, setSelected] = useState<number | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(620);
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(280, entries[0].contentRect.width)));
    if (chartRef.current) observer.observe(chartRef.current);
    return () => observer.disconnect();
  }, []);
  if (!points.length) return <p className="simulation-hint">No comparison history yet.</p>;
  const index = Math.min(selected ?? points.length - 1, points.length - 1);
  const point = points[index];
  const height = width < 480 ? 240 : Math.round(width * .47), pad = { left: 62, right: 28, top: 24, bottom: 32 };
  const values = points.flatMap(p => [p.strategy.equity, p.vwce.equity]);
  const low = Math.min(...values), high = Math.max(...values), spread = Math.max(high - low, data.metadata.initial_capital * .01);
  const min = low - spread * .15, max = high + spread * .15;
  const x = (i: number) => pad.left + (points.length === 1 ? .5 : i / (points.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (max - value) / (max - min) * (height - pad.top - pad.bottom);
  const path = (key: "strategy" | "vwce") => points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[key].equity)}`).join(" ");
  const selectX = (clientX: number, rect: DOMRect) => setSelected(Math.min(points.length - 1, Math.max(0,
    Math.round((((clientX - rect.left) / rect.width) * width - pad.left) / (width - pad.left - pad.right) * (points.length - 1)))));
  const ticks = [...new Set([0, Math.round((points.length - 1) / 3), Math.round(2 * (points.length - 1) / 3), points.length - 1])];
  return <div className="simulation-chart" ref={chartRef}>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="InvestOS versus VWCE portfolio value in EUR"
      onPointerDown={e => {
        if ((e.target as Element).closest(".simulation-trade-marker")) return;
        e.currentTarget.setPointerCapture(e.pointerId); selectX(e.clientX, e.currentTarget.getBoundingClientRect());
      }}
      onPointerMove={e => { if (e.buttons) selectX(e.clientX, e.currentTarget.getBoundingClientRect()); }}>
      {[0, .25, .5, .75, 1].map(part => <g key={part}>
        <line x1={pad.left} x2={width - pad.right} y1={pad.top + part * (height - pad.top - pad.bottom)} y2={pad.top + part * (height - pad.top - pad.bottom)} className="simulation-grid" />
        <text x={pad.left - 10} y={pad.top + part * (height - pad.top - pad.bottom) + 4} textAnchor="end">{new Intl.NumberFormat(undefined, { style: "currency", currency: "EUR", notation: max - min >= 1000 ? "compact" : "standard", maximumFractionDigits: max - min >= 1000 ? 1 : 0 }).format(max - part * (max - min))}</text>
      </g>)}
      <path d={path("strategy")} className="simulation-line simulation-strategy" />
      <path d={path("vwce")} className="simulation-line simulation-vwce" />
      {selected != null && <line x1={x(index)} x2={x(index)} y1={pad.top} y2={height - pad.bottom} className="simulation-cursor" />}
      <circle cx={x(index)} cy={y(point.strategy.equity)} r="4" className="simulation-dot simulation-strategy" />
      <circle cx={x(index)} cy={y(point.vwce.equity)} r="4" className="simulation-dot simulation-vwce" />
      {data.transactions.filter(t => t.portfolio_id === "strategy" && (t.type === "BUY" || t.type === "SELL")).map(t => {
        const i = points.findIndex(p => p.date === t.execution_date);
        return i < 0 ? null : <g key={t.id} className="simulation-trade-marker" role="button" tabIndex={0} aria-label={`${t.type} ${t.symbol} on ${t.execution_date}`}
          onClick={e => { e.stopPropagation(); setSelected(i); onTradeSelect(); }} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(i); onTradeSelect(); } }}>
          <title>{t.type} {t.symbol} · {dateLabel(t.execution_date)}</title><circle cx={x(i)} cy={y(points[i].strategy.equity)} r="8" />
          <text x={x(i)} y={y(points[i].strategy.equity) + 3} textAnchor="middle">{t.type[0]}</text>
        </g>;
      })}
      {ticks.map(i => <text key={i} x={x(i)} y={height - 9} textAnchor="middle">{new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(points[i].date))}</text>)}
    </svg>
    <input className="simulation-chart-range" type="range" min="0" max={Math.max(0, points.length - 1)} value={index} disabled={points.length === 1}
      aria-label="Portfolio history date" aria-valuetext={dateLabel(point.date)} onFocus={() => setSelected(index)} onChange={e => setSelected(Number(e.target.value))} />
    <div className="simulation-legend"><span><i className="simulation-strategy-key" />InvestOS</span><span><i className="simulation-vwce-key" />VWCE</span></div>
    {selected != null && <div className="simulation-selected" aria-live="polite">
      <span>{dateLabel(point.date)}</span><span>InvestOS {money(point.strategy.equity)}</span><span>VWCE {money(point.vwce.equity)}</span>
      <button type="button" onClick={() => setSelected(null)} aria-label="Clear chart selection">×</button>
    </div>}
  </div>;
}

function Position({ position: p }: { position: SimulationPosition }) {
  return <article className="simulation-position">
    <header><strong>{p.name} <small>{p.symbol}</small></strong><span>{p.status === "open" ? p.market_value == null ? "—" : money(p.market_value) : percent(p.realized_return_pct)}</span></header>
    <dl className="simulation-facts">
      <div><dt>Purchased</dt><dd>{dateLabel(p.entry_date)}</dd></div>
      <div><dt>Average buy price</dt><dd>{money(p.entry_price, p.currency)}</dd></div>
      <div><dt>Invested including fees</dt><dd>{money(p.invested_capital)}</dd></div>
      {p.status === "open" ? <>
        <div><dt>Shares</dt><dd>{quantity(p.quantity)}</dd></div>
        <div><dt>Latest close</dt><dd>{p.current_price == null ? "—" : money(p.current_price, p.currency)}{p.price_date && <small>{dateLabel(p.price_date)}</small>}</dd></div>
        <div><dt>Unrealized result</dt><dd>{p.unrealized_pnl == null ? "—" : money(p.unrealized_pnl)} · {percent(p.unrealized_return_pct)}</dd></div>
      </> : <>
        <div><dt>Sold</dt><dd>{p.exit_date && dateLabel(p.exit_date)}</dd></div>
        <div><dt>Sale price</dt><dd>{p.exit_price == null ? "—" : money(p.exit_price, p.currency)}</dd></div>
        <div><dt>Net proceeds</dt><dd>{money(p.sale_proceeds)}</dd></div>
        <div><dt>Realized result</dt><dd>{money(p.realized_pnl)} · {percent(p.realized_return_pct)}</dd></div>
        <div><dt>Held</dt><dd>{p.holding_days} days</dd></div>
      </>}
      <div><dt>Trading fees</dt><dd>{money(p.fees)}</dd></div>
      <div><dt>Cash dividends</dt><dd>{money(p.dividends)}</dd></div>
    </dl>
    {p.replaced_by && <p>Replaced by {p.replaced_by}.</p>}
    {p.replacement_of_symbol && <p>Replacement for {p.replacement_of_symbol}.</p>}
    {p.exit_reason && <p>{p.exit_reason}</p>}
    {p.status === "open" && <details><summary>Investment thesis · {p.thesis_status}</summary>
      {p.last_assessment_date && <small>Reviewed {dateLabel(p.last_assessment_date)}</small>}<p>{p.last_explanation ?? "No completed AI review is available."}</p>
    </details>}
  </article>;
}

function AnalysisDecision({ decision: d }: { decision: SimulationDecision }) {
  const assessment = d.assessment;
  return <article className="simulation-analysis-decision" id={d.id}>
    <header><strong>{d.symbol ?? "Portfolio"}</strong><span>{label(d.action)} · {label(d.execution_status)}</span></header>
    <p>{assessment?.explanation ?? d.explanation}</p>
    {assessment && <details className="simulation-evidence"><summary>Full analysis</summary>
      {assessment.investment_assessment && <p>Investment case: {label(assessment.investment_assessment)} · Thesis {label(assessment.thesis_status)}</p>}
      {assessment.business_assessment && <p>{assessment.business_assessment}</p>}
      {assessment.valuation_assessment && <p>{assessment.valuation_assessment}</p>}
      {assessment.principal_risks.length > 0 && <><h5>Risks</h5><ul>{assessment.principal_risks.map((risk, i) => <li key={i}>{risk}</li>)}</ul></>}
      {assessment.evidence.length > 0 && <><h5>Evidence</h5>{assessment.evidence.map((e, i) => <p key={i}>{e.explanation}<small>{e.reference_id}</small></p>)}</>}
      <small>{d.model} · {dateLabel(d.analysis_date)}{d.financial_as_of ? ` · Financials ${dateLabel(d.financial_as_of)}` : ""}</small>
    </details>}
  </article>;
}

const reviewStatus = (status?: string | null) => {
  switch (status) {
    case "success": return "Reviewed";
    case "not_needed": return "No review needed";
    case "missing_api_key": return "AI not configured";
    case "failed": return "Review failed";
    case "indeterminate": return "Review incomplete";
    case "expired": return "Review expired";
    case "ready": case "attempted": return "Review pending";
    default: return "No AI review";
  }
};

export function PortfolioSimulation() {
  const [data, setData] = useState<PortfolioSimulationData | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tradeLimit, setTradeLimit] = useState(15);
  const [analysisLimit, setAnalysisLimit] = useState(15);
  const [revision, setRevision] = useState(0);
  const historyRef = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    let active = true; setLoading(true); setError(false);
    fetchPortfolioSimulation().then(next => {
      if (next.schema_version !== 1 || !comparisonPoints(next).length) throw new Error("Invalid simulation data");
      if (active) setData(next);
    }).catch(() => { if (active) setError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  if (loading) return <section className="portfolio-simulation" aria-label="InvestOS simulation"><p role="status">Loading performance…</p></section>;
  if (error || !data) return <section className="portfolio-simulation" aria-label="InvestOS simulation"><p role="alert">Performance could not be loaded.</p><button type="button" onClick={() => setRevision(v => v + 1)}>Retry</button></section>;
  const strategy = data.portfolios.strategy;
  const positions = strategy.positions.filter(p => p.status === "open");
  const tradeDays = simulationTradeHistory(data);
  const analysisDays = simulationAnalysisHistory(data);
  const tradeCount = tradeDays.reduce((total, day) => total + day.trades.length, 0);
  const investedPct = strategy.equity > 0 ? Math.max(0, Math.min(100, strategy.invested_value / strategy.equity * 100)) : 0;
  const difference = strategy.cumulative_return_pct - data.portfolios.vwce.cumulative_return_pct;
  const stale = simulationIsStale(data.metadata);
  const status = stale ? "Updates delayed"
    : data.metadata.status === "awaiting_api_key" ? "AI not configured"
    : data.metadata.status === "analysis_error" ? "AI review incomplete"
    : data.metadata.status === "accounting_error" ? "Portfolio update needs review"
    : data.metadata.status === "initialized" || data.metadata.status === "awaiting_market_session" ? "Waiting for the first market session"
    : data.metadata.status === "analysis_pending" ? "Daily review in progress" : null;
  return <section className="portfolio-simulation" aria-label="InvestOS versus VWCE simulation">
    <div className="simulation-overview">
      <header className="simulation-heading"><h2>Performance comparison</h2><span className="simulation-badge">Paper</span></header>
      <div className="simulation-summary">
        {(["strategy", "vwce"] as const).map(key => <div key={key} className="simulation-total">
          <span>{key === "strategy" ? "InvestOS" : "VWCE"}</span><strong>{headlineMoney(data.portfolios[key].equity)}</strong>
          <small className={data.portfolios[key].cumulative_return_pct < 0 ? "simulation-negative" : "simulation-positive"}>{percent(data.portfolios[key].cumulative_return_pct)}</small>
        </div>)}
      </div>
      <ComparisonChart data={data} onTradeSelect={() => {
        if (historyRef.current) historyRef.current.open = true;
        requestAnimationFrame(() => historyRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      }} />
      {status && <p className="simulation-status" role="status">{status}</p>}
      <details className="simulation-methodology"><summary>Since {dateLabel(data.metadata.start_date)}{data.metadata.latest_successful_update ? ` · Updated ${dateLabel(data.metadata.latest_successful_update)}` : ""}</summary>
        <dl className="simulation-facts">
          {[["Cash", money(strategy.cash)], ["Realized result", money(strategy.realized_pnl)], ["Unrealized result", money(strategy.unrealized_pnl)],
            ["Dividends", money(strategy.dividends)], ["Trading fees", money(strategy.fees)], ["VWCE trading fees", money(data.portfolios.vwce.fees)],
            ["Max. drawdown", percent(strategy.performance.max_drawdown_pct)], ["Annualized return", percent(strategy.performance.annualized_return_pct)],
            ["AI costs (estimated)", money(data.ai_costs.estimated_usd, "USD")]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}
        </dl>
        <p>Paper portfolio · Returns include {allocation(data.metadata.transaction_fee_rate * 100)}% trading fees. AI costs are separate; taxes and additional execution costs are excluded. Dividend coverage may be incomplete.</p>
        <p>Last AI review: {data.metadata.last_successful_analysis ? dateLabel(data.metadata.last_successful_analysis) : "Not run"}.</p>
        {strategy.stale_symbols.length > 0 && <p>Carried-forward prices: {strategy.stale_symbols.join(", ")}.</p>}
        {!data.ai_costs.complete && <p>AI cost estimate is incomplete.</p>}
        <details className="simulation-evidence"><summary>AI usage</summary>{data.ai_usage.length ? data.ai_usage.map(u => <p key={u.id}>{dateLabel(u.session)} · {label(u.status)} · {u.usage?.input_tokens ?? "Unknown"} input / {u.usage?.output_tokens ?? "Unknown"} output tokens · {u.estimated_cost_usd == null ? "Cost unknown" : money(u.estimated_cost_usd, "USD")}</p>) : <p>No API usage recorded.</p>}</details>
      </details>
      <div className="simulation-comparison"><span>InvestOS vs VWCE</span><strong className={difference < 0 ? "simulation-negative" : "simulation-positive"}>{new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(difference)} pp</strong></div>
      <div className="simulation-allocation">
        <div><span>Invested</span><strong>{headlineMoney(strategy.invested_value)}</strong></div>
        <div className="simulation-allocation-bar" role="img" aria-label={`${allocation(investedPct)}% invested, ${allocation(100 - investedPct)}% cash`}><span style={{ width: `${investedPct}%` }} /></div>
        <div className="simulation-allocation-labels"><span>{allocation(investedPct)}% invested</span><span>{allocation(100 - investedPct)}% cash</span></div>
      </div>
      <details className="simulation-section"><summary><strong>Holdings</strong><span>{positions.length} {positions.length === 1 ? "position" : "positions"}<ChevronRight size={18} /></span></summary>
        {positions.length ? positions.map(p => <Position key={p.id} position={p} />) : <p className="simulation-hint">No holdings yet.</p>}
        {data.orders.some(o => o.portfolio_id === "strategy" && o.status === "pending") && <details className="simulation-evidence"><summary>Pending orders</summary>{data.orders.filter(o => o.portfolio_id === "strategy" && o.status === "pending").map(o => <p key={o.id}>{label(o.type)} {o.symbol} · Awaiting execution</p>)}</details>}
      </details>
    </div>
    <details className="simulation-section simulation-history" ref={historyRef}>
      <summary><strong>History</strong><span>{tradeCount} {tradeCount === 1 ? "trade" : "trades"}<ChevronRight size={18} /></span></summary>
      {!tradeDays.length && <p className="simulation-hint">No executed trades yet.</p>}
      {tradeDays.slice(0, tradeLimit).map(day => <section className="simulation-day" key={day.date}>
        <h3>{dateLabel(day.date)}</h3>
        {day.trades.map(t => <details className="simulation-trade" key={t.id} id={t.id}>
          <summary><span className={`simulation-trade-side ${t.type === "BUY" ? "simulation-positive" : "simulation-negative"}`}>{label(t.type)}</span><span className="simulation-trade-stock"><strong>{t.symbol}</strong><small>{quantity(t.quantity)} shares · {money(t.execution_price, t.price_currency)}</small></span><strong>{money(t.gross_eur)}</strong><ChevronRight size={16} /></summary>
          <div className="simulation-trade-detail"><p>{t.rationale}</p><p>Fees {money(t.fees_eur)} · Cash movement {money(t.net_cash_eur)}</p>
            {t.realized_pnl_eur != null && <p>Realized result {money(t.realized_pnl_eur)}</p>}
            <p>EUR conversion {quantity(t.fx_to_eur)} · {dateLabel(t.fx_date)}</p><small>{t.price_source} · {t.fx_source}</small>
            {t.position_id && strategy.positions.filter(p => p.id === t.position_id && p.status === "closed").map(p => <Position key={p.id} position={p} />)}
          </div>
        </details>)}
      </section>)}
      {tradeDays.length > tradeLimit && <button type="button" className="simulation-more" onClick={() => setTradeLimit(v => v + 15)}>Show more trades</button>}
    </details>
    <details className="simulation-section simulation-history">
      <summary><strong>Analysis history</strong><span>{analysisDays.length} {analysisDays.length === 1 ? "day" : "days"}<ChevronRight size={18} /></span></summary>
      {!analysisDays.length && <p className="simulation-hint">No daily analysis yet.</p>}
      {analysisDays.slice(0, analysisLimit).map(day => <details className="simulation-analysis-day" key={day.date}>
        <summary><strong>{dateLabel(day.date)}</strong><span>{reviewStatus(day.review?.status)}<ChevronRight size={16} /></span></summary>
        <div className="simulation-analysis-content">
          <h4>Deterministic picks</h4>
          {day.review?.candidates ? day.review.candidates.length ? <div className="simulation-picks">{day.review.candidates.map(symbol => <span key={symbol}>{symbol}</span>)}</div> : <p className="simulation-hint">No qualifying picks.</p> : <p className="simulation-hint">Picks were not recorded for this day.</p>}
          {day.review && <small>{day.review.screened_count} screened · {day.review.eligible_count} eligible</small>}
          <h4>AI analysis</h4>
          {!day.decisions.some(d => d.assessment) && <p className="simulation-hint">{reviewStatus(day.review?.status)}.{day.review?.status === "not_needed" ? " No qualifying candidates or holdings to review." : ""}</p>}
          {day.decisions.map(d => <AnalysisDecision key={d.id} decision={d} />)}
        </div>
      </details>)}
      {analysisDays.length > analysisLimit && <button type="button" className="simulation-more" onClick={() => setAnalysisLimit(v => v + 15)}>Show more days</button>}
    </details>
  </section>;
}
