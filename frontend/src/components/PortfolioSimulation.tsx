import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { fetchPortfolioSimulation } from "../api";
import { comparisonPoints, simulationIsStale, simulationMoney as money, simulationPercent as percent,
  type PortfolioSimulationData, type SimulationPosition } from "../portfolioSimulation";
import "../portfolioSimulation.css";
const dateLabel = (day: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(new Date(day));
const quantity = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(value);

function ComparisonChart({ data, openDetails }: { data: PortfolioSimulationData; openDetails: () => void }) {
  const points = comparisonPoints(data);
  const [selected, setSelected] = useState<number | null>(null);
  if (!points.length) return <p className="simulation-hint">No paired portfolio history is available.</p>;
  const index = Math.min(selected ?? points.length - 1, points.length - 1);
  const point = points[index];
  const width = 620, height = 240, pad = { left: 64, right: 16, top: 22, bottom: 30 };
  const values = points.flatMap(p => [p.strategy.equity, p.vwce.equity]);
  const low = Math.min(...values), high = Math.max(...values), spread = Math.max(high - low, data.metadata.initial_capital * .01);
  const min = low - spread * .15, max = high + spread * .15;
  const x = (i: number) => pad.left + (points.length === 1 ? .5 : i / (points.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (max - value) / (max - min) * (height - pad.top - pad.bottom);
  const path = (key: "strategy" | "vwce") => points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[key].equity)}`).join(" ");
  const selectX = (clientX: number, rect: DOMRect) => setSelected(Math.min(points.length - 1, Math.max(0,
    Math.round((((clientX - rect.left) / rect.width) * width - pad.left) / (width - pad.left - pad.right) * (points.length - 1)))));
  return <div className="simulation-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="InvestOS Strategy versus VWCE portfolio value in EUR"
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); selectX(e.clientX, e.currentTarget.getBoundingClientRect()); }}
      onPointerMove={e => { if (e.buttons) selectX(e.clientX, e.currentTarget.getBoundingClientRect()); }}>
      {[0, .5, 1].map(part => <g key={part}>
        <line x1={pad.left} x2={width - pad.right} y1={pad.top + part * (height - pad.top - pad.bottom)} y2={pad.top + part * (height - pad.top - pad.bottom)} className="simulation-grid" />
        <text x={pad.left - 8} y={pad.top + part * (height - pad.top - pad.bottom) + 4} textAnchor="end">{new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(max - part * (max - min))}</text>
      </g>)}
      <path d={path("vwce")} className="simulation-line simulation-vwce" />
      <path d={path("strategy")} className="simulation-line simulation-strategy" onClick={openDetails} />
      <line x1={x(index)} x2={x(index)} y1={pad.top} y2={height - pad.bottom} className="simulation-cursor" />
      <circle cx={x(index)} cy={y(point.vwce.equity)} r="5" className="simulation-dot simulation-vwce" />
      <circle cx={x(index)} cy={y(point.strategy.equity)} r="4" className="simulation-dot simulation-strategy" />
      {data.transactions.filter(t => t.portfolio_id === "strategy" && (t.type === "BUY" || t.type === "SELL")).map(t => {
        const i = points.findIndex(p => p.date === t.execution_date);
        return i < 0 ? null : <g key={t.id} className="simulation-trade-marker" role="button" tabIndex={0} aria-label={`${t.type} ${t.symbol} on ${t.execution_date}`}
          onClick={() => { setSelected(i); openDetails(); }} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(i); openDetails(); } }}>
          <title>{t.type} {t.symbol} · {dateLabel(t.execution_date)}</title><circle cx={x(i)} cy={y(points[i].strategy.equity)} r="8" />
          <text x={x(i)} y={y(points[i].strategy.equity) + 3} textAnchor="middle">{t.type[0]}</text>
        </g>;
      })}
      <text x={pad.left} y={height - 8}>{dateLabel(points[0].date)}</text>
      {points.length > 1 && <text x={width - pad.right} y={height - 8} textAnchor="end">{dateLabel(points[points.length - 1].date)}</text>}
    </svg>
    <input type="range" min="0" max={Math.max(0, points.length - 1)} value={index} disabled={points.length === 1}
      aria-label="Portfolio history date" aria-valuetext={dateLabel(point.date)} onChange={e => setSelected(Number(e.target.value))} />
    <div className="simulation-selected" aria-live="polite">
      <strong>{dateLabel(point.date)}</strong>
      <span>VWCE {money(point.vwce.equity)} · {percent(point.vwce.cumulative_return_pct)}</span>
      <span>InvestOS {money(point.strategy.equity)} · {percent(point.strategy.cumulative_return_pct)}</span>
      <small>Difference {new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(point.strategy.cumulative_return_pct - point.vwce.cumulative_return_pct)} pp</small>
    </div>
    {points.length === 1 && <p className="simulation-hint">History starts here. Future market sessions will add points.</p>}
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

export function PortfolioSimulation() {
  const [data, setData] = useState<PortfolioSimulationData | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(false);
  const [tab, setTab] = useState<"performance" | "holdings" | "history">("performance");
  const [limit, setLimit] = useState(25);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true; setLoading(true); setError(false);
    fetchPortfolioSimulation().then(next => {
      if (next.schema_version !== 1 || !comparisonPoints(next).length) throw new Error("Invalid simulation data");
      if (active) setData(next);
    }).catch(() => { if (active) setError(true); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  if (loading) return <section className="portfolio-simulation" aria-label="InvestOS simulation"><p role="status">Loading portfolio simulation…</p></section>;
  if (error || !data) return <section className="portfolio-simulation" aria-label="InvestOS simulation"><p role="alert">Portfolio simulation data could not be loaded.</p><button type="button" onClick={() => setRevision(v => v + 1)}>Retry simulation</button></section>;
  const strategy = data.portfolios.strategy;
  const positions = strategy.positions;
  const timeline = [...data.decisions.map(d => ({ id: d.id, date: d.analysis_date, kind: "decision" as const, value: d })),
    ...data.transactions.filter(t => t.portfolio_id === "strategy").map(t => ({ id: t.id, date: t.execution_timestamp, kind: "transaction" as const, value: t }))]
    .sort((a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id));
  const latestReview = data.reviews[data.reviews.length - 1];
  const stale = simulationIsStale(data.metadata);
  const status = stale ? "Updates are delayed. Values below reflect the recorded dates."
    : data.metadata.status === "awaiting_api_key" ? "AI analysis is not configured yet."
    : data.metadata.status === "analysis_error" ? "The latest AI review did not complete. Existing investments are retained."
    : data.metadata.status === "accounting_error" ? "The latest portfolio update needs review. The previous ledger is preserved."
    : data.metadata.status === "initialized" || data.metadata.status === "awaiting_market_session" ? "Waiting for the first eligible market session."
    : data.metadata.status === "analysis_pending" ? "The daily investment review is in progress." : null;
  return <section className="portfolio-simulation" aria-label="InvestOS versus VWCE simulation">
    <header className="simulation-heading"><h2>INVESTOS VS VWCE</h2><p>Paper simulation · EUR · Since {dateLabel(data.metadata.start_date)}</p></header>
    <div className="simulation-summary">
      {(["vwce", "strategy"] as const).map(key => key === "vwce" ? <div key={key} className="simulation-total simulation-vwce"><span>VWCE</span><strong>{money(data.portfolios.vwce.equity)}</strong><small>{percent(data.portfolios.vwce.cumulative_return_pct)} since inception</small></div> : <button type="button" key={key} className={`simulation-total simulation-${key}`} onClick={() => { setDetail(true); setTab("performance"); }}>
        <span>{"InvestOS Strategy"}</span><strong>{money(data.portfolios[key].equity)}</strong><small>{percent(data.portfolios[key].cumulative_return_pct)} since inception</small>
      </button>)}
    </div>
    <ComparisonChart data={data} openDetails={() => setDetail(true)} />
    <div className="simulation-update">
      {status && <p role="status">{status}</p>}
      <small>Last portfolio update: {data.metadata.latest_successful_update ? dateLabel(data.metadata.latest_successful_update) : "No market session processed"}</small>
      <small>Last successful AI review: {data.metadata.last_successful_analysis ? dateLabel(data.metadata.last_successful_analysis) : "Not run"}</small>
      {strategy.stale_symbols.length > 0 && <small>Latest available prices carried forward: {strategy.stale_symbols.join(", ")}.</small>}
      {latestReview?.message && <small>{latestReview.message.replace(/OPENAI_API_KEY is not configured\./, "AI analysis is not configured.")}</small>}
    </div>
    {!detail ? <button type="button" className="simulation-open" onClick={() => setDetail(true)}>InvestOS Strategy details <ChevronRight size={18} /></button> : <div className="simulation-detail">
      <header><button type="button" className="simulation-back" onClick={() => setDetail(false)}><ArrowLeft size={18} />Close details</button><h3>InvestOS Strategy</h3></header>
      <div className="simulation-detail-tabs" aria-label="Strategy detail sections">
        {(["performance", "holdings", "history"] as const).map(key => <button type="button" key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{key === "performance" ? "Performance" : key === "holdings" ? "Holdings" : "History"}</button>)}
      </div>
      {tab === "performance" && <>
        <dl className="simulation-facts">
          {[["Portfolio value", money(strategy.equity)], ["Cash", money(strategy.cash)], ["Invested value", money(strategy.invested_value)],
            ["Total return", percent(strategy.cumulative_return_pct)], ["Realized gains / losses", money(strategy.realized_pnl)], ["Unrealized gains / losses", money(strategy.unrealized_pnl)],
            ["Cash dividends", money(strategy.dividends)], ["Strategy trading fees", money(strategy.fees)], ["VWCE trading fees", money(data.portfolios.vwce.fees)],
            ["Maximum drawdown", percent(strategy.performance.max_drawdown_pct)], ["Annualized return", strategy.performance.annualized_return_pct == null ? "Requires one year of history" : percent(strategy.performance.annualized_return_pct)],
            ["AI expenses (estimated)", money(data.ai_costs.estimated_usd, "USD")]].map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}
        </dl>
        <p className="simulation-hint">Investment returns include 0.10% per purchase or sale. AI operating expenses are separate and have not been deducted. Taxes and additional execution costs are excluded.</p>
        <p className="simulation-hint">Reported cash dividends are credited on the ex-date. Corporate-action coverage may be incomplete; these results are not guaranteed complete total returns.</p>
        {!data.ai_costs.complete && <p className="simulation-hint">Some AI expenses are unknown; the displayed estimate is incomplete.</p>}
        <details><summary>AI usage</summary>{data.ai_usage.length ? data.ai_usage.map(u => <p key={u.id}>{dateLabel(u.session)} · {u.status} · {u.usage?.input_tokens ?? "Unknown"} input / {u.usage?.output_tokens ?? "Unknown"} output tokens · {u.estimated_cost_usd == null ? "Cost unknown" : money(u.estimated_cost_usd, "USD")}</p>) : <p>No API usage recorded.</p>}</details>
      </>}
      {tab === "holdings" && <>
        {positions.filter(p => p.status === "open").length ? positions.filter(p => p.status === "open").map(p => <Position key={p.id} position={p} />) : <p className="simulation-hint">No stocks are currently held. Available cash: {money(strategy.cash)}.</p>}
        {data.orders.some(o => o.status === "pending") && <details><summary>Pending simulated orders</summary>{data.orders.filter(o => o.status === "pending").map(o => <p key={o.id}>{o.type} {o.symbol} · Awaiting a valid session after {dateLabel(o.market_cutoff)}. {o.rationale}</p>)}</details>}
      </>}
      {tab === "history" && <>
        {positions.filter(p => p.status === "closed").map(p => <Position key={p.id} position={p} />)}
        <h4>Investment timeline</h4>
        {!timeline.length && <p className="simulation-hint">No strategy transactions or investment decisions have been recorded yet.</p>}
        <ol className="simulation-timeline">{timeline.slice(0, limit).map(event => <li key={event.id} id={event.id}>
          <small>{dateLabel(event.date)}</small>
          {event.kind === "transaction" ? <>
            <strong>{event.value.type} · {event.value.symbol} · Executed</strong>
            <p>{quantity(event.value.quantity)} shares · {money(event.value.execution_price, event.value.price_currency)} · Cash {money(event.value.net_cash_eur)}</p>
            {event.value.realized_pnl_eur != null && <p>Realized result {money(event.value.realized_pnl_eur)}</p>}
            <p>{event.value.rationale}</p>
            <details><summary>Execution details</summary><p>Fees {money(event.value.fees_eur)} · EUR conversion {quantity(event.value.fx_to_eur)} ({dateLabel(event.value.fx_date)})</p>
              <p>{event.value.price_source} · {event.value.fx_source}</p>
              {event.value.decision_id && <a href={`#${event.value.decision_id}`}>Investment decision</a>}
            </details>
          </> : <>
            <strong>{event.value.action} · {event.value.symbol ?? "Portfolio"}</strong>
            <p>{event.value.explanation}</p><small>{event.value.execution_status.replace(/_/g, " ")}</small>
            <details><summary>Review evidence</summary><p>Model {event.value.model} · Analysis {event.value.analysis_version}{event.value.financial_as_of ? ` · Financials ${dateLabel(event.value.financial_as_of)}` : ""}</p>
              {event.value.assessment?.evidence.map((e, i) => <p key={i}>{e.explanation} <small>{e.reference_id}</small></p>)}
              {event.value.assessment?.principal_risks.map((risk, i) => <p key={i}>{risk}</p>)}
            </details>
          </>}
        </li>)}</ol>
        {timeline.length > limit && <button type="button" onClick={() => setLimit(v => v + 25)}>Show more history</button>}
      </>}
    </div>}
  </section>;
}
