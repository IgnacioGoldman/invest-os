import type { OpenDataCompanyContext, OpenDataMetric, OpenDataStockSnapshot, StockEntryAnalysis, StockEntryAnalysisSection } from "../api";
import { ArrowDown, ArrowUp, ArrowUpDown, BarChart3, ChevronDown, ChevronLeft, ChevronRight, Filter, GripVertical, Info, SlidersHorizontal, X } from "lucide-react";
import { Fragment, memo, useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../format";

type Props = {
  snapshots: OpenDataStockSnapshot[];
  selectedTicker: string;
  loading: boolean;
  analyses: Record<string, StockEntryAnalysis>;
  analysisLoading: boolean;
  onSelectTicker: (ticker: string) => void;
};

const COLUMNS = [
  ["business_health", "revenue_growth_yoy", "Q Rev YoY", "percent"],
  ["business_health", "revenue_cagr_3y", "Q Rev CAGR 3Y", "percent"],
  ["business_health", "eps_growth_yoy", "Q EPS YoY", "percent"],
  ["business_health", "eps_cagr_3y", "Q EPS CAGR 3Y", "percent"],
  ["business_health", "gross_margin", "Q Gross", "percent"],
  ["business_health", "operating_margin", "Q Operating", "percent"],
  ["business_health", "net_margin", "Q Net", "percent"],
  ["business_health", "free_cash_flow", "Q FCF", "compact"],
  ["business_health", "roe", "Q ROE", "percent"],
  ["business_health", "roic", "Q ROIC", "percent"],
  ["business_health", "cash", "Cash", "compact"],
  ["business_health", "debt", "Debt", "compact"],
  ["business_health", "debt_to_equity", "D/E", "ratio"],
  ["price_opportunity", "current_price", "Price", "ratio"],
  ["price_opportunity", "support_1d_distance", "Support 1D", "percent"],
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
type ColumnKind = "conviction" | "assessment" | "text" | "metric" | "derived";
type FilterValue = { field: string; value: string };
type DerivedMetric = {
  value: number | null;
  kind: MetricKind;
  notes: string;
};
type PeerMetricKey = "revenue_cagr_3y" | "roic" | "fcf_yield" | "pe";
type PeerDistribution = {
  all: number[];
  bySector: Map<string, number[]>;
};
type DerivedMetricContext = {
  peerDistributions: Record<PeerMetricKey, PeerDistribution>;
};

type ColumnDefinition = {
  id: string;
  label: string;
  kind: ColumnKind;
  group?: MetricGroup;
  key?: string;
  metricKind?: MetricKind;
  derivedKey?: string;
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

const DERIVED_COLUMNS: ColumnDefinition[] = [
  { id: "derived:unusual_score", label: "Unusual", kind: "derived", derivedKey: "unusual_score", metricKind: "ratio" },
  { id: "derived:pe_hist_percentile", label: "PE Hist %", kind: "derived", derivedKey: "pe_hist_percentile", metricKind: "percent" },
  { id: "derived:pe_vs_median", label: "PE vs Med", kind: "derived", derivedKey: "pe_vs_median", metricKind: "percent" },
  { id: "derived:ps_hist_percentile", label: "P/S Hist %", kind: "derived", derivedKey: "ps_hist_percentile", metricKind: "percent" },
  { id: "derived:fcfy_hist_percentile", label: "FCFY Hist %", kind: "derived", derivedKey: "fcfy_hist_percentile", metricKind: "percent" },
  { id: "derived:rev_accel", label: "Rev Accel", kind: "derived", derivedKey: "rev_accel", metricKind: "percent" },
  { id: "derived:eps_accel", label: "EPS Accel", kind: "derived", derivedKey: "eps_accel", metricKind: "percent" },
  { id: "derived:op_margin_yoy_delta", label: "Op dYoY", kind: "derived", derivedKey: "op_margin_yoy_delta", metricKind: "percent" },
  { id: "derived:fcf_margin_3y_delta", label: "FCF Mgn d3Y", kind: "derived", derivedKey: "fcf_margin_3y_delta", metricKind: "percent" },
  { id: "derived:fcf_conversion", label: "FCF / NI", kind: "derived", derivedKey: "fcf_conversion", metricKind: "percent" },
  { id: "derived:net_cash", label: "Net Cash", kind: "derived", derivedKey: "net_cash", metricKind: "compact" },
  { id: "derived:net_debt_to_fcf", label: "Net Debt / FCF", kind: "derived", derivedKey: "net_debt_to_fcf", metricKind: "ratio" },
  { id: "derived:shares_3y_change", label: "Shares Δ3Y", kind: "derived", derivedKey: "shares_3y_change", metricKind: "percent" },
  { id: "derived:pe_to_rev_cagr", label: "PE / Rev CAGR", kind: "derived", derivedKey: "pe_to_rev_cagr", metricKind: "ratio" },
  { id: "derived:growth_plus_fcfy", label: "Growth + FCFY", kind: "derived", derivedKey: "growth_plus_fcfy", metricKind: "percent" },
  { id: "derived:sector_rev_rank", label: "Sector Rev %", kind: "derived", derivedKey: "sector_rev_rank", metricKind: "percent" },
  { id: "derived:sector_roic_rank", label: "Sector ROIC %", kind: "derived", derivedKey: "sector_roic_rank", metricKind: "percent" },
  { id: "derived:sector_fcfy_rank", label: "Sector FCFY %", kind: "derived", derivedKey: "sector_fcfy_rank", metricKind: "percent" },
  { id: "derived:sector_pe_cheap_rank", label: "Sector Cheap PE %", kind: "derived", derivedKey: "sector_pe_cheap_rank", metricKind: "percent" },
  { id: "derived:price_fund_gap", label: "Price/Fund Gap", kind: "derived", derivedKey: "price_fund_gap", metricKind: "percent" },
];

const DEFAULT_MOVABLE_COLUMNS = [...STATIC_COLUMNS, ...DERIVED_COLUMNS, ...METRIC_COLUMNS];
const DEFAULT_VISIBLE_COLUMN_IDS = [
  "conviction",
  "business",
  "price",
  "valuation",
  "sector",
  "metric:price_opportunity:support_1d_distance",
];
const PAGE_SIZE = 10;

const CHARTS: Array<{
  title: string;
  series: string;
  metric: string;
  kind: MetricKind;
}> = [
  { title: "Quarterly Revenue", series: "quarterly_fundamentals", metric: "revenue", kind: "compact" },
  { title: "Quarterly EPS", series: "quarterly_fundamentals", metric: "eps_diluted", kind: "ratio" },
  { title: "Quarterly Gross Margin", series: "quarterly_fundamentals", metric: "gross_margin", kind: "percent" },
  { title: "Quarterly Operating Margin", series: "quarterly_fundamentals", metric: "operating_margin", kind: "percent" },
  { title: "Quarterly Net Margin", series: "quarterly_fundamentals", metric: "net_margin", kind: "percent" },
  { title: "Quarterly FCF Margin", series: "quarterly_fundamentals", metric: "fcf_margin", kind: "percent" },
  { title: "Quarterly Cash", series: "quarterly_fundamentals", metric: "cash", kind: "compact" },
  { title: "Quarterly Debt", series: "quarterly_fundamentals", metric: "debt", kind: "compact" },
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

function formatSignedPercent(value?: number | null) {
  if (value == null) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatRatio(value)}%`;
}

function supportSignalLabel(value?: number | null) {
  if (value == null) return "Far";
  if (value <= 2.5) return "At support";
  if (value <= 6) return "Near support";
  return "Above support";
}

function formatSupportSignal(value?: number | null) {
  if (value == null) return "Far";
  return `${supportSignalLabel(value)} ${formatSignedPercent(value)}`;
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

function finiteNumber(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function snapshotMetricValue(snapshot: OpenDataStockSnapshot, group: MetricGroup, key: string) {
  return finiteNumber(snapshot[group]?.[key]?.value);
}

function snapshotFlatMetricValue(snapshot: OpenDataStockSnapshot, key: string) {
  return finiteNumber(snapshot.metrics?.[key]?.value);
}

function sortedHistoricalRows(snapshot: OpenDataStockSnapshot, series: string) {
  return [...(snapshot.historical_series[series] ?? [])].sort((left, right) =>
    left.period.localeCompare(right.period, undefined, { numeric: true, sensitivity: "base" }),
  );
}

function historicalValues(snapshot: OpenDataStockSnapshot, series: string, metric: string) {
  return sortedHistoricalRows(snapshot, series)
    .map((row) => ({ period: row.period, value: metricValue(row, metric) }))
    .filter((point): point is { period: string; value: number } => point.value != null);
}

function historicalDelta(snapshot: OpenDataStockSnapshot, series: string, metric: string, yearsBack: number) {
  const points = historicalValues(snapshot, series, metric);
  const latest = points[points.length - 1];
  const prior = points[points.length - 1 - yearsBack];
  if (!latest || !prior) return null;
  return latest.value - prior.value;
}

function historicalPercentChange(snapshot: OpenDataStockSnapshot, series: string, metric: string, yearsBack: number) {
  const points = historicalValues(snapshot, series, metric);
  const latest = points[points.length - 1];
  const prior = points[points.length - 1 - yearsBack];
  if (!latest || !prior || prior.value === 0) return null;
  return ((latest.value / prior.value) - 1) * 100;
}

function median(values: number[]) {
  const clean = values.filter((value) => Number.isFinite(value)).sort((left, right) => left - right);
  if (clean.length === 0) return null;
  const middle = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[middle] : (clean[middle - 1] + clean[middle]) / 2;
}

function percentileOfValue(values: number[], value: number | null) {
  const clean = values.filter((item) => Number.isFinite(item));
  if (value == null || clean.length < 2) return null;
  const lowerOrEqual = clean.filter((item) => item <= value).length;
  return (lowerOrEqual / clean.length) * 100;
}

function upperBound(values: number[], target: number) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle] <= target) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low;
}

function lowerBound(values: number[], target: number) {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle] < target) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low;
}

function sortedNumbers(values: number[]) {
  return values.filter((value) => Number.isFinite(value)).sort((left, right) => left - right);
}

const PEER_METRIC_GETTERS: Record<PeerMetricKey, (snapshot: OpenDataStockSnapshot) => number | null> = {
  revenue_cagr_3y: (snapshot) => snapshotMetricValue(snapshot, "business_health", "revenue_cagr_3y"),
  roic: (snapshot) => snapshotMetricValue(snapshot, "business_health", "roic"),
  fcf_yield: (snapshot) => snapshotMetricValue(snapshot, "valuation", "fcf_yield"),
  pe: (snapshot) => snapshotMetricValue(snapshot, "valuation", "pe"),
};

function buildDerivedMetricContext(snapshots: OpenDataStockSnapshot[]): DerivedMetricContext {
  const peerDistributions = Object.fromEntries(
    (Object.keys(PEER_METRIC_GETTERS) as PeerMetricKey[]).map((key) => {
      const getter = PEER_METRIC_GETTERS[key];
      const all: number[] = [];
      const bySector = new Map<string, number[]>();
      snapshots.forEach((snapshot) => {
        const value = getter(snapshot);
        if (value == null) {
          return;
        }
        all.push(value);
        if (snapshot.sector) {
          bySector.set(snapshot.sector, [...(bySector.get(snapshot.sector) ?? []), value]);
        }
      });
      bySector.forEach((values, sector) => bySector.set(sector, sortedNumbers(values)));
      return [key, { all: sortedNumbers(all), bySector }];
    }),
  ) as Record<PeerMetricKey, PeerDistribution>;
  return { peerDistributions };
}

function peerPercentile(
  context: DerivedMetricContext,
  snapshot: OpenDataStockSnapshot,
  key: PeerMetricKey,
  current: number | null,
  higherBetter = true,
) {
  if (current == null) return null;
  const distribution = context.peerDistributions[key];
  const sectorValues = snapshot.sector ? distribution.bySector.get(snapshot.sector) : null;
  const values = sectorValues && sectorValues.length >= 3 ? sectorValues : distribution.all;
  if (values.length < 2) return null;
  const betterOrEqual = higherBetter ? upperBound(values, current) : values.length - lowerBound(values, current);
  return (betterOrEqual / values.length) * 100;
}

function ratio(numerator: number | null, denominator: number | null) {
  if (numerator == null || denominator == null || denominator === 0) return null;
  return numerator / denominator;
}

function pctChangeFromMedian(snapshot: OpenDataStockSnapshot, series: string, metric: string, current: number | null) {
  const values = historicalValues(snapshot, series, metric).map((point) => point.value);
  const middle = median(values);
  if (current == null || middle == null || middle === 0) return null;
  return ((current / middle) - 1) * 100;
}

function derivedMetric(value: number | null, kind: MetricKind, notes: string): DerivedMetric {
  return { value, kind, notes };
}

function computeDerivedMetrics(snapshot: OpenDataStockSnapshot, context: DerivedMetricContext): Record<string, DerivedMetric> {
  const revenueGrowth = snapshotMetricValue(snapshot, "business_health", "revenue_growth_yoy");
  const revenueCagr = snapshotMetricValue(snapshot, "business_health", "revenue_cagr_3y");
  const epsGrowth = snapshotMetricValue(snapshot, "business_health", "eps_growth_yoy");
  const epsCagr = snapshotMetricValue(snapshot, "business_health", "eps_cagr_3y");
  const cash = snapshotMetricValue(snapshot, "business_health", "cash");
  const debt = snapshotMetricValue(snapshot, "business_health", "debt");
  const fcf = snapshotMetricValue(snapshot, "business_health", "free_cash_flow");
  const pe = snapshotMetricValue(snapshot, "valuation", "pe");
  const ps = snapshotMetricValue(snapshot, "valuation", "price_to_sales");
  const fcfYield = snapshotMetricValue(snapshot, "valuation", "fcf_yield");
  const price1y = snapshotMetricValue(snapshot, "price_opportunity", "change_1y");
  const distanceAth = snapshotMetricValue(snapshot, "price_opportunity", "distance_from_ath");
  const netIncome = snapshotFlatMetricValue(snapshot, "net_income_ttm");
  const valuationPeValues = historicalValues(snapshot, "valuation_history", "pe").map((point) => point.value);
  const valuationPsValues = historicalValues(snapshot, "valuation_history", "price_to_sales").map((point) => point.value);
  const valuationFcfYieldValues = historicalValues(snapshot, "valuation_history", "fcf_yield").map((point) => point.value);
  const peHistPercentile = percentileOfValue(valuationPeValues, pe);
  const psHistPercentile = percentileOfValue(valuationPsValues, ps);
  const fcfyHistPercentile = percentileOfValue(valuationFcfYieldValues, fcfYield);
  const netCash = cash == null || debt == null ? null : cash - debt;
  const netDebt = cash == null || debt == null ? null : debt - cash;
  const revAccel = revenueGrowth == null || revenueCagr == null ? null : revenueGrowth - revenueCagr;
  const epsAccel = epsGrowth == null || epsCagr == null ? null : epsGrowth - epsCagr;
  const peVsMedian = pctChangeFromMedian(snapshot, "valuation_history", "pe", pe);
  const priceFundGap = price1y == null || revenueGrowth == null ? null : price1y - revenueGrowth;
  const growthPlusFcfy = revenueCagr == null || fcfYield == null ? null : revenueCagr + fcfYield;
  const fcfConversionRatio = ratio(fcf, netIncome);

  const unusualInputs = [
    peHistPercentile == null ? null : 100 - peHistPercentile,
    fcfyHistPercentile,
    revAccel == null ? null : Math.max(Math.min(50 + revAccel * 2, 100), 0),
    priceFundGap == null ? null : Math.max(Math.min(50 - priceFundGap, 100), 0),
    distanceAth == null ? null : Math.max(Math.min(Math.abs(distanceAth) * 2, 100), 0),
  ].filter((value): value is number => value != null);
  const unusualScore = unusualInputs.length ? unusualInputs.reduce((sum, value) => sum + value, 0) / unusualInputs.length : null;

  return {
    unusual_score: derivedMetric(unusualScore, "ratio", "Composite unusualness score from valuation compression, FCF-yield percentile, growth acceleration, price/fundamental gap, and drawdown."),
    pe_hist_percentile: derivedMetric(peHistPercentile, "percent", "Current PE percentile against available annual valuation history. Higher means more expensive versus its own history."),
    pe_vs_median: derivedMetric(peVsMedian, "percent", "Current PE premium or discount versus available annual valuation-history median."),
    ps_hist_percentile: derivedMetric(psHistPercentile, "percent", "Current price/sales percentile against available annual valuation history."),
    fcfy_hist_percentile: derivedMetric(fcfyHistPercentile, "percent", "Current FCF yield percentile against available annual valuation history. Higher means more attractive cash-flow yield versus its own history."),
    rev_accel: derivedMetric(revAccel, "percent", "Latest-quarter revenue growth YoY minus 3-year revenue CAGR."),
    eps_accel: derivedMetric(epsAccel, "percent", "EPS growth YoY minus 3-year EPS CAGR."),
    op_margin_yoy_delta: derivedMetric(historicalDelta(snapshot, "annual_fundamentals", "operating_margin", 1), "percent", "Latest annual operating margin minus prior-year annual operating margin."),
    fcf_margin_3y_delta: derivedMetric(historicalDelta(snapshot, "annual_fundamentals", "fcf_margin", 3), "percent", "Latest annual FCF margin minus annual FCF margin three periods earlier."),
    fcf_conversion: derivedMetric(fcfConversionRatio == null ? null : fcfConversionRatio * 100, "percent", "TTM free cash flow divided by TTM net income."),
    net_cash: derivedMetric(netCash, "compact", "Cash minus debt. Negative values indicate net debt."),
    net_debt_to_fcf: derivedMetric(ratio(netDebt, fcf), "ratio", "Net debt divided by TTM free cash flow. Negative values indicate net cash."),
    shares_3y_change: derivedMetric(historicalPercentChange(snapshot, "annual_fundamentals", "shares_diluted", 3), "percent", "Latest annual diluted shares versus three annual periods earlier. Negative suggests buybacks; positive suggests dilution."),
    pe_to_rev_cagr: derivedMetric(ratio(pe, revenueCagr), "ratio", "Trailing PE divided by 3-year revenue CAGR percentage."),
    growth_plus_fcfy: derivedMetric(growthPlusFcfy, "percent", "3-year revenue CAGR plus current FCF yield."),
    sector_rev_rank: derivedMetric(peerPercentile(context, snapshot, "revenue_cagr_3y", revenueCagr), "percent", "Revenue CAGR percentile within sector when enough peers exist, otherwise within the loaded universe."),
    sector_roic_rank: derivedMetric(peerPercentile(context, snapshot, "roic", snapshotMetricValue(snapshot, "business_health", "roic")), "percent", "ROIC percentile within sector when enough peers exist, otherwise within the loaded universe."),
    sector_fcfy_rank: derivedMetric(peerPercentile(context, snapshot, "fcf_yield", fcfYield), "percent", "FCF-yield percentile within sector when enough peers exist, otherwise within the loaded universe."),
    sector_pe_cheap_rank: derivedMetric(peerPercentile(context, snapshot, "pe", pe, false), "percent", "Cheapness percentile by PE within sector when enough peers exist, otherwise within the loaded universe. Higher means lower PE than more peers."),
    price_fund_gap: derivedMetric(priceFundGap, "percent", "1-year price change minus latest-quarter revenue growth YoY. Negative values can flag price weakness despite business growth."),
  };
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

function sortValueFor(
  snapshot: OpenDataStockSnapshot,
  analysis: StockEntryAnalysis | undefined,
  sortKey: string,
  derivedByTicker: Record<string, Record<string, DerivedMetric>>,
): SortValue {
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

  if (sortKey.startsWith("derived:")) {
    const key = sortKey.slice("derived:".length);
    return derivedByTicker[snapshot.ticker]?.[key]?.value ?? null;
  }

  return null;
}

function filterValueFor(
  snapshot: OpenDataStockSnapshot,
  analysis: StockEntryAnalysis | undefined,
  field: string,
  derivedByTicker: Record<string, Record<string, DerivedMetric>>,
) {
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
  if (field.startsWith("derived:")) {
    const key = field.slice("derived:".length);
    const metric = derivedByTicker[snapshot.ticker]?.[key];
    if (!metric) return "";
    return metric.value == null ? "-" : String(metric.value);
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

function quarterlyRevenueGrowthPoints(snapshot: OpenDataStockSnapshot) {
  return sortedHistoricalRows(snapshot, "quarterly_revenue")
    .map((row) => ({ period: row.period, value: metricValue(row, "revenue_growth_yoy") }))
    .filter((point): point is { period: string; value: number } => point.value != null);
}

function revenueGrowthSignal(value?: number | null): { label: string; tone: Tone; detail: string } {
  if (value == null) return { label: "Unclear", tone: "neutral", detail: "Comparable quarterly revenue YoY is unavailable." };
  if (value >= 20) return { label: "Strong", tone: "good", detail: "Latest-quarter revenue YoY is at least 20%." };
  if (value >= 8) return { label: "Solid", tone: "good", detail: "Latest-quarter revenue YoY is at least 8%." };
  if (value >= 0) return { label: "Mixed", tone: "watch", detail: "Latest-quarter revenue YoY is positive but below 8%." };
  return { label: "Weak", tone: "caution", detail: "Latest-quarter revenue YoY is negative." };
}

function formatSignedPp(value?: number | null) {
  if (value == null) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatRatio(value)} pp`;
}

function revenueGrowthMomentum(snapshot: OpenDataStockSnapshot): {
  label: string;
  tone: Tone;
  change: number | null;
  latest?: { period: string; value: number };
  previous?: { period: string; value: number };
  detail: string;
} {
  const points = quarterlyRevenueGrowthPoints(snapshot);
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  if (!latest || !previous) {
    return {
      label: "Unclear",
      tone: "neutral",
      change: null,
      detail: "Needs at least two comparable quarterly revenue YoY points.",
    };
  }

  const change = latest.value - previous.value;
  if (change >= 3) {
    return {
      label: "Accelerating",
      tone: "good",
      change,
      latest,
      previous,
      detail: `${latest.period} revenue YoY is ${formatSignedPp(change)} above ${previous.period}.`,
    };
  }
  if (change <= -3) {
    return {
      label: "Decelerating",
      tone: "caution",
      change,
      latest,
      previous,
      detail: `${latest.period} revenue YoY is ${formatSignedPp(change)} below ${previous.period}.`,
    };
  }
  return {
    label: "Stable",
    tone: "watch",
    change,
    latest,
    previous,
    detail: `${latest.period} revenue YoY is within 3 pp of ${previous.period}.`,
  };
}

function QuarterlyRevenueGrowthBarChart({ snapshot }: { snapshot: OpenDataStockSnapshot }) {
  const points = quarterlyRevenueGrowthPoints(snapshot);
  const [hoveredPoint, setHoveredPoint] = useState<{ period: string; value: number; x: number; y: number } | null>(null);
  if (points.length === 0) {
    return (
      <div className="temp-bar-chart empty-chart">
        <strong>Latest-quarter revenue YoY</strong>
        <small>No comparable quarterly revenue growth history from SEC facts.</small>
      </div>
    );
  }

  const width = Math.max(620, points.length * 22 + 80);
  const height = 220;
  const left = 52;
  const right = 18;
  const top = 18;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const values = points.map((point) => point.value);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const spread = max - min || 1;
  const yFor = (value: number) => top + ((max - value) / spread) * plotHeight;
  const zeroY = yFor(0);
  const gap = 4;
  const barWidth = Math.max(6, plotWidth / points.length - gap);
  const slotWidth = plotWidth / points.length;
  const tooltipWidth = 118;
  const tooltipHeight = 44;
  const tooltipX = hoveredPoint ? Math.min(width - right - tooltipWidth, Math.max(left, hoveredPoint.x - tooltipWidth / 2)) : 0;
  const tooltipY = hoveredPoint ? Math.max(top, hoveredPoint.y - tooltipHeight - 8) : 0;

  return (
    <div className="temp-bar-chart">
      <div className="mini-chart-heading">
        <strong>Latest-quarter revenue YoY</strong>
        <small>
          {points.length} comparable quarters, latest {points[points.length - 1].period}{" "}
          {formatPercent(points[points.length - 1].value)}
        </small>
      </div>
      <div className="temp-bar-chart-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${snapshot.ticker} quarterly revenue growth YoY`}>
          <line x1={left} x2={width - right} y1={zeroY} y2={zeroY} className="zero-line" />
          <text x={left - 8} y={top + 4} textAnchor="end">
            {formatPercent(max)}
          </text>
          <text x={left - 8} y={zeroY + 4} textAnchor="end">
            0%
          </text>
          <text x={left - 8} y={top + plotHeight} textAnchor="end">
            {formatPercent(min)}
          </text>
          {points.map((point, index) => {
            const x = left + index * slotWidth + gap / 2;
            const y = point.value >= 0 ? yFor(point.value) : zeroY;
            const barHeight = Math.max(1, Math.abs(zeroY - yFor(point.value)));
            const labelEvery = Math.max(1, Math.ceil(points.length / 6));
            const labelVisible =
              index === 0 || index === points.length - 1 || (index % labelEvery === 0 && index < points.length - 2);
            const [yearLabel, quarterLabel] = point.period.replace("FY", "").split(" ");
            const tooltipPoint = {
              period: point.period,
              value: point.value,
              x: x + barWidth / 2,
              y: Math.min(y, zeroY),
            };
            return (
              <g key={point.period}>
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  rx={2}
                  className={point.value >= 0 ? "positive" : "negative"}
                />
                <rect
                  x={left + index * slotWidth}
                  y={top}
                  width={slotWidth}
                  height={plotHeight}
                  className="bar-hit-area"
                  tabIndex={0}
                  aria-label={`${point.period}: ${formatPercent(point.value)}`}
                  onFocus={() => setHoveredPoint(tooltipPoint)}
                  onBlur={() => setHoveredPoint(null)}
                  onMouseEnter={() => setHoveredPoint(tooltipPoint)}
                  onMouseLeave={() => setHoveredPoint(null)}
                />
                {labelVisible && (
                  <text x={x + barWidth / 2} y={height - 18} textAnchor="middle">
                    <tspan x={x + barWidth / 2}>{yearLabel}</tspan>
                    <tspan x={x + barWidth / 2} dy="11">
                      {quarterLabel}
                    </tspan>
                  </text>
                )}
              </g>
            );
          })}
          {hoveredPoint && (
            <g className="temp-bar-tooltip" transform={`translate(${tooltipX} ${tooltipY})`} pointerEvents="none">
              <rect width={tooltipWidth} height={tooltipHeight} rx={6} />
              <text x={10} y={17} className="tooltip-period">
                {hoveredPoint.period}
              </text>
              <text x={10} y={34} className={`tooltip-value ${hoveredPoint.value >= 0 ? "positive" : "negative"}`}>
                {formatPercent(hoveredPoint.value)}
              </text>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

function StocksInsightsTempTable({
  snapshots,
}: {
  snapshots: OpenDataStockSnapshot[];
}) {
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const rows = [...snapshots].sort((left, right) => left.ticker.localeCompare(right.ticker));
  const toggleExpandedRow = (ticker: string) => {
    setExpandedRows((current) => ({ ...current, [ticker]: !current[ticker] }));
  };

  return (
    <section className="panel open-data-stocks-temp">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>Stocks Insights temp</h2>
        </div>
        <div className="panel-heading-actions">
          <span>{rows.length}</span>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="empty block">No open-data stock metrics loaded.</p>
      ) : (
        <div className="table-wrap">
          <table className="open-data-table exploration-temp-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Latest revenue growth YoY</th>
                <th>Momentum revenue growth YoY</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((snapshot) => {
                const revenueGrowth = snapshot.business_health.revenue_growth_yoy;
                const growthSignal = revenueGrowthSignal(revenueGrowth?.value);
                const momentum = revenueGrowthMomentum(snapshot);
                const rowExpanded = Boolean(expandedRows[snapshot.ticker]);
                return (
                  <Fragment key={snapshot.ticker}>
                    <tr className={rowExpanded ? "exploration-row-expanded" : ""}>
                      <td>
                        <div className="ticker-cell-main">
                          <button
                            type="button"
                            className="icon-button row-toggle exploration-row-toggle"
                            onClick={() => toggleExpandedRow(snapshot.ticker)}
                            title={rowExpanded ? "Hide quarterly revenue chart" : "Show quarterly revenue chart"}
                            aria-expanded={rowExpanded}
                          >
                            {rowExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </button>
                          <strong>{snapshot.ticker}</strong>
                        </div>
                        <small>{snapshot.name ?? `CIK ${snapshot.cik ?? "-"}`}</small>
                      </td>
                      <td title={revenueGrowth ? `${growthSignal.detail}\n${revenueGrowth.notes}\n${revenueGrowth.source}` : growthSignal.detail}>
                        <span className={`analysis-tag table-assessment-tag ${growthSignal.tone}`}>{growthSignal.label}</span>
                        <small>{formatValue(revenueGrowth, "percent")}</small>
                      </td>
                      <td title={momentum.detail}>
                        <span className={`analysis-tag table-assessment-tag ${momentum.tone}`}>{momentum.label}</span>
                        <small>
                          {momentum.change == null
                            ? "Needs 2 quarters"
                            : `${formatSignedPp(momentum.change)} vs ${momentum.previous?.period ?? "previous quarter"}`}
                        </small>
                      </td>
                    </tr>
                    {rowExpanded && (
                      <tr className="exploration-detail-row temp-chart-row">
                        <td colSpan={3}>
                          <QuarterlyRevenueGrowthBarChart snapshot={snapshot} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
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

export const OpenDataStockTable = memo(function OpenDataStockTable({
  snapshots,
  selectedTicker,
  loading,
  analyses,
  analysisLoading,
  onSelectTicker,
}: Props) {
  const [openDetail, setOpenDetail] = useState<DetailKind>(null);
  const [query, setQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState<FilterValue[]>([]);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [activeFilterField, setActiveFilterField] = useState("sector");
  const [legendOpen, setLegendOpen] = useState(false);
  const [sortKey, setSortKey] = useState("symbol");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);
  const [columnOrder, setColumnOrder] = useState(() => DEFAULT_MOVABLE_COLUMNS.map((column) => column.id));
  const [visibleColumnIds, setVisibleColumnIds] = useState(() => DEFAULT_VISIBLE_COLUMN_IDS);
  const [columnMenuOpen, setColumnMenuOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [draggedColumn, setDraggedColumn] = useState<string | null>(null);
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.ticker === selectedTicker) ?? snapshots[0] ?? null;
  const selectedAnalysis = selectedSnapshot ? analyses[selectedSnapshot.ticker] ?? null : null;
  const columnsById = useMemo(() => new Map(DEFAULT_MOVABLE_COLUMNS.map((column) => [column.id, column])), []);
  const derivedContext = useMemo(() => buildDerivedMetricContext(snapshots), [snapshots]);
  const derivedByTicker = useMemo(
    () =>
      Object.fromEntries(
        snapshots.map((snapshot) => [snapshot.ticker, computeDerivedMetrics(snapshot, derivedContext)]),
      ) as Record<string, Record<string, DerivedMetric>>,
    [derivedContext, snapshots],
  );

  const orderedColumns = useMemo(() => {
    const knownIds = new Set(DEFAULT_MOVABLE_COLUMNS.map((column) => column.id));
    const ordered = columnOrder
      .filter((id) => knownIds.has(id))
      .map((id) => columnsById.get(id))
      .filter((column): column is ColumnDefinition => Boolean(column));
    const missing = DEFAULT_MOVABLE_COLUMNS.filter((column) => !columnOrder.includes(column.id));
    return [...ordered, ...missing];
  }, [columnOrder, columnsById]);
  const visibleColumns = useMemo(
    () => orderedColumns.filter((column) => visibleColumnIds.includes(column.id)),
    [orderedColumns, visibleColumnIds],
  );
  const hiddenColumns = useMemo(
    () => orderedColumns.filter((column) => !visibleColumnIds.includes(column.id)),
    [orderedColumns, visibleColumnIds],
  );

  const filterDimensions = useMemo<FilterDimension[]>(() => {
    if (!filterMenuOpen && activeFilters.length === 0) {
      return [];
    }

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
      ...DERIVED_COLUMNS.map((column) => ({
        field: column.id,
        label: column.label,
        values: uniqueOptions(
          snapshots.map((snapshot) => {
            const metric = derivedByTicker[snapshot.ticker]?.[column.derivedKey ?? ""];
            const label = formatByKind(metric?.value, column.metricKind ?? metric?.kind ?? "ratio");
            return { value: metric?.value == null ? "-" : String(metric.value), label };
          }),
        ),
      })),
      ...METRIC_COLUMNS.map((column) => ({
        field: column.id,
        label: column.label,
        values: uniqueOptions(
          snapshots.map((snapshot) => {
            const metric = snapshot[column.group as MetricGroup]?.[column.key ?? ""];
            const isSupportSignal = column.group === "price_opportunity" && column.key === "support_1d_distance";
            const label = isSupportSignal ? formatSupportSignal(metric?.value) : formatValue(metric, column.metricKind ?? "ratio");
            return { value: metric?.value == null ? label : String(metric.value), label };
          }),
        ),
      })),
    ].filter((dimension) => dimension.values.length > 0);
  }, [activeFilters.length, analyses, derivedByTicker, filterMenuOpen, snapshots]);

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
        const matchesActiveFilters = activeFilters.every(
          (filter) => filterValueFor(snapshot, analysis, filter.field, derivedByTicker) === filter.value,
        );

        return matchesQuery && matchesActiveFilters;
      })
      .sort((left, right) => {
        const comparison = compareSortValues(
          sortValueFor(left, analyses[left.ticker], sortKey, derivedByTicker),
          sortValueFor(right, analyses[right.ticker], sortKey, derivedByTicker),
          sortDirection,
        );
        return comparison || left.ticker.localeCompare(right.ticker);
      });
  }, [
    analyses,
    activeFilters,
    query,
    derivedByTicker,
    snapshots,
    sortDirection,
    sortKey,
  ]);
  const totalPages = Math.max(1, Math.ceil(visibleSnapshots.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedSnapshots = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return visibleSnapshots.slice(start, start + PAGE_SIZE);
  }, [currentPage, visibleSnapshots]);

  useEffect(() => {
    setPage(1);
  }, [activeFilters, query, sortDirection, sortKey]);

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

  const toggleColumnVisibility = (columnId: string) => {
    setVisibleColumnIds((ids) => {
      if (ids.includes(columnId)) {
        return ids.length === 1 ? ids : ids.filter((id) => id !== columnId);
      }
      return [...ids, columnId];
    });
  };

  const resetVisibleColumns = () => setVisibleColumnIds(DEFAULT_VISIBLE_COLUMN_IDS);

  const toggleExpandedRow = (ticker: string) => {
    setExpandedRows((rows) => ({
      ...rows,
      [ticker]: !rows[ticker],
    }));
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
      const isSupportSignal = column.group === "price_opportunity" && column.key === "support_1d_distance";
      return (
        <td key={column.id} title={metric ? `${column.label}: ${metric.notes}\n${metric.source}` : column.label}>
          <strong>{isSupportSignal ? formatSupportSignal(metric?.value) : formatValue(metric, column.metricKind ?? "ratio")}</strong>
          {metric && (
            <small>
              {isSupportSignal ? "Daily zones" : `Source period ${metric.as_of}`}
              <br />
              {tierLabel(metric.tier)}
            </small>
          )}
        </td>
      );
    }

    if (column.kind === "derived" && column.derivedKey) {
      const metric = derivedByTicker[snapshot.ticker]?.[column.derivedKey];
      return (
        <td
          key={column.id}
          className="derived-metric-cell"
          title={metric ? `${column.label}: ${metric.notes}` : `${column.label}: Not enough collected facts to compute.`}
        >
          <strong>{formatByKind(metric?.value, column.metricKind ?? metric?.kind ?? "ratio")}</strong>
          <small>derived</small>
        </td>
      );
    }

    return <td key={column.id}>-</td>;
  };

  const renderColumnDetail = (snapshot: OpenDataStockSnapshot, analysis: StockEntryAnalysis | undefined, column: ColumnDefinition) => {
    if (column.id === "conviction") {
      return (
        <article className="exploration-metric-card" key={column.id}>
          <span>{column.label}</span>
          <strong>{analysis ? analysis.conviction.toFixed(1) : analysisLoading ? "..." : "-"}</strong>
          <small>AI analysis</small>
        </article>
      );
    }

    if (column.id === "business" || column.id === "price" || column.id === "valuation") {
      const section = analysisSectionFor(analysis, column.id);
      const firstNote = section?.evidence[0] ?? section?.concerns[0] ?? "AI assessment";
      return (
        <article className="exploration-metric-card" key={column.id}>
          <span>{column.label}</span>
          <div className="exploration-metric-value">
            <AssessmentTag section={section} />
          </div>
          <small>{firstNote}</small>
        </article>
      );
    }

    if (column.id === "sector") {
      return (
        <article className="exploration-metric-card" key={column.id}>
          <span>{column.label}</span>
          <strong>{snapshot.sector ?? "-"}</strong>
          <small>{snapshot.industry ?? snapshot.exchange ?? "-"}</small>
        </article>
      );
    }

    if (column.kind === "metric" && column.group && column.key) {
      const metric = snapshot[column.group][column.key];
      const isSupportSignal = column.group === "price_opportunity" && column.key === "support_1d_distance";
      return (
        <article
          className="exploration-metric-card"
          key={column.id}
          title={metric ? `${column.label}: ${metric.notes}\n${metric.source}` : column.label}
        >
          <span>{column.label}</span>
          <strong>{isSupportSignal ? formatSupportSignal(metric?.value) : formatValue(metric, column.metricKind ?? "ratio")}</strong>
          {metric && (
            <small>
              {tierLabel(metric.tier)}
              <br />
              {isSupportSignal ? "Daily zones" : `Source period ${metric.as_of}`}
            </small>
          )}
        </article>
      );
    }

    if (column.kind === "derived" && column.derivedKey) {
      const metric = derivedByTicker[snapshot.ticker]?.[column.derivedKey];
      return (
        <article
          className="exploration-metric-card derived"
          key={column.id}
          title={metric ? `${column.label}: ${metric.notes}` : `${column.label}: Not enough collected facts to compute.`}
        >
          <span>{column.label}</span>
          <strong>{formatByKind(metric?.value, column.metricKind ?? metric?.kind ?? "ratio")}</strong>
          <small>derived</small>
        </article>
      );
    }

    return (
      <article className="exploration-metric-card" key={column.id}>
        <span>{column.label}</span>
        <strong>-</strong>
      </article>
    );
  };

  return (
    <>
    <StocksInsightsTempTable snapshots={snapshots} />
    <section className="panel open-data-stocks">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>Stocks Insights</h2>
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
          <span>{pagedSnapshots.length} / {visibleSnapshots.length} / {snapshots.length}</span>
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
                onClick={() => {
                  setColumnMenuOpen(false);
                  setFilterMenuOpen((open) => !open);
                }}
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
            <div className="column-menu">
              <button
                type="button"
                className={`filter-menu-trigger ${columnMenuOpen ? "active" : ""}`}
                onClick={() => {
                  setFilterMenuOpen(false);
                  setColumnMenuOpen((open) => !open);
                }}
                aria-expanded={columnMenuOpen}
              >
                <SlidersHorizontal size={16} aria-hidden="true" />
                Columns
                <span>{visibleColumns.length}</span>
              </button>
              {columnMenuOpen && (
                <div className="column-popover">
                  <div className="column-option-list">
                    {orderedColumns.map((column) => {
                      const checked = visibleColumnIds.includes(column.id);
                      return (
                        <label className="column-option" key={column.id}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={checked && visibleColumns.length === 1}
                            onChange={() => toggleColumnVisibility(column.id)}
                          />
                          <span>{column.label}</span>
                        </label>
                      );
                    })}
                  </div>
                  <button type="button" className="filter-clear" onClick={resetVisibleColumns}>
                    Default columns
                  </button>
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
          {visibleSnapshots.length > PAGE_SIZE && (
            <div className="table-pagination" aria-label="Stocks table pagination">
              <button
                type="button"
                className="icon-button"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={currentPage === 1}
                title="Previous page"
              >
                <ChevronLeft size={18} aria-hidden="true" />
              </button>
              <strong>{currentPage} / {totalPages}</strong>
              <button
                type="button"
                className="icon-button"
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                disabled={currentPage === totalPages}
                title="Next page"
              >
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            </div>
          )}
          <div className="table-wrap">
            <table
              className="open-data-table exploration-metrics-table"
              style={{ minWidth: Math.max(760, 230 + visibleColumns.length * 132) }}
            >
              <thead>
                <tr>
                  <th className="sticky-symbol-column">{renderSortHeader("symbol", "Symbol")}</th>
                  {visibleColumns.map((column) => renderDraggableHeader(column))}
                </tr>
              </thead>
              <tbody>
                {pagedSnapshots.map((snapshot) => {
                  const isSelected = selectedSnapshot?.ticker === snapshot.ticker;
                  const analysis = analyses[snapshot.ticker];
                  const rowExpanded = Boolean(expandedRows[snapshot.ticker]);
                  return (
                    <Fragment key={snapshot.ticker}>
                      <tr className={rowExpanded ? "exploration-row-expanded" : ""}>
                        <td className="sticky-symbol-column">
                          <div className="ticker-cell-main">
                            <button
                              type="button"
                              className="icon-button row-toggle exploration-row-toggle"
                              onClick={() => toggleExpandedRow(snapshot.ticker)}
                              title={rowExpanded ? "Hide hidden values" : "Show hidden values"}
                              aria-expanded={rowExpanded}
                            >
                              {rowExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
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
                          <span className="latest-badge">Fetched {formatDateTime(snapshot.generated_at)}</span>
                        </td>
                        {visibleColumns.map((column) => renderColumnCell(snapshot, analysis, column))}
                      </tr>
                      {rowExpanded && (
                        <tr className="exploration-detail-row">
                          <td colSpan={visibleColumns.length + 1}>
                            <div className="exploration-detail-panel">
                              <div className="lot-lifecycle-heading">
                                <strong>All hidden values for {snapshot.ticker}</strong>
                                <span>Fetched {formatDateTime(snapshot.generated_at)}</span>
                              </div>
                              {hiddenColumns.length > 0 ? (
                                <div className="exploration-metric-grid">
                                  {hiddenColumns.map((column) => renderColumnDetail(snapshot, analysis, column))}
                                </div>
                              ) : (
                                <p className="empty block">No hidden columns.</p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
                {visibleSnapshots.length === 0 && (
                  <tr>
                    <td colSpan={visibleColumns.length + 1}>
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
    </>
  );
});
