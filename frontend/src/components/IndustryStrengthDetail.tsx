import { useState } from "react";
import type { OpenDataStockSnapshot } from "../api";
import { INDUSTRY_STRENGTH_COPY, industryStrengthContext, industryStrengthSignal, type IndustryStrength } from "../industryStrength";
import { formatMomentumPp } from "../revenueGrowthMomentum";
import { MetricStatus } from "./MetricStatus";
import "../industryStrength.css";

const percent = (value: number | null) => value == null ? "-" : `${value > 0 ? "+" : ""}${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}%`;

function ComparisonChart({ context, ticker }: { context: IndustryStrength; ticker: string }) {
  const [selected, setSelected] = useState<number | null>(null);
  const points = context.chart;
  if (points.length < 2) return null;
  const width = 680, height = 280;
  const pad = { left: 12, right: 52, top: 22, bottom: 30 };
  const values = points.flatMap((p) => [p.stock, p.industry, p.market]);
  const min = Math.min(100, ...values), max = Math.max(100, ...values);
  const spread = Math.max(max - min, 10);
  const x = (i: number) => pad.left + i / (points.length - 1) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (max + spread * 0.08 - value) / (spread * 1.16) * (height - pad.top - pad.bottom);
  const series = [{ key: "stock", label: ticker }, { key: "industry", label: "Tracked industry" }, { key: "market", label: context.benchmark.name }] as const;
  const point = points[selected ?? points.length - 1];
  return (
    <article className="mobile-growth-chart industry-comparison-chart">
      <h3>1Y comparison · starting at 100</h3>
      <div className="industry-chart-legend">
        {series.map((s) => <span key={s.key}><i className={`industry-series-${s.key}`} />{s.label}</span>)}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${ticker}, tracked industry and ${context.benchmark.name} over one year, indexed to 100`}>
        {[min, (min + max) / 2, max].map((value, i) => <g key={i}>
          <line className="mobile-chart-gridline" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
          <text className="mobile-chart-axis-label" x={width - 4} y={y(value)}>{value.toFixed(0)}</text>
        </g>)}
        {series.map((s) => <path key={s.key} className={`industry-chart-line industry-series-${s.key}`} d={points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(p[s.key]).toFixed(2)}`).join(" ")} />)}
        {selected != null && <line className="industry-chart-cursor" x1={x(selected)} x2={x(selected)} y1={pad.top} y2={height - pad.bottom} />}
        {[0, points.length - 1].map((i) => <text key={i} className="mobile-chart-date" textAnchor={i === 0 ? "start" : "end"} x={x(i)} y={height - 6}>{points[i].date}</text>)}
        <rect className="mobile-chart-hit" x={pad.left} y={pad.top} width={width - pad.left - pad.right} height={height - pad.top - pad.bottom}
          onPointerMove={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            setSelected(Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * (points.length - 1)));
          }} onPointerLeave={() => setSelected(null)} />
      </svg>
      <p className="industry-chart-values">{point.date} · {series.map((s) => `${s.label} ${point[s.key].toFixed(2)}`).join(" · ")}</p>
    </article>
  );
}

