import type { OpenDataCompanyContext, OpenDataMetric, OpenDataStockSnapshot } from "../api";
import { BarChart3, ChevronDown, RefreshCcw } from "lucide-react";
import { useState } from "react";

type Props = {
  snapshot: OpenDataStockSnapshot | null;
  loading: boolean;
  onRefresh: () => void;
};

const COLUMNS = [
  ["business_health", "revenue_growth_yoy", "Rev YoY", "percent"],
  ["business_health", "revenue_cagr_3y", "Rev CAGR 3Y", "percent"],
  ["business_health", "eps_growth_yoy", "EPS YoY", "percent"],
  ["business_health", "eps_cagr_3y", "EPS CAGR 3Y", "percent"],
  ["business_health", "gross_margin", "Gross", "percent"],
  ["business_health", "operating_margin", "Operating", "percent"],
  ["business_health", "net_margin", "Net", "percent"],
  ["business_health", "free_cash_flow", "FCF", "compact"],
  ["business_health", "roe", "ROE", "percent"],
  ["business_health", "roic", "ROIC", "percent"],
  ["business_health", "cash", "Cash", "compact"],
  ["business_health", "debt", "Debt", "compact"],
  ["business_health", "debt_to_equity", "D/E", "ratio"],
  ["price_opportunity", "current_price", "Price", "ratio"],
  ["price_opportunity", "change_1d", "1D", "percent"],
  ["price_opportunity", "change_1w", "1W", "percent"],
  ["price_opportunity", "change_1m", "1M", "percent"],
  ["price_opportunity", "change_3m", "3M", "percent"],
  ["price_opportunity", "change_6m", "6M", "percent"],
  ["price_opportunity", "change_1y", "1Y", "percent"],
  ["price_opportunity", "change_2y", "2Y", "percent"],
  ["price_opportunity", "change_5y", "5Y", "percent"],
  ["price_opportunity", "distance_from_ath", "ATH", "percent"],
  ["price_opportunity", "distance_from_52w_high", "52W High", "percent"],
  ["price_opportunity", "distance_from_52w_low", "52W Low", "percent"],
  ["valuation", "pe", "PE", "ratio"],
  ["valuation", "forward_pe", "Forward PE", "ratio"],
  ["valuation", "peg", "PEG", "ratio"],
  ["valuation", "price_to_sales", "P/S", "ratio"],
  ["valuation", "ev_to_ebitda", "EV/EBITDA", "ratio"],
  ["valuation", "fcf_yield", "FCF Yield", "percent"],
] as const;

type MetricKind = "percent" | "ratio" | "compact";
type HistoricalRow = OpenDataStockSnapshot["historical_series"][string][number];

const CHARTS: Array<{
  title: string;
  series: string;
  metric: string;
  kind: MetricKind;
}> = [
  { title: "Revenue", series: "annual_fundamentals", metric: "revenue", kind: "compact" },
  { title: "EPS", series: "annual_fundamentals", metric: "eps_diluted", kind: "ratio" },
  { title: "Gross Margin", series: "annual_fundamentals", metric: "gross_margin", kind: "percent" },
  { title: "Operating Margin", series: "annual_fundamentals", metric: "operating_margin", kind: "percent" },
  { title: "Net Margin", series: "annual_fundamentals", metric: "net_margin", kind: "percent" },
  { title: "FCF Margin", series: "annual_fundamentals", metric: "fcf_margin", kind: "percent" },
  { title: "Cash", series: "annual_fundamentals", metric: "cash", kind: "compact" },
  { title: "Debt", series: "annual_fundamentals", metric: "debt", kind: "compact" },
  { title: "PE", series: "valuation_history", metric: "pe", kind: "ratio" },
  { title: "Price / Sales", series: "valuation_history", metric: "price_to_sales", kind: "ratio" },
  { title: "EV / EBITDA", series: "valuation_history", metric: "ev_to_ebitda", kind: "ratio" },
  { title: "FCF Yield", series: "valuation_history", metric: "fcf_yield", kind: "percent" },
];

