import type { OpenDataCompanyContext, OpenDataMetric, OpenDataStockSnapshot, StockEntryAnalysis, StockEntryAnalysisSection } from "../api";
import { ArrowDown, ArrowUp, ArrowUpDown, BarChart3, ChevronRight, Filter, GripVertical, Info, RefreshCcw, X } from "lucide-react";
import { useMemo, useState } from "react";
import { formatDateTime } from "../format";

type Props = {
  snapshots: OpenDataStockSnapshot[];
  selectedTicker: string;
  loading: boolean;
  analyses: Record<string, StockEntryAnalysis>;
  analysisLoading: boolean;
  onSelectTicker: (ticker: string) => void;
  onRefresh: (ticker: string) => void;
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
type DetailKind = "charts" | "analysis" | null;
type Tone = "good" | "watch" | "caution" | "bad" | "neutral";
type ConvictionFilter = "all" | "strong" | "setup" | "uncertain" | "weak" | "needs_data";
type SortDirection = "asc" | "desc";
type SortValue = number | string | null;
type MetricGroup = "business_health" | "price_opportunity" | "valuation";
type ColumnKind = "conviction" | "assessment" | "text" | "metric";
type FilterValue = { field: string; value: string };

type ColumnDefinition = {
  id: string;
  label: string;
  kind: ColumnKind;
  group?: MetricGroup;
  key?: string;
  metricKind?: MetricKind;
};

type FilterDimension = {
  field: string;
  label: string;
  values: Array<{ value: string; label: string }>;
};

const CONVICTION_HELP =
  "0-3: weak / avoid / insufficient facts\n" +
  "4-5: interesting but too uncertain\n" +
  "6-7: interesting setup, but with meaningful caveats\n" +
  "8-10: very strong setup with cleaner valuation, price action, and evidence";

const OPPORTUNITY_COPY: Record<StockEntryAnalysis["opportunity_type"], { label: string; detail: string; tone: Tone }> = {
  "Temporary selloff": {
    label: "Short-term wobble",
    detail: "The stock has pulled back, but the supplied facts do not prove a deeper bargain.",
    tone: "watch",
  },
  "Quality compounder pullback": {
    label: "Good business, less stretched",
    detail: "Good business, still expensive-ish, but temporarily less stretched than it was.",
    tone: "good",
  },
  "Valuation reset": {
    label: "Price reset",
    detail: "The price or valuation has reset enough to make a fresh look worthwhile.",
    tone: "good",
  },
  "Momentum continuation": {
    label: "Still running",
    detail: "The longer trend is strong, so this is more trend-following than bargain hunting.",
    tone: "watch",
  },
  "Falling knife risk": {
    label: "Still falling",
    detail: "The price move looks risky enough that waiting for better evidence may be wiser.",
    tone: "bad",
  },
  "Insufficient data": {
    label: "Need more facts",
    detail: "The supplied facts are not enough to judge the setup confidently.",
    tone: "neutral",
  },
};

const ASSESSMENT_COPY: Record<string, { label: string; tone: Tone }> = {
  strong: { label: "Strong", tone: "good" },
  solid: { label: "Solid", tone: "good" },
  mixed: { label: "Mixed", tone: "watch" },
  weak: { label: "Weak", tone: "caution" },
  unclear: { label: "Unclear", tone: "neutral" },
  no_dip: { label: "No dip", tone: "caution" },
  strong_trend: { label: "Strong trend", tone: "watch" },
  better_spot: { label: "Better spot", tone: "watch" },
  pullback: { label: "Pullback", tone: "good" },
  deep_pullback: { label: "Deep pullback", tone: "watch" },
  falling: { label: "Falling", tone: "bad" },
  cheap: { label: "Cheap", tone: "good" },
  fair: { label: "Fair", tone: "good" },
  slightly_expensive: { label: "Slightly expensive", tone: "watch" },
  pricey: { label: "Pricey", tone: "caution" },
  very_pricey: { label: "Very pricey", tone: "bad" },
  fair_or_unclear: { label: "Fair / unclear", tone: "watch" },
  expensive_but_quality_supported: { label: "Pricey", tone: "caution" },
  moderate_short_term_pullback_with_strong_longer_trend: { label: "Pullback", tone: "good" },
  meaningful_pullback_weak_trend: { label: "Better spot", tone: "watch" },
  extended_no_pullback: { label: "No dip", tone: "caution" },
  strong_momentum_no_pullback: { label: "Strong trend", tone: "watch" },
};

const ASSESSMENT_LEGEND = [
  {
    title: "Business",
    description: "Checks whether the company itself looks healthy using growth, profitability, cash generation, returns, and debt.",
    rows: [
      ["Strong", "good", "Growth, margins, returns, and cash generation look strong."],
      ["Solid", "good", "Good fundamentals, but not elite across the board."],
      ["Mixed", "watch", "Some facts are good and others are weaker or less clean."],
      ["Weak", "caution", "Several core business facts look poor or deteriorating."],
      ["Unclear", "neutral", "Not enough business facts to classify."],
    ],
  },
  {
    title: "Price",
    description: "Checks whether the current price offers a useful entry. A healthy pullback is good; a price that is simply falling can be risky until it stabilizes.",
    rows: [
      ["Pullback", "good", "Meaningful pullback while the longer trend remains healthy."],
      ["Better spot", "watch", "Off highs and less stretched, but not a clear bargain."],
      ["Deep pullback", "watch", "Meaningfully below highs, but trend is weak or sideways."],
      ["Strong trend", "watch", "Uptrend is strong, but this is more momentum than entry discount."],
      ["No dip", "caution", "Near highs or still stretched; no useful pullback."],
      ["Falling", "bad", "Large drawdown or weak trend evidence; this may be a falling-knife setup."],
      ["Unclear", "neutral", "Not enough price facts to classify."],
    ],
  },
  {
    title: "Valuation",
    description: "Checks whether the price looks cheap or expensive using PE, forward PE, price/sales, EV/EBITDA, FCF yield, and available history.",
    rows: [
      ["Cheap", "good", "Clearly attractive versus available history and quality."],
      ["Fair", "good", "Not cheap, but not obviously expensive either."],
      ["Slightly expensive", "watch", "Elevated, but not severely stretched."],
      ["Pricey", "caution", "Clearly expensive on available valuation facts."],
      ["Very pricey", "bad", "Stretched on multiple valuation measures."],
      ["Unclear", "neutral", "Not enough valuation facts to classify."],
    ],
  },
] satisfies Array<{ title: string; description: string; rows: Array<[string, Tone, string]> }>;

const CONVICTION_FILTER_OPTIONS: Array<{ value: ConvictionFilter; label: string }> = [
  { value: "all", label: "All conviction" },
  { value: "strong", label: "8-10 strong" },
  { value: "setup", label: "6-7 setup" },
  { value: "uncertain", label: "4-5 uncertain" },
  { value: "weak", label: "0-3 weak" },
  { value: "needs_data", label: "Needs data" },
];

const STATIC_COLUMNS: ColumnDefinition[] = [
  { id: "conviction", label: "Conviction", kind: "conviction" },
  { id: "business", label: "Business", kind: "assessment" },
  { id: "price", label: "Price", kind: "assessment" },
  { id: "valuation", label: "Valuation", kind: "assessment" },
  { id: "sector", label: "Sector", kind: "text" },
];

const METRIC_COLUMNS: ColumnDefinition[] = COLUMNS.map(([group, key, label, metricKind]) => ({
  id: `metric:${group}:${key}`,
  label,
  kind: "metric",
  group,
  key,
  metricKind,
}));

const DEFAULT_MOVABLE_COLUMNS = [...STATIC_COLUMNS, ...METRIC_COLUMNS];

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
  const notes = metric.notes.toLowerCase();
  if (metric.value == null && notes.includes("eps turned positive")) return "Turnaround";
  if (metric.value == null && notes.includes("not meaningful")) return "Not meaningful";
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

function assessmentLabel(value: string) {
  return value.replace(/_/g, " ");
}

function assessmentCopy(value: string) {
  return ASSESSMENT_COPY[value] ?? { label: assessmentLabel(value), tone: "neutral" as const };
}

function analysisHeading(analysis: StockEntryAnalysis) {
  if (!analysis.name || analysis.name === analysis.ticker) return analysis.ticker;
  return `${analysis.ticker} (${analysis.name})`;
}

function verdictText(analysis: StockEntryAnalysis) {
  const summary = analysis.summary.trim();
  const names = [analysis.name, analysis.ticker].filter(Boolean) as string[];
  for (const name of names) {
    if (summary.startsWith(`${name} has `)) return summary.slice(`${name} has `.length);
    if (summary.startsWith(`${name} looks like `)) return `looks like ${summary.slice(`${name} looks like `.length)}`;
    if (summary.startsWith(`${name} `)) return summary.slice(name.length + 1);
  }
  return summary;
}

function convictionTone(value: number, needsMoreData: boolean): Tone {
  if (needsMoreData || value < 4) return "bad";
  if (value < 8) return "watch";
  return "good";
}

function convictionMatches(analysis: StockEntryAnalysis | undefined, filter: ConvictionFilter) {
  if (filter === "all") return true;
  if (!analysis) return false;
  if (filter === "needs_data") return analysis.needs_more_data;
  if (filter === "strong") return !analysis.needs_more_data && analysis.conviction >= 8;
  if (filter === "setup") return !analysis.needs_more_data && analysis.conviction >= 6 && analysis.conviction < 8;
  if (filter === "uncertain") return !analysis.needs_more_data && analysis.conviction >= 4 && analysis.conviction < 6;
  return analysis.needs_more_data || analysis.conviction < 4;
}

function analysisSectionFor(analysis: StockEntryAnalysis | undefined, columnId: string): StockEntryAnalysisSection | undefined {
  if (!analysis) return undefined;
  if (columnId === "business") return analysis.business_health;
  if (columnId === "price") return analysis.price_opportunity;
  if (columnId === "valuation") return analysis.valuation;
  return undefined;
}

function sortValueFor(snapshot: OpenDataStockSnapshot, analysis: StockEntryAnalysis | undefined, sortKey: string): SortValue {
  if (sortKey === "symbol") return snapshot.ticker;
  if (sortKey === "name") return snapshot.name ?? null;
  if (sortKey === "industry") return snapshot.industry ?? null;
  if (sortKey === "exchange") return snapshot.exchange ?? null;
  if (sortKey === "region") return snapshot.country ?? null;
  if (sortKey === "conviction") return analysis?.conviction ?? null;
  if (sortKey === "business" || sortKey === "price" || sortKey === "valuation") {
    const section = analysisSectionFor(analysis, sortKey);
    return section ? assessmentCopy(section.assessment).label : null;
  }
  if (sortKey === "sector") return snapshot.sector ?? snapshot.industry ?? snapshot.exchange ?? null;

  if (sortKey.startsWith("metric:")) {
    const [, group, key] = sortKey.split(":") as [string, MetricGroup, string];
    const value = snapshot[group]?.[key]?.value;
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  return null;
}

function filterValueFor(snapshot: OpenDataStockSnapshot, analysis: StockEntryAnalysis | undefined, field: string) {
  if (field === "symbol") return snapshot.ticker;
  if (field === "name") return snapshot.name ?? "";
  if (field === "sector") return snapshot.sector ?? "";
  if (field === "industry") return snapshot.industry ?? "";
  if (field === "exchange") return snapshot.exchange ?? "";
  if (field === "region") return snapshot.country ?? "";
  if (field === "conviction") {
    if (!analysis) return "";
    if (analysis.needs_more_data) return "needs_data";
    if (analysis.conviction >= 8) return "strong";
    if (analysis.conviction >= 6) return "setup";
    if (analysis.conviction >= 4) return "uncertain";
    return "weak";
  }
  if (field === "business" || field === "price" || field === "valuation") {
    return analysisSectionFor(analysis, field)?.assessment ?? "";
  }
  if (field.startsWith("metric:")) {
    const [, group, key] = field.split(":") as [string, MetricGroup, string];
    const metric = snapshot[group]?.[key];
    if (!metric) return "";
    return metric.value == null ? formatValue(metric, "ratio") : String(metric.value);
  }
  return "";
}

function filterLabelFor(field: string, value: string, dimensions: FilterDimension[]) {
  const dimension = dimensions.find((item) => item.field === field);
  const valueLabel = dimension?.values.find((item) => item.value === value)?.label ?? value;
  return `${dimension?.label ?? field}: ${valueLabel}`;
}

function uniqueOptions(rows: Array<{ value: string; label: string }>) {
  const byValue = new Map<string, string>();
  for (const row of rows) {
    const value = row.value.trim();
    if (!value || byValue.has(value)) continue;
    byValue.set(value, row.label.trim() || value);
  }
  return Array.from(byValue, ([value, label]) => ({ value, label })).sort((left, right) =>
    left.label.localeCompare(right.label, undefined, { numeric: true, sensitivity: "base" }),
  );
}

function moveColumn(ids: string[], fromId: string, toId: string) {
  if (fromId === toId) return ids;
  const fromIndex = ids.indexOf(fromId);
  const toIndex = ids.indexOf(toId);
  if (fromIndex < 0 || toIndex < 0) return ids;
  const next = [...ids];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

function compareSortValues(left: SortValue, right: SortValue, direction: SortDirection) {
  if (left == null && right == null) return 0;
  if (left == null) return 1;
  if (right == null) return -1;

  const comparison =
    typeof left === "number" && typeof right === "number"
      ? left - right
      : String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });

  return direction === "asc" ? comparison : -comparison;
}

function opportunityToneFor(analysis: StockEntryAnalysis, baseTone: Tone): Tone {
  const valuationTone = assessmentCopy(analysis.valuation.assessment).tone;
  const confidenceTone = convictionTone(analysis.conviction, analysis.needs_more_data);
  if (analysis.needs_more_data || confidenceTone === "bad") return "bad";
  if (baseTone === "good" && (confidenceTone !== "good" || valuationTone === "bad")) return "watch";
  return baseTone;
}

function AnalysisSection({ title, section }: { title: string; section: StockEntryAnalysisSection }) {
  const tag = assessmentCopy(section.assessment);
  const detail = assessmentLabel(section.assessment);

  return (
    <details className="entry-analysis-section">
      <summary>
        <h4>{title}</h4>
        <span className={`analysis-tag ${tag.tone}`} title={detail}>
          {tag.label}
        </span>
      </summary>
      {section.evidence.length > 0 && (
        <ul>
          {section.evidence.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {section.concerns.length > 0 && (
        <div className="entry-analysis-concerns">
          {section.concerns.slice(0, 3).map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>
      )}
    </details>
  );
}

function AssessmentTag({ section }: { section?: StockEntryAnalysisSection }) {
  if (!section) {
    return <span className="analysis-tag table-assessment-tag neutral">-</span>;
  }
  const tag = assessmentCopy(section.assessment);
  const detail = assessmentLabel(section.assessment);

  return (
    <span className={`analysis-tag table-assessment-tag ${tag.tone}`} title={detail}>
      {tag.label}
    </span>
  );
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
          <h3>{snapshot.ticker} Over Time</h3>
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

function OpenDataAnalysis({ analysis }: { analysis: StockEntryAnalysis }) {
  const opportunity = OPPORTUNITY_COPY[analysis.opportunity_type];
  const opportunityTone = opportunityToneFor(analysis, opportunity.tone);
  const confidenceTone = convictionTone(analysis.conviction, analysis.needs_more_data);

  return (
    <div className="open-data-detail open-data-analysis-detail">
      <article className="entry-analysis-card">
        <div className="entry-analysis-hero">
          <div>
            <div className="entry-analysis-title">
              <strong>{analysisHeading(analysis)}</strong>
              <span className={`tone-chip ${opportunityTone}`} title={opportunity.detail}>
                {opportunity.label}
              </span>
              {analysis.needs_more_data && <span className="warning-chip">Needs data</span>}
            </div>
            <p className="entry-analysis-verdict">
              <strong>Verdict:</strong> {verdictText(analysis)}
            </p>
          </div>
          <div
            className={`conviction-meter ${confidenceTone}`}
            aria-label={`Conviction ${analysis.conviction} out of 10`}
            title={CONVICTION_HELP}
          >
            <strong>{analysis.conviction.toFixed(1)}</strong>
            <span>Conviction</span>
          </div>
        </div>

        <div className="entry-analysis-grid">
          <AnalysisSection title="Business" section={analysis.business_health} />
          <AnalysisSection title="Price" section={analysis.price_opportunity} />
          <AnalysisSection title="Valuation" section={analysis.valuation} />
        </div>

        <div className="dca-plan">
          <div className="dca-bars" aria-label="DCA plan">
            <span style={{ flexGrow: analysis.dca_entry.buy_now || 1 }}>Now {analysis.dca_entry.buy_now}%</span>
            <span style={{ flexGrow: analysis.dca_entry.buy_dip_1 || 1 }}>Dip 1 {analysis.dca_entry.buy_dip_1}%</span>
            <span style={{ flexGrow: analysis.dca_entry.buy_dip_2 || 1 }}>Dip 2 {analysis.dca_entry.buy_dip_2}%</span>
          </div>
        </div>

        {analysis.missing_data.length > 0 && (
          <div className="entry-analysis-missing">
            <strong>Missing data for stronger confidence</strong>
            <ul>
              {analysis.missing_data.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="entry-analysis-footer">
          <span>Generated {formatDateTime(analysis.generated_at)}</span>
          {analysis.source_snapshot_generated_at && (
            <span>Facts {formatDateTime(analysis.source_snapshot_generated_at)}</span>
          )}
        </div>
      </article>
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
    </div>
  );
}

export function OpenDataStockTable({
  snapshots,
  selectedTicker,
  loading,
  analyses,
  analysisLoading,
  onSelectTicker,
  onRefresh,
}: Props) {
  const [openDetail, setOpenDetail] = useState<DetailKind>(null);
  const [query, setQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState<FilterValue[]>([]);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [activeFilterField, setActiveFilterField] = useState("sector");
  const [legendOpen, setLegendOpen] = useState(false);
  const [sortKey, setSortKey] = useState("symbol");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [columnOrder, setColumnOrder] = useState(() => DEFAULT_MOVABLE_COLUMNS.map((column) => column.id));
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.ticker === selectedTicker) ?? snapshots[0] ?? null;
  const selectedAnalysis = selectedSnapshot ? analyses[selectedSnapshot.ticker] ?? null : null;
  const refreshTicker = selectedSnapshot?.ticker ?? selectedTicker;

  const columnsById = useMemo(() => new Map(DEFAULT_MOVABLE_COLUMNS.map((column) => [column.id, column])), []);

  const orderedColumns = useMemo(() => {
    const knownIds = new Set(DEFAULT_MOVABLE_COLUMNS.map((column) => column.id));
    const ordered = columnOrder
      .filter((id) => knownIds.has(id))
      .map((id) => columnsById.get(id))
      .filter((column): column is ColumnDefinition => Boolean(column));
    const missing = DEFAULT_MOVABLE_COLUMNS.filter((column) => !columnOrder.includes(column.id));
    return [...ordered, ...missing];
  }, [columnOrder, columnsById]);

  const filterDimensions = useMemo<FilterDimension[]>(() => {
    const analysesList = snapshots
      .map((snapshot) => analyses[snapshot.ticker])
      .filter((analysis): analysis is StockEntryAnalysis => Boolean(analysis));

    const assessmentDimension = (field: string, label: string, pick: (analysis: StockEntryAnalysis) => StockEntryAnalysisSection) => ({
      field,
      label,
      values: uniqueOptions(analysesList.map((analysis) => {
        const assessment = pick(analysis).assessment;
        return { value: assessment, label: assessmentCopy(assessment).label };
      })),
    });

    return [
      {
        field: "symbol",
        label: "Symbol",
        values: uniqueOptions(snapshots.map((snapshot) => ({ value: snapshot.ticker, label: snapshot.ticker }))),
      },
      {
        field: "name",
        label: "Name",
        values: uniqueOptions(
          snapshots.map((snapshot) => ({ value: snapshot.name ?? "", label: snapshot.name ?? snapshot.ticker })),
        ),
      },
      {
        field: "sector",
        label: "Sector",
        values: uniqueOptions(snapshots.map((snapshot) => ({ value: snapshot.sector ?? "", label: snapshot.sector ?? "" }))),
      },
      {
        field: "industry",
        label: "Industry",
        values: uniqueOptions(snapshots.map((snapshot) => ({ value: snapshot.industry ?? "", label: snapshot.industry ?? "" }))),
      },
      {
        field: "region",
        label: "Region",
        values: uniqueOptions(snapshots.map((snapshot) => ({ value: snapshot.country ?? "", label: snapshot.country ?? "" }))),
      },
      {
        field: "exchange",
        label: "Exchange",
        values: uniqueOptions(snapshots.map((snapshot) => ({ value: snapshot.exchange ?? "", label: snapshot.exchange ?? "" }))),
      },
      {
        field: "conviction",
        label: "Conviction",
        values: CONVICTION_FILTER_OPTIONS.filter((option) => option.value !== "all"),
      },
      assessmentDimension("business", "Business", (analysis) => analysis.business_health),
      assessmentDimension("price", "Price", (analysis) => analysis.price_opportunity),
      assessmentDimension("valuation", "Valuation", (analysis) => analysis.valuation),
      ...METRIC_COLUMNS.map((column) => ({
        field: column.id,
        label: column.label,
        values: uniqueOptions(
          snapshots.map((snapshot) => {
            const metric = snapshot[column.group as MetricGroup]?.[column.key ?? ""];
            const label = formatValue(metric, column.metricKind ?? "ratio");
            return { value: metric?.value == null ? label : String(metric.value), label };
          }),
        ),
      })),
    ].filter((dimension) => dimension.values.length > 0);
  }, [analyses, snapshots]);

  const activeFilterCount = activeFilters.length;
  const activeFilterDimension =
    filterDimensions.find((dimension) => dimension.field === activeFilterField) ?? filterDimensions[0] ?? null;

  const filterValueLabel = (field: string) => {
    const existing = activeFilters.find((filter) => filter.field === field);
    if (!existing) return "Any";
    return filterLabelFor(existing.field, existing.value, filterDimensions).split(": ").slice(1).join(": ");
  };

  const applyFilterValue = (value: string) => {
    setActiveFilters((filters) => {
      const next = filters.filter((filter) => filter.field !== activeFilterField);
      return [...next, { field: activeFilterField, value }];
    });
    setFilterMenuOpen(false);
  };

  const removeFilter = (field: string) => {
    setActiveFilters((filters) => filters.filter((filter) => filter.field !== field));
  };

  const clearFilters = () => setActiveFilters([]);

  const visibleSnapshots = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return snapshots
      .filter((snapshot) => {
        const analysis = analyses[snapshot.ticker];
        const matchesQuery =
          needle.length === 0 ||
          [snapshot.ticker, snapshot.name, snapshot.sector, snapshot.industry, snapshot.exchange]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(needle));
        const matchesActiveFilters = activeFilters.every((filter) => filterValueFor(snapshot, analysis, filter.field) === filter.value);

        return matchesQuery && matchesActiveFilters;
      })
      .sort((left, right) => {
        const comparison = compareSortValues(
          sortValueFor(left, analyses[left.ticker], sortKey),
          sortValueFor(right, analyses[right.ticker], sortKey),
          sortDirection,
        );
        return comparison || left.ticker.localeCompare(right.ticker);
      });
  }, [
    analyses,
    activeFilters,
    query,
    snapshots,
    sortDirection,
    sortKey,
  ]);

  const toggleDetail = (ticker: string, detail: Exclude<DetailKind, null>) => {
    const isSelected = selectedSnapshot?.ticker === ticker;
    onSelectTicker(ticker);
    setOpenDetail((current) => (isSelected && current === detail ? null : detail));
  };

  const toggleSort = (key: string) => {
    if (key === sortKey) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  };

  const handleColumnDrop = (targetId: string) => {
    if (!draggedColumn) return;
    setColumnOrder((ids) => moveColumn(ids, draggedColumn, targetId));
    setDraggedColumn(null);
  };

  const renderSortHeader = (key: string, label: string) => {
    const active = key === sortKey;
    const Icon = active ? (sortDirection === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
    return (
      <button
        type="button"
        className={`sort-header ${active ? "active" : ""}`}
        onClick={() => toggleSort(key)}
        aria-sort={active ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}
        title={`Sort by ${label}`}
      >
        <span>{label}</span>
        <Icon size={13} aria-hidden="true" />
      </button>
    );
  };

  const renderDraggableHeader = (column: ColumnDefinition) => (
    <th
      key={column.id}
      className={`draggable-column ${draggedColumn === column.id ? "dragging" : ""}`}
      draggable
      onDragStart={(event) => {
        setDraggedColumn(column.id);
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", column.id);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      }}
      onDrop={(event) => {
        event.preventDefault();
        handleColumnDrop(column.id);
      }}
      onDragEnd={() => setDraggedColumn(null)}
    >
      <div className="draggable-header">
        <GripVertical size={14} aria-hidden="true" />
        {renderSortHeader(column.id, column.label)}
      </div>
    </th>
  );

  const renderColumnCell = (snapshot: OpenDataStockSnapshot, analysis: StockEntryAnalysis | undefined, column: ColumnDefinition) => {
    if (column.id === "conviction") {
      const isSelected = selectedSnapshot?.ticker === snapshot.ticker;
      const confidenceTone = analysis ? convictionTone(analysis.conviction, analysis.needs_more_data) : "neutral";
      return (
        <td className="conviction-cell" key={column.id}>
          {analysis ? (
            <button
              type="button"
              className={`table-conviction ${confidenceTone} ${isSelected && openDetail === "analysis" ? "active" : ""}`}
              onClick={() => toggleDetail(snapshot.ticker, "analysis")}
              aria-expanded={isSelected && openDetail === "analysis"}
              title={CONVICTION_HELP}
            >
              {analysis.conviction.toFixed(1)}
            </button>
          ) : (
            <button
              type="button"
              className="table-conviction neutral"
              onClick={() => toggleDetail(snapshot.ticker, "analysis")}
              aria-expanded={isSelected && openDetail === "analysis"}
              title={analysisLoading ? "Loading AI analysis" : "No AI analysis loaded yet"}
            >
              {analysisLoading ? "..." : "-"}
            </button>
          )}
        </td>
      );
    }

    if (column.id === "business" || column.id === "price" || column.id === "valuation") {
      return (
        <td key={column.id}>
          <AssessmentTag section={analysisSectionFor(analysis, column.id)} />
        </td>
      );
    }

    if (column.id === "sector") {
      return (
        <td key={column.id}>
          {snapshot.sector ?? "-"}
          <small>{snapshot.industry ?? snapshot.exchange ?? "-"}</small>
        </td>
      );
    }

    if (column.kind === "metric" && column.group && column.key) {
      const metric = snapshot[column.group][column.key];
      return (
        <td key={column.id} title={metric ? `${column.label}: ${metric.notes}\n${metric.source}` : column.label}>
          <strong>{formatValue(metric, column.metricKind ?? "ratio")}</strong>
          {metric && (
            <small>
              Latest as of {metric.as_of}
              <br />
              {tierLabel(metric.tier)}
            </small>
          )}
        </td>
      );
    }

    return <td key={column.id}>-</td>;
  };

  return (
    <section className="panel open-data-stocks">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>Open Data Fundamentals</h2>
          <button
            type="button"
            className="info-button"
            onClick={() => setLegendOpen((open) => !open)}
            aria-expanded={legendOpen}
            title="Show Business, Price, and Valuation tag meanings"
          >
            <Info size={16} aria-hidden="true" />
          </button>
          {legendOpen && (
            <div className="assessment-legend">
              {ASSESSMENT_LEGEND.map((section) => (
                <section className="assessment-legend-section" key={section.title}>
                  <h3>{section.title}</h3>
                  <p>{section.description}</p>
                  <ul>
                    {section.rows.map(([label, tone, description]) => (
                      <li key={label}>
                        <span className={`legend-tag ${tone}`}>{label}</span>
                        <span>{description}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
        <div className="panel-heading-actions">
          <span>{visibleSnapshots.length} / {snapshots.length}</span>
          <button
            type="button"
            onClick={() => onRefresh(refreshTicker)}
            disabled={loading}
            title={`Collect fresh deterministic facts for ${refreshTicker}`}
          >
            <RefreshCcw size={16} aria-hidden="true" />
            {loading ? "Collecting" : "Collect Facts"}
          </button>
        </div>
      </div>

      {loading && <p className="loading inline">Loading open-data stock metrics...</p>}
      {!loading && snapshots.length === 0 && <p className="empty block">No open-data stock metrics loaded.</p>}

      {snapshots.length > 0 && (
        <>
          <div className="open-data-filters">
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search symbol, name, sector"
              aria-label="Search stocks"
            />
            <div className="filter-menu">
              <button
                type="button"
                className={`filter-menu-trigger ${activeFilterCount > 0 ? "active" : ""}`}
                onClick={() => setFilterMenuOpen((open) => !open)}
                aria-expanded={filterMenuOpen}
              >
                <Filter size={16} aria-hidden="true" />
                Filter
                {activeFilterCount > 0 && <span>{activeFilterCount}</span>}
              </button>
              {filterMenuOpen && (
                <div className="filter-popover">
                  <div className="filter-columns">
                    <div className="filter-category-list">
                      {filterDimensions.map((dimension) => (
                        <button
                          key={dimension.field}
                          type="button"
                          className={activeFilterField === dimension.field ? "active" : ""}
                          onClick={() => setActiveFilterField(dimension.field)}
                        >
                          <span>{dimension.label}</span>
                          <small>{filterValueLabel(dimension.field)}</small>
                          <ChevronRight size={15} aria-hidden="true" />
                        </button>
                      ))}
                    </div>
                    <div className="filter-option-list">
                      <strong>{activeFilterDimension?.label ?? "Filter"}</strong>
                      {activeFilterDimension?.values.map((option) => {
                        const active = activeFilters.some(
                          (filter) => filter.field === activeFilterDimension.field && filter.value === option.value,
                        );
                        return (
                          <button
                            key={option.value}
                            type="button"
                            className={active ? "active" : ""}
                            onClick={() => applyFilterValue(option.value)}
                          >
                            {option.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  {activeFilterCount > 0 && (
                    <button type="button" className="filter-clear" onClick={clearFilters}>
                      Clear filters
                    </button>
                  )}
                </div>
              )}
            </div>
            {activeFilters.length > 0 && (
              <div className="active-filter-list" aria-label="Active filters">
                {activeFilters.map((filter) => (
                  <button
                    key={`${filter.field}-${filter.value}`}
                    type="button"
                    className="active-filter-chip"
                    onClick={() => removeFilter(filter.field)}
                    title="Remove filter"
                  >
                    {filterLabelFor(filter.field, filter.value, filterDimensions)}
                    <X size={13} aria-hidden="true" />
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="table-wrap">
            <table className="open-data-table">
              <thead>
                <tr>
                  <th className="sticky-symbol-column">{renderSortHeader("symbol", "Symbol")}</th>
                  {orderedColumns.map((column) => renderDraggableHeader(column))}
                </tr>
              </thead>
              <tbody>
                {visibleSnapshots.map((snapshot) => {
                  const isSelected = selectedSnapshot?.ticker === snapshot.ticker;
                  const analysis = analyses[snapshot.ticker];
                  return (
                    <tr key={snapshot.ticker}>
                      <td className="sticky-symbol-column">
                        <div className="ticker-cell-main">
                          <strong>{snapshot.ticker}</strong>
                          <button
                            type="button"
                            className={`table-icon-button ${isSelected && openDetail === "charts" ? "active" : ""}`}
                            onClick={() => toggleDetail(snapshot.ticker, "charts")}
                            aria-expanded={isSelected && openDetail === "charts"}
                            title="Show over-time charts for collected facts"
                          >
                            <BarChart3 size={15} aria-hidden="true" />
                          </button>
                        </div>
                        <small>{snapshot.name ?? `CIK ${snapshot.cik ?? "-"}`}</small>
                        <span className="latest-badge">Latest snapshot values</span>
                      </td>
                      {orderedColumns.map((column) => renderColumnCell(snapshot, analysis, column))}
                    </tr>
                  );
                })}
                {visibleSnapshots.length === 0 && (
                  <tr>
                    <td colSpan={orderedColumns.length + 1}>
                      <p className="empty block">No stocks match the current filters.</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {openDetail && selectedSnapshot && (
            <div className="detail-modal-backdrop" role="presentation" onClick={() => setOpenDetail(null)}>
              <div
                className="detail-modal"
                role="dialog"
                aria-modal="true"
                aria-label={`${selectedSnapshot.ticker} ${openDetail === "charts" ? "charts" : "AI analysis"}`}
                onClick={(event) => event.stopPropagation()}
              >
                <div className="detail-modal-heading">
                  <div>
                    <strong>{selectedSnapshot.ticker}</strong>
                    <span>{openDetail === "charts" ? "Charts" : "AI analysis"}</span>
                  </div>
                  <button type="button" className="icon-button" onClick={() => setOpenDetail(null)} title="Close">
                    <X size={18} aria-hidden="true" />
                  </button>
                </div>
                {openDetail === "charts" && <OpenDataCharts snapshot={selectedSnapshot} />}
                {openDetail === "analysis" &&
                  (selectedAnalysis ? (
                    <OpenDataAnalysis analysis={selectedAnalysis} />
                  ) : (
                    <div className="open-data-detail">
                      <p className="loading inline">
                        {analysisLoading ? "Loading AI analysis..." : "No AI analysis loaded for this stock yet."}
                      </p>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