export function IndustryStrengthDetail({ snapshot, onOpenPeer }: {
  snapshot: OpenDataStockSnapshot;
  onOpenPeer: (ticker: string) => void;
}) {
  const [ascending, setAscending] = useState(false);
  const context = industryStrengthContext(snapshot);
  const signal = industryStrengthSignal(context);
  const available = context?.value != null;
  const peers = [...(context?.peers ?? [])].sort((a, b) => (ascending ? 1 : -1) * (a.return_pct - b.return_pct) || a.ticker.localeCompare(b.ticker));
  const copy = INDUSTRY_STRENGTH_COPY;
  return (
    <section className="mobile-growth-detail-panel industry-strength-detail">
      <div className="mobile-growth-copy">
        <span>Metric definition</span><h2>{copy.title}</h2>
        <p className="metric-question">{copy.question}</p><p>{copy.description}</p>
      </div>
      <div className="mobile-growth-formula">
        <span>Current value</span><strong>{formatMomentumPp(context?.value ?? null)}</strong>
        <MetricStatus signal={signal} context="1Y" />
        {available && context ? <>
          <small>{context.industry} · {context.sector}</small>
          <div className="industry-return-row"><span>Tracked industry average</span><strong>{percent(context.industry_return)}</strong></div>
          <div className="industry-return-row"><span>{context.benchmark.name}</span><strong>{percent(context.market_return)}</strong></div>
          <small>Industry return − market return = {formatMomentumPp(context.value)}.</small>
          <div className="industry-return-row"><span>{snapshot.ticker}</span><strong>{percent(context.stock_return)}</strong></div>
          <small>{snapshot.ticker} versus tracked industry: {formatMomentumPp(context.stock_vs_industry)}.</small>
          <small>{context.start_date} to {context.end_date} · {context.peer_count} of {context.tracked_peer_count} tracked peers included.</small>
        </> : <small>{context?.reason ?? "Industry comparison is unavailable. The next data refresh will calculate it where classification, benchmark history and at least five peers are available."}</small>}
      </div>
      {available && context && <ComparisonChart key={snapshot.ticker} context={context} ticker={snapshot.ticker} />}
      {peers.length > 0 && <article className="industry-peer-list">
        <h3>Companies in the comparison</h3>
        {!available && <p>Available peer returns; insufficient data for a reliable industry comparison.</p>}
        <table>
          <thead><tr><th scope="col">Company</th><th scope="col" aria-sort={ascending ? "ascending" : "descending"}><button type="button" onClick={() => setAscending(!ascending)}>1Y return {ascending ? "↑" : "↓"}</button></th></tr></thead>
          <tbody>
            {available && context && <tr className="industry-selected-stock"><th scope="row">{snapshot.ticker}<small>Selected stock · excluded from peer average</small></th><td>{percent(context.stock_return)}</td></tr>}
            {peers.map((p) => <tr key={p.ticker}><th scope="row"><button type="button" onClick={() => onOpenPeer(p.ticker)}>{p.ticker}<small>{p.name}</small></button></th><td>{percent(p.return_pct)}</td></tr>)}
          </tbody>
        </table>
      </article>}
      <div className="mobile-growth-copy industry-method">
        <h3>How to read it</h3>
        <p>Ahead of market: at least +5 pp. Behind market: at most −5 pp. In line: between −5 and +5 pp. These are descriptive thresholds, not investment ratings. Both the industry and market can be falling even when the industry is ahead.</p>
        <p>Equal-weight tracked peers, excluding {snapshot.ticker}. Price returns exclude dividends. The tracked sample does not represent every company in the industry. Read this alongside growth, cash flow and valuation.</p>
        {context && <>
          <p>Grouping: {context.classification_source} · reviewed {context.classification_reviewed_at}. {context.industry} ({context.sector}). Original saved label: {context.original_industry} ({context.original_sector}); its original vendor was not recorded.</p>
          <p>Benchmark: <a href={context.benchmark.source_url} target="_blank" rel="noreferrer">{context.benchmark.name} ({context.benchmark.symbol})</a> · {context.benchmark.currency} · price return. Calculated {context.generated_at.slice(0, 10)}{context.end_date ? ` from prices through ${context.end_date}` : ""}.</p>
          {context.classification_sources.length > 0 && <p>Business references: {context.classification_sources.map((url, i) => <a key={url} href={url} target="_blank" rel="noreferrer">{i ? ", " : ""}{new URL(url).hostname}</a>)}</p>}
          {context.excluded_peers.length > 0 && <details><summary>Excluded peers ({context.excluded_peers.length})</summary><ul>{context.excluded_peers.map((p) => <li key={p.ticker}>{p.ticker}: {p.reason}</li>)}</ul></details>}
        </>}
      </div>
    </section>
  );
}