function formatCompact(value?: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRatio(value?: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

function formatPercent(value?: number | null) {
  if (value == null) return "-";
  return `${formatRatio(value)}%`;
}

function formatValue(metric: OpenDataMetric | undefined, kind: string) {
  if (!metric) return "-";
  if (kind === "percent") return formatPercent(metric.value);
  if (kind === "ratio") return formatRatio(metric.value);
  return formatCompact(metric.value);
}

function tierLabel(tier: OpenDataMetric["tier"]) {
  return tier.replace(/_/g, " ");
}

function metricValue(row: HistoricalRow, metric: string) {
  const value = row.metrics[metric]?.value;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatByKind(value: number | null | undefined, kind: MetricKind) {
  if (kind === "percent") return formatPercent(value);
  if (kind === "compact") return formatCompact(value);
  return formatRatio(value);
}

function MiniLineChart({
  rows,
  metric,
  title,
  kind,
}: {
  rows: HistoricalRow[];
  metric: string;
  title: string;
  kind: MetricKind;
}) {
  const points = rows
    .map((row) => ({ period: row.period, value: metricValue(row, metric) }))
    .filter((point): point is { period: string; value: number } => point.value != null);

  if (points.length < 2) {
    return (
      <div className="mini-chart empty-chart">
        <div>
          <strong>{title}</strong>
          <small>Not enough annual values</small>
        </div>
      </div>
    );
  }

  const width = 320;
  const height = 150;
  const left = 46;
  const right = 14;
  const top = 18;
  const bottom = 32;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || Math.max(Math.abs(max), 1);
  const minY = min - spread * 0.08;
  const maxY = max + spread * 0.08;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const svgPoints = points.map((point, index) => {
    const x = left + (points.length === 1 ? 0 : (index / (points.length - 1)) * plotWidth);
    const y = top + ((maxY - point.value) / (maxY - minY || 1)) * plotHeight;
    return { ...point, x, y };
  });

  return (
    <div className="mini-chart">
      <div className="mini-chart-heading">
        <strong>{title}</strong>
        <small>
          {formatByKind(points[0].value, kind)} to {formatByKind(points[points.length - 1].value, kind)}
        </small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title} over time`}>
        <line x1={left} x2={width - right} y1={top + plotHeight} y2={top + plotHeight} />
        <line x1={left} x2={left} y1={top} y2={top + plotHeight} />
        <text x={left - 8} y={top + 4} textAnchor="end">
          {formatByKind(max, kind)}
        </text>
        <text x={left - 8} y={top + plotHeight} textAnchor="end">
          {formatByKind(min, kind)}
        </text>
        <polyline points={svgPoints.map((point) => `${point.x},${point.y}`).join(" ")} />
        {svgPoints.map((point) => (
          <g key={`${point.period}-${point.value}`}>
            <circle cx={point.x} cy={point.y} r="3.5" />
            <title>
              {point.period}: {formatByKind(point.value, kind)}
            </title>
          </g>
        ))}
        {svgPoints.map((point, index) => {
          if (index !== 0 && index !== svgPoints.length - 1) return null;
          return (
            <text key={point.period} x={point.x} y={height - 8} textAnchor={index === 0 ? "start" : "end"}>
              {point.period}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

function OpenDataCharts({ snapshot }: { snapshot: OpenDataStockSnapshot }) {
  const annualRows = snapshot.historical_series.annual_fundamentals ?? [];
  const valuationRows = snapshot.historical_series.valuation_history ?? [];
  const rowsBySeries: Record<string, HistoricalRow[]> = {
    annual_fundamentals: annualRows,
    valuation_history: valuationRows,
  };

  return (
    <div className="open-data-detail">
      <div className="open-data-detail-heading">
        <div>
          <h3>GOOGL Over Time</h3>
          <p>Annual facts used by the stock-analysis skill before it asks for more data.</p>
        </div>
        <span>{annualRows.length || valuationRows.length} annual periods</span>
      </div>
      <div className="chart-grid">
        {CHARTS.map((chart) => (
          <MiniLineChart
            key={`${chart.series}-${chart.metric}`}
            rows={rowsBySeries[chart.series] ?? []}
            metric={chart.metric}
            title={chart.title}
            kind={chart.kind}
          />
        ))}
      </div>
      {snapshot.company_context && <CompanyContextPanel context={snapshot.company_context} />}
      {snapshot.data_gaps.length > 0 && (
        <div className="data-gaps">
          <strong>Still missing for stronger AI analysis</strong>
          <ul>
            {snapshot.data_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CompanyContextPanel({ context }: { context: OpenDataCompanyContext }) {
  return (
    <div className="company-context">
      <div className="company-context-heading">
        <div>
          <h4>Company Context</h4>
          <p>Recent SEC filings collected as factual context for the stock-analysis step.</p>
        </div>
        <span>Latest {context.as_of}</span>
      </div>
      {context.recent_filings.length > 0 ? (
        <div className="filing-list">
          {context.recent_filings.map((filing) => (
            <article className="filing-item" key={filing.accession_number}>
              <div className="filing-title">
                <strong>{filing.form}</strong>
                <span>{filing.filing_date}</span>
                {filing.source_url && (
                  <a href={filing.source_url} target="_blank" rel="noreferrer">
                    SEC
                  </a>
                )}
              </div>
              <p>{filing.primary_document_description || filing.primary_document || filing.notes}</p>
              <div className="filing-meta">
                {filing.report_date && <span>Report {filing.report_date}</span>}
                {filing.items.map((item) => (
                  <span key={item}>Item {item}</span>
                ))}
              </div>
              {filing.exhibits.length > 0 && (
                <div className="exhibit-list">
                  {filing.exhibits.slice(0, 4).map((exhibit) => (
                    <a
                      key={`${filing.accession_number}-${exhibit.document}`}
                      href={exhibit.url ?? filing.source_url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      title={exhibit.description ?? exhibit.document}
                    >
                      {exhibit.type || exhibit.document}
                    </a>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="empty block">No recent SEC filing context loaded.</p>
      )}
      {context.known_context_gaps.length > 0 && (
        <div className="context-gaps">
          <strong>Context boundaries</strong>
          <ul>
            {context.known_context_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function OpenDataStockTable({ snapshot, loading, onRefresh }: Props) {
  const [chartsOpen, setChartsOpen] = useState(false);

  return (
    <section className="panel open-data-stocks">
      <div className="panel-heading">
        <h2>Open Data Fundamentals</h2>
        <div className="panel-heading-actions">
          <span>{snapshot ? 1 : 0}</span>
          <button type="button" onClick={onRefresh} disabled={loading} title="Collect fresh deterministic facts">
            <RefreshCcw size={16} aria-hidden="true" />
            {loading ? "Collecting" : "Collect Facts"}
          </button>
        </div>
      </div>

      {loading && <p className="loading inline">Loading GOOGL open data...</p>}
      {!loading && !snapshot && <p className="empty block">No open-data stock metrics loaded.</p>}

      {snapshot && (
        <>
          <div className="table-wrap">
            <table className="open-data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Sector</th>
                  {COLUMNS.map(([, , label]) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <button
                      type="button"
                      className={`ticker-drilldown ${chartsOpen ? "open" : ""}`}
                      onClick={() => setChartsOpen((open) => !open)}
                      aria-expanded={chartsOpen}
                      title="Show over-time charts for collected facts"
                    >
                      <ChevronDown size={15} aria-hidden="true" />
                      <strong>{snapshot.ticker}</strong>
                      <BarChart3 size={15} aria-hidden="true" />
                    </button>
                    <small>{snapshot.name ?? `CIK ${snapshot.cik ?? "-"}`}</small>
                    <span className="latest-badge">Latest snapshot values</span>
                  </td>
                  <td>
                    {snapshot.sector ?? "-"}
                    <small>{snapshot.industry ?? snapshot.exchange ?? "-"}</small>
                  </td>
                  {COLUMNS.map(([group, key, label, kind]) => {
                    const metric = snapshot[group][key];
                    return (
                      <td key={key} title={metric ? `${label}: ${metric.notes}\n${metric.source}` : label}>
                        <strong>{formatValue(metric, kind)}</strong>
                        {metric && (
                          <small>
                            Latest as of {metric.as_of}
                            <br />
                            {tierLabel(metric.tier)}
                          </small>
                        )}
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
          {chartsOpen && <OpenDataCharts snapshot={snapshot} />}
        </>
      )}
    </section>
  );
}
