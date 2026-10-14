import { calculateRevenueGrowthMomentum, formatMomentumPp, revenueMomentumDetail, REVENUE_MOMENTUM_DESCRIPTION } from "../revenueGrowthMomentum";
import { MoneyPanel } from "./MoneyPanel";
import { prepareStockAnalysis, type StockAnalysisBrief } from "../aiAnalysis";
import { StockAnalysisDialog, type AnalysisCopyStatus } from "./StockAnalysisDialog";
import { FilterSelector, type FilterShortcut } from "./FilterSelector";
import { WatchlistDialog, WatchlistGroups, type WatchlistGroupActions } from "./WatchlistGroups";
import type { WatchlistGroup, WatchlistItem } from "../watchlist";
import { MetricStatus } from "./MetricStatus";
import { fcfMarginSignal, forwardPeSignal, growthSignal, metricSignal, revenueGrowthSignal, supportSignal, type MetricSignal as Signal, type MetricTone as Tone } from "../metricStatus";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BookmarkCheck,
  BookmarkPlus,
  Check,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  LogIn,
  Plus,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchOpenDataStockPriceHistory,
  type OpenDataMetric,
  type OpenDataPricePoint,
  type OpenDataStockSnapshot,
} from "../api";
import {
  EARNINGS_THIS_WEEK_FILTER_KEY,
  PULLBACK_FILTER_KEY,
  SUPPORT_FILTER_KEY,
  savedFilterKey,
  type SavedFilter,
  type SaveFilterInput,
} from "../personalization";

type Props = {
  snapshots: OpenDataStockSnapshot[];
  selectedTicker: string;
  loading: boolean;
  onSelectTicker: (ticker: string) => void;
  routeDetailOpen?: boolean;
  onCloseDetail?: () => void;
  actions?: ReactNode;
  headerActions?: (openTicker: (ticker: string) => void) => ReactNode;
  editMode?: boolean;
  removingTicker?: string | null;
  onRemoveStock?: (ticker: string) => void;
  personalization?: {
    signedIn: boolean;
    userId: string | null;
    savedFilters: SavedFilter[];
    watchlistTickers: string[];
    watchlistItems: WatchlistItem[];
    watchlistGroups: WatchlistGroup[];
    watchlistLoading: boolean;
    watchlistLoadError: string | null;
    onReloadWatchlist: () => Promise<void>;
    filterBadgeCounts: Record<string, number>;
    onRequestSignIn: () => Promise<void>;
    onSaveFilter: (input: Omit<SaveFilterInput, "userId">) => Promise<SavedFilter>;
    onDeleteFilter: (filterId: string) => Promise<void>;
    onAddToWatchlist: (ticker: string, groupId?: string | null) => Promise<void>;
    onRemoveFromWatchlist: (ticker: string) => Promise<void>;
  } & WatchlistGroupActions;
};

type GrowthDetailKey =
  | "revenue"
  | "momentum"
  | "eps_gaap"
  | "fcf_margin"
  | "upcoming_earnings"
  | "support"
  | "forward_pe";
export type FilterKey =
  | "revenue"
  | "momentum"
  | "eps"
  | "fcf_margin"
  | "valuation"
  | "forward_pe"
  | "upcoming_earnings"
  | "support_1m"
  | "support_3m"
  | "support_6m"
  | "support_1y"
  | "support_2y"
  | "support_5y";
export type SortKey = "watchlist_order" | "symbol" | "support_best" | Exclude<FilterKey, "forward_pe">;
export type SortDirection = "asc" | "desc";
const SPACE_TABS = ["explore", "watchlist", "portfolio"] as const;
type SpaceTab = typeof SPACE_TABS[number];
type StockListTab = Exclude<SpaceTab, "portfolio">;
type StockListView = {
  query: string;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
  savedFilterId: string | null;
  page: number;
};
export type LogicOperator = "and" | "or";
export type FilterCondition = {
  id: string;
  field: FilterKey;
  value: string;
};
export type FilterGroup = {
  id: string;
  operator: LogicOperator;
  conditions: FilterCondition[];
};
export type FilterExpression = {
  operator: LogicOperator;
  groups: FilterGroup[];
};
type ChartRange = "1W" | "1M" | "3M" | "6M" | "1Y" | "2Y" | "5Y" | "ALL";
type MetricKind = "percent" | "ratio" | "compact" | "price" | "days";

const GROWTH_DETAIL_COPY: Record<GrowthDetailKey, { title: string; question: string; description: string }> = {
  revenue: {
    title: "Latest Revenue Growth YoY",
    question: "Is the business growing right now?",
    description:
      "Compares the company's revenue in its latest reported quarter with the same quarter one year earlier. It shows how quickly the company's sales are growing or declining. For example, +15% means the company generated 15% more revenue than in the same quarter last year.",
  },
  momentum: {
    title: "Revenue Growth Momentum",
    question: "Is the company's growth getting stronger or weaker?",
    description:
      REVENUE_MOMENTUM_DESCRIPTION,
  },
  eps_gaap: {
    title: "GAAP EPS Growth YoY",
    question: "Are reported earnings improving?",
    description:
      "GAAP EPS growth shows reported accounting earnings per share versus the same quarter last year. It can be affected by unusual gains, charges, or accounting items, so use it alongside cash-flow and margin metrics.",
  },
  fcf_margin: {
    title: "Free Cash Flow Margin",
    question: "Is the company turning revenue into actual cash?",
    description:
      "Compares trailing-12-month free cash flow with trailing-12-month revenue. TTM is used because a single quarter can be noisy when collections, inventory, working capital, or capex timing shift cash flow around.",
  },
  forward_pe: {
    title: "Forward P/E",
    question: "What are you paying for expected earnings?",
    description:
      "Compares the current share price with expected earnings per share over the next 12 months. It is a compact first-pass valuation check, not a full valuation model.",
  },
  upcoming_earnings: {
    title: "Upcoming Earnings",
    question: "Is there an earnings catalyst coming soon?",
    description:
      "Counts the days until the next expected earnings release date or earnings window. Earnings releases can be catalysts for sharp price moves, so a lower value means the next scheduled information event is closer.",
  },
  support: {
    title: "Proximity to Support",
    question: "Is the current price close to a nearby support zone?",
    description:
      "Compares the current price with a detected support zone from recent daily price history. Support means a clustered swing-low area with enough touches to look like a practical floor, not just the lowest price in the range.",
  },
};

type FilterDefinition = {
  key: FilterKey;
  label: string;
  shortLabel: string;
  section: "Growth" | "Quality" | "Catalyst" | "Support";
  description: string;
  options: Array<{ label: string; tone: Tone }>;
};

const SUPPORT_KEYS: Record<Extract<FilterKey, `support_${string}`>, string> = {
  support_1m: "support_1m_distance",
  support_3m: "support_3m_distance",
  support_6m: "support_6m_distance",
  support_1y: "support_1y_distance",
  support_2y: "support_2y_distance",
  support_5y: "support_5y_distance",
};

const SUPPORT_FILTER_KEYS = ["support_1m", "support_3m", "support_6m", "support_1y", "support_2y", "support_5y"] as const;
const PULLBACK_SUPPORT_FILTER_KEYS = ["support_1m", "support_3m", "support_6m"] as const;
const SUPPORT_PRESET_FILTER_KEYS = ["support_1y", "support_2y", "support_5y"] as const;
type SupportFilterKey = typeof SUPPORT_FILTER_KEYS[number];
type BuiltInPreset = "pullback" | "support" | "earnings";
type BuiltInPresetCopy = {
  name: string;
  summary: string;
};

const FILTER_DEFINITIONS: FilterDefinition[] = [
  {
    key: "revenue",
    label: "Latest revenue growth YoY",
    shortLabel: "Revenue YoY",
    section: "Growth",
    description: "Year-over-year revenue growth in the latest reported quarter.",
    options: ["Strong", "Solid", "Flat", "Weak", "Unclear"].map(metricSignal),
  },
  {
    key: "momentum",
    label: "Revenue growth momentum",
    shortLabel: "Momentum",
    section: "Growth",
    description: "Change in revenue growth rate versus the previous quarter.",
    options: ["Accelerating", "Stable", "Decelerating", "Unclear"].map(metricSignal),
  },
  {
    key: "eps",
    label: "GAAP EPS growth YoY",
    shortLabel: "GAAP EPS",
    section: "Growth",
    description: "Reported GAAP earnings-per-share growth in the latest quarter.",
    options: ["Strong", "Solid", "Modest", "Weak", "Unclear"].map(metricSignal),
  },
  {
    key: "fcf_margin",
    label: "Free cash flow margin",
    shortLabel: "FCF Mgn",
    section: "Quality",
    description: "Trailing-12-month free cash flow divided by trailing-12-month revenue.",
    options: ["Strong", "Solid", "Thin", "Weak", "Unclear"].map(metricSignal),
  },
  {
    key: "valuation",
    label: "Valuation",
    shortLabel: "Valuation",
    section: "Quality",
    description: "Composite valuation check using forward P/E, FCF yield, price/sales, and EV/EBITDA when available.",
    options: ["Cheap", "Fair", "Pricey", "Very pricey", "Unclear"].map(metricSignal),
  },
  {
    key: "forward_pe",
    label: "Forward P/E",
    shortLabel: "Forward P/E",
    section: "Quality",
    description: "Expected earnings multiple: Cheap is positive and up to 18×; Fair is above 18× and up to 25×. Missing or non-positive values are Unclear.",
    options: ["Cheap", "Fair", "Pricey", "Very pricey", "Unclear"].map(metricSignal),
  },
  {
    key: "upcoming_earnings",
    label: "Upcoming earnings",
    shortLabel: "Earnings",
    section: "Catalyst",
    description: "Days until the next expected earnings release date or earnings window.",
    options: ["This week", "Next 30 days", "Later", "Unclear"].map(metricSignal),
  },
  ...(["1m", "3m", "6m", "1y", "2y", "5y"] as const).map((range) => ({
    key: `support_${range}` as FilterKey,
    label: `Near ${range.toUpperCase()} support`,
    shortLabel: `${range.toUpperCase()} support`,
    section: "Support" as const,
    description: `Distance from the ${range.toUpperCase()} support level. Closer to 0% means nearer support.`,
    options: ["At support", "Near support", "Above support", "Far"].map(metricSignal),
  })),
];

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "watchlist_order", label: "Group order" },
  { key: "symbol", label: "Symbol" },
  { key: "support_best", label: "Priority support" },
  ...FILTER_DEFINITIONS.flatMap(({ key, shortLabel }) => key === "forward_pe" ? [] : [{ key, label: shortLabel }]),
];

const CHART_RANGES: Array<{ key: ChartRange; days: number | null }> = [
  { key: "1W", days: 7 },
  { key: "1M", days: 30 },
  { key: "3M", days: 91 },
  { key: "6M", days: 182 },
  { key: "1Y", days: 365 },
  { key: "2Y", days: 365 * 2 },
  { key: "5Y", days: 365 * 5 },
  { key: "ALL", days: null },
];
const PAGE_SIZE = 10;

function finiteNumber(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatNumber(value?: number | null, maximumFractionDigits = 2) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

function formatPercent(value?: number | null, signed = false) {
  if (value == null) return "-";
  return `${signed && value > 0 ? "+" : ""}${formatNumber(value)}%`;
}

function formatPrice(value?: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: value < 10 ? 4 : 2,
  }).format(value);
}

function formatChartPrice(value: number) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) < 100 ? 1 : 0,
  }).format(value);
}

function formatCompact(value?: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function formatMetric(metric: OpenDataMetric | undefined, kind: MetricKind) {
  if (!metric) return "-";
  const value = finiteNumber(metric.value);
  if (value == null) {
    const notes = metric.notes.toLowerCase();
    if (notes.includes("not meaningful")) return "Not meaningful";
    if (notes.includes("turned positive")) return "Turnaround";
    return "-";
  }
  if (kind === "percent") return formatPercent(value, true);
  if (kind === "compact") return formatCompact(value);
  if (kind === "price") return formatPrice(value);
  if (kind === "days") return `${formatNumber(value)}d`;
  return formatNumber(value);
}

function valuationSignal(snapshot: OpenDataStockSnapshot): Signal {
  const forwardPe = finiteNumber(snapshot.valuation.forward_pe?.value);
  const fcfYield = finiteNumber(snapshot.valuation.fcf_yield?.value);
  const priceSales = finiteNumber(snapshot.valuation.price_to_sales?.value);
  const evToEbitda = finiteNumber(snapshot.valuation.ev_to_ebitda?.value);

  if (forwardPe == null && fcfYield == null && priceSales == null && evToEbitda == null) {
    return metricSignal("Unclear");
  }
  if (
    (forwardPe != null && forwardPe >= 50)
    || (fcfYield != null && fcfYield < 1)
    || (priceSales != null && priceSales >= 20)
    || (evToEbitda != null && evToEbitda >= 40)
  ) {
    return metricSignal("Very pricey");
  }
  if (
    (forwardPe != null && forwardPe >= 35)
    || (fcfYield != null && fcfYield < 2)
    || (priceSales != null && priceSales >= 12)
    || (evToEbitda != null && evToEbitda >= 25)
  ) {
    return metricSignal("Pricey");
  }
  if (
    forwardPe != null
    && forwardPe <= 18
    && (fcfYield == null || fcfYield >= 4)
    && (priceSales == null || priceSales <= 8)
  ) {
    return metricSignal("Cheap");
  }
  if (
    (forwardPe != null && forwardPe <= 25)
    || (fcfYield != null && fcfYield >= 3)
    || (priceSales != null && priceSales <= 8)
  ) {
    return metricSignal("Fair");
  }
  return metricSignal("Unclear");
}

function valuationSortScore(snapshot: OpenDataStockSnapshot) {
  const signal = valuationSignal(snapshot);
  const rank = ["Cheap", "Fair", "Pricey", "Very pricey", "Unclear"].indexOf(signal.label);
  const forwardPe = finiteNumber(snapshot.valuation.forward_pe?.value);
  const pe = finiteNumber(snapshot.valuation.pe?.value);
  return (rank < 0 ? 4 : rank) * 1000 + (forwardPe ?? pe ?? 999);
}

function valuationDetailText(snapshot: OpenDataStockSnapshot) {
  return [
    `Forward P/E: ${formatMetric(snapshot.valuation.forward_pe, "ratio")}.`,
    `FCF yield: ${formatMetric(snapshot.valuation.fcf_yield, "percent")}.`,
    `P/S: ${formatMetric(snapshot.valuation.price_to_sales, "ratio")}.`,
    `EV/EBITDA: ${formatMetric(snapshot.valuation.ev_to_ebitda, "ratio")}.`,
  ].join(" ");
}

function upcomingEarningsMetric(snapshot: OpenDataStockSnapshot) {
  return snapshot.price_opportunity.days_to_next_earnings ?? snapshot.metrics.days_to_next_earnings;
}

function upcomingEarningsSignal(metric?: OpenDataMetric): Signal {
  const days = finiteNumber(metric?.value);
  return metricSignal(days == null ? "Unclear" : days <= 7 ? "This week" : days <= 30 ? "Next 30 days" : "Later");
}

function epsGaapMetric(snapshot: OpenDataStockSnapshot) {
  return snapshot.business_health.eps_gaap_growth_yoy ?? snapshot.business_health.eps_growth_yoy;
}

function historicalRowSortValue(row: OpenDataStockSnapshot["historical_series"][string][number]) {
  const asOf = Date.parse(`${row.as_of}T00:00:00Z`);
  return Number.isFinite(asOf) ? asOf : null;
}

function historicalRows(snapshot: OpenDataStockSnapshot, series: string) {
  return [...(snapshot.historical_series[series] ?? [])].sort((left, right) => {
    const leftDate = historicalRowSortValue(left);
    const rightDate = historicalRowSortValue(right);
    if (leftDate != null && rightDate != null && leftDate !== rightDate) return leftDate - rightDate;
    if (leftDate != null && rightDate == null) return -1;
    if (leftDate == null && rightDate != null) return 1;
    return left.period.localeCompare(right.period, undefined, { numeric: true, sensitivity: "base" });
  });
}

function metricValue(row: OpenDataStockSnapshot["historical_series"][string][number], key: string) {
  return finiteNumber(row.metrics[key]?.value);
}

function revenueGrowthPoints(snapshot: OpenDataStockSnapshot) {
  return historicalRows(snapshot, "quarterly_revenue")
    .map((row) => ({ period: row.period, value: metricValue(row, "revenue_growth_yoy") }))
    .filter((point): point is { period: string; value: number } => point.value != null);
}

function periodParts(period: string) {
  const match = /^FY(\d+)\s+(Q[1-4])$/.exec(period);
  return match ? { year: Number(match[1]), quarter: match[2] } : null;
}

function revenueGrowthDetail(snapshot: OpenDataStockSnapshot) {
  const rows = historicalRows(snapshot, "quarterly_revenue");
  const latest = [...rows].reverse().find((row) => metricValue(row, "revenue_growth_yoy") != null);
  if (!latest) return null;
  const parts = periodParts(latest.period);
  const prior = parts
    ? rows.find((row) => {
        const priorParts = periodParts(row.period);
        return priorParts?.year === parts.year - 1 && priorParts.quarter === parts.quarter;
      })
    : null;
  return {
    latest,
    prior,
    latestRevenue: metricValue(latest, "revenue"),
    priorRevenue: prior ? metricValue(prior, "revenue") : null,
    growth: latest.metrics.revenue_growth_yoy,
  };
}

function quarterlyGrowthPoints(snapshot: OpenDataStockSnapshot, metric: string) {
  const points = historicalRows(snapshot, "quarterly_fundamentals")
    .map((row) => ({ period: row.period, value: metricValue(row, metric), parts: periodParts(row.period) }))
    .filter((point): point is { period: string; value: number; parts: { year: number; quarter: string } } =>
      point.value != null && point.parts != null,
    );
  const byQuarter = new Map(points.map((point) => [`${point.parts.year}:${point.parts.quarter}`, point]));
  return points
    .map((point) => {
      const prior = byQuarter.get(`${point.parts.year - 1}:${point.parts.quarter}`);
      if (!prior || prior.value <= 0 || point.value <= 0) return null;
      return { period: point.period, value: ((point.value - prior.value) / Math.abs(prior.value)) * 100 };
    })
    .filter((point): point is { period: string; value: number } => point != null);
}

function quarterlyMetricPoints(snapshot: OpenDataStockSnapshot, metric: string) {
  return historicalRows(snapshot, "quarterly_fundamentals")
    .map((row) => ({ period: row.period, value: metricValue(row, metric) }))
    .filter((point): point is { period: string; value: number } => point.value != null);
}

function revenueMomentum(snapshot: OpenDataStockSnapshot) {
  const momentum = calculateRevenueGrowthMomentum(snapshot);
  return { ...momentum, tone: metricSignal(momentum.label).tone };
}

function inferredSupportLevel(currentPrice?: number | null, supportDistance?: number | null) {
  if (currentPrice == null || supportDistance == null) return null;
  const divisor = 1 + supportDistance / 100;
  return divisor > 0 ? currentPrice / divisor : null;
}

function signalFor(snapshot: OpenDataStockSnapshot, key: FilterKey): Signal {
  if (key === "revenue") return revenueGrowthSignal(snapshot.business_health.revenue_growth_yoy);
  if (key === "eps") return growthSignal(epsGaapMetric(snapshot));
  if (key === "fcf_margin") return fcfMarginSignal(snapshot.business_health.fcf_margin?.value);
  if (key === "valuation") return valuationSignal(snapshot);
  if (key === "forward_pe") return forwardPeSignal(snapshot.valuation.forward_pe);
  if (key === "momentum") return revenueMomentum(snapshot);
  if (key === "upcoming_earnings") return upcomingEarningsSignal(upcomingEarningsMetric(snapshot));
  return supportSignal(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value);
}

function supportWindows(snapshot: OpenDataStockSnapshot, keys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS) {
  return keys
    .map((key) => ({
      key,
      label: FILTER_DEFINITIONS.find((definition) => definition.key === key)?.shortLabel ?? key,
      window: key.replace("support_", "").toUpperCase(),
      value: finiteNumber(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value),
      metric: snapshot.price_opportunity[SUPPORT_KEYS[key]],
    }))
    .filter((item): item is { key: SupportFilterKey; label: string; window: string; value: number; metric: OpenDataMetric } =>
      item.value != null,
    );
}

function supportTimeframeRank(key: SupportFilterKey) {
  return SUPPORT_FILTER_KEYS.indexOf(key);
}

function supportSignalRank(value: number) {
  if (value <= 2.5) return 0;
  if (value <= 6) return 1;
  if (value <= 25) return 2;
  return 3;
}

function closestSupport(snapshot: OpenDataStockSnapshot, keys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS) {
  return [...supportWindows(snapshot, keys)].sort((left, right) => {
    const signalDelta = supportSignalRank(left.value) - supportSignalRank(right.value);
    if (signalDelta !== 0) return signalDelta;
    const timeframeDelta = supportTimeframeRank(right.key) - supportTimeframeRank(left.key);
    if (timeframeDelta !== 0) return timeframeDelta;
    return Math.abs(left.value) - Math.abs(right.value);
  })[0] ?? null;
}

function sortValue(
  snapshot: OpenDataStockSnapshot,
  key: SortKey,
  supportKeys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS,
): number | string | null {
  if (key === "symbol" || key === "watchlist_order") return snapshot.ticker;
  if (key === "support_best") {
    const support = closestSupport(snapshot, supportKeys);
    return support ? Math.abs(support.value) : null;
  }
  if (key === "revenue") return finiteNumber(snapshot.business_health.revenue_growth_yoy?.value);
  if (key === "eps") return finiteNumber(epsGaapMetric(snapshot)?.value);
  if (key === "fcf_margin") return finiteNumber(snapshot.business_health.fcf_margin?.value);
  if (key === "valuation") return valuationSortScore(snapshot);
  if (key === "momentum") return revenueMomentum(snapshot).change;
  if (key === "upcoming_earnings") return finiteNumber(upcomingEarningsMetric(snapshot)?.value);
  return finiteNumber(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value);
}

function rowMetric(
  snapshot: OpenDataStockSnapshot,
  key: SortKey,
  supportKeys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS,
) {
  if (key === "symbol") {
    const dailyChange = snapshot.price_opportunity.change_1d?.value;
    const dailySignal = metricSignal(dailyChange == null ? "Unavailable" : dailyChange > 0 ? "Up today" : dailyChange < 0 ? "Down today" : "Flat today");
    return {
      value: formatPrice(snapshot.price_opportunity.current_price?.value),
      signal: dailySignal,
      secondary: formatPercent(dailyChange, true),
    };
  }
  if (key === "revenue" || key === "eps") {
    const metric = key === "revenue" ? snapshot.business_health.revenue_growth_yoy : epsGaapMetric(snapshot);
    return { value: formatPercent(metric?.value, true), signal: key === "revenue" ? revenueGrowthSignal(metric) : growthSignal(metric), secondary: null };
  }
  if (key === "fcf_margin") {
    const metric = snapshot.business_health.fcf_margin;
    return { value: formatPercent(metric?.value, true), signal: fcfMarginSignal(metric?.value), secondary: "TTM" };
  }
  if (key === "valuation") {
    return {
      value: formatMetric(snapshot.valuation.forward_pe, "ratio"),
      signal: valuationSignal(snapshot),
      secondary: "Forward P/E",
    };
  }
  if (key === "momentum") {
    const momentum = revenueMomentum(snapshot);
    return {
      value: formatMomentumPp(momentum.change),
      signal: momentum,
      secondary: momentum.latestMovement,
    };
  }
  if (key === "upcoming_earnings") {
    const metric = upcomingEarningsMetric(snapshot);
    return {
      value: formatMetric(metric, "days"),
      signal: upcomingEarningsSignal(metric),
      secondary: "Next report",
    };
  }
  if (key === "support_best" || key === "watchlist_order") {
    const support = closestSupport(snapshot, supportKeys);
    return {
      value: formatPercent(support?.value, true),
      signal: supportSignal(support?.value),
      secondary: support?.window ?? null,
    };
  }
  const value = snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value;
  return { value: formatPercent(value, true), signal: supportSignal(value), secondary: key.replace("support_", "").toUpperCase() };
}

let filterId = 0;

function nextFilterId(prefix: "group" | "condition") {
  filterId += 1;
  return `${prefix}-${filterId}`;
}

function createCondition(field: FilterKey = "revenue", value?: string): FilterCondition {
  const definition = FILTER_DEFINITIONS.find((item) => item.key === field) ?? FILTER_DEFINITIONS[0];
  return {
    id: nextFilterId("condition"),
    field: definition.key,
    value: value ?? definition.options[0].label,
  };
}

function createFilterGroup(field: FilterKey = "revenue"): FilterGroup {
  return {
    id: nextFilterId("group"),
    operator: "or",
    conditions: [createCondition(field)],
  };
}

function createSupportConditions(fields: readonly Extract<FilterKey, `support_${string}`>[]) {
  return fields.flatMap((field) => [
    createCondition(field, "At support"),
    createCondition(field, "Near support"),
  ]);
}

function createValuationConditions(field: "valuation" | "forward_pe" = "valuation") {
  return [
    createCondition(field, "Cheap"),
    createCondition(field, "Fair"),
  ];
}

function createStrongOrSolidYoyGroup(): FilterGroup {
  return {
    id: nextFilterId("group"),
    operator: "or",
    conditions: [createCondition("revenue", "Strong"), createCondition("revenue", "Solid")],
  };
}

function createStrongYoyExpression(preset: BuiltInPreset): FilterExpression {
  const supportFields = preset === "pullback" ? PULLBACK_SUPPORT_FILTER_KEYS : SUPPORT_PRESET_FILTER_KEYS;
  return {
    operator: "and",
    groups: [
      {
        id: nextFilterId("group"),
        operator: "or",
        conditions: createSupportConditions(supportFields),
      },
      createStrongOrSolidYoyGroup(),
      {
        id: nextFilterId("group"),
        operator: "or",
        conditions: createValuationConditions(),
      },
      ...(preset === "pullback" ? [{
        id: nextFilterId("group"),
        operator: "or" as const,
        conditions: createValuationConditions("forward_pe"),
      }] : []),
    ],
  };
}

function createUpcomingEarningsExpression(): FilterExpression {
  return {
    operator: "and",
    groups: [
      {
        id: nextFilterId("group"),
        operator: "or",
        conditions: [
          createCondition("upcoming_earnings", "This week"),
          createCondition("upcoming_earnings", "Next 30 days"),
        ],
      },
      createStrongOrSolidYoyGroup(),
    ],
  };
}

function createBuiltInPresetExpression(preset: BuiltInPreset): FilterExpression {
  return preset === "earnings" ? createUpcomingEarningsExpression() : createStrongYoyExpression(preset);
}

function createEmptyFilterExpression(): FilterExpression {
  return {
    operator: "and",
    groups: [],
  };
}

function activeFilterCount(expression: FilterExpression) {
  return expression.groups.reduce((total, group) => total + group.conditions.length, 0);
}

function filterExpressionMatches(snapshot: OpenDataStockSnapshot, expression: FilterExpression) {
  if (expression.groups.length === 0) return true;
  const groupMatches = expression.groups.map((group) => {
    if (group.conditions.length === 0) return true;
    const matches = group.conditions.map((condition) => signalFor(snapshot, condition.field).label === condition.value);
    return group.operator === "and" ? matches.every(Boolean) : matches.some(Boolean);
  });
  return expression.operator === "and" ? groupMatches.every(Boolean) : groupMatches.some(Boolean);
}

function builtInPresetFor(expression: FilterExpression): BuiltInPreset | null {
  if (expression.operator !== "and") return null;
  const signatures = expression.groups.map((group) => ({
    operator: group.operator,
    conditions: group.conditions.map((condition) => `${condition.field}:${condition.value}`).sort(),
  }));
  const growthSignature = ["revenue:Solid", "revenue:Strong"];
  const hasGrowthGroup = signatures.some(
    (group) => group.operator === "or" && group.conditions.join("|") === growthSignature.join("|"),
  );
  if (!hasGrowthGroup) return null;
  if (
    expression.groups.length === 2
    && signatures.some(
      (group) =>
        group.operator === "or"
        && group.conditions.join("|")
          === "upcoming_earnings:Next 30 days|upcoming_earnings:This week",
    )
  ) {
    return "earnings";
  }
  const valuationSignature = ["valuation:Cheap", "valuation:Fair"];
  const hasValuationGroup = signatures.some(
    (group) => group.operator === "or" && group.conditions.join("|") === valuationSignature.join("|"),
  );
  if (!hasValuationGroup) return null;
  const supportSignature = (fields: readonly Extract<FilterKey, `support_${string}`>[]) => fields
    .flatMap((key) => [`${key}:At support`, `${key}:Near support`])
    .sort()
    .join("|");
  if (
    expression.groups.length === 4
    && signatures.some((group) => group.operator === "or" && group.conditions.join("|") === "forward_pe:Cheap|forward_pe:Fair")
    && signatures.some((group) => group.operator === "or" && group.conditions.join("|") === supportSignature(PULLBACK_SUPPORT_FILTER_KEYS))
  ) {
    return "pullback";
  }
  if (expression.groups.length === 3 && signatures.some((group) => group.operator === "or" && group.conditions.join("|") === supportSignature(SUPPORT_PRESET_FILTER_KEYS))) {
    return "support";
  }
  return null;
}

const BUILT_IN_PRESET_COPY: Record<BuiltInPreset, BuiltInPresetCopy> = {
  support: {
    name: "Strong growth + support",
    summary:
      "Companies with strong latest revenue growth, cheap or fair valuation, and current price at or near support zones identified across the past 1Y, 2Y, and 5Y.",
  },
  pullback: {
    name: "Strong YoY + Pullback + Fair Price",
    summary:
      "Companies with Strong or Solid latest revenue growth YoY, cheap or fair valuation, and Cheap or Fair forward P/E (positive and up to 25×), with price at or near support zones identified across the past 1M, 3M, and 6M.",
  },
  earnings: {
    name: "Growth + upcoming earnings",
    summary: "Companies reporting earnings this week or in the next 30 days with Strong or Solid latest revenue growth YoY.",
  },
};

function builtInPresetName(preset: BuiltInPreset | null) {
  return preset ? BUILT_IN_PRESET_COPY[preset].name : null;
}

function builtInPresetSummary(preset: BuiltInPreset | null) {
  return preset ? BUILT_IN_PRESET_COPY[preset].summary : null;
}

function StockStatus({ signal, context, compact = false }: { signal: Signal; context?: string | null; compact?: boolean }) {
  return (
    <MetricStatus signal={signal} context={context} className={`mobile-status${compact ? " mobile-row-status" : ""}`} />
  );
}

function FilterSheet({
  open,
  expression,
  sortKey,
  sortDirection,
  actions,
  personalization,
  watchlistView = false,
  activeSavedFilterId,
  onClose,
  onApply,
  onExpressionChange,
  onApplyPullbackPreset,
  onApplySupportPreset,
  onApplyEarningsPreset,
  onSortKeyChange,
  onSortDirectionChange,
  onClear,
  onSavedFilter,
}: {
  open: boolean;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
  actions?: ReactNode;
  personalization?: Props["personalization"];
  watchlistView?: boolean;
  activeSavedFilterId: string | null;
  onClose: () => void;
  onApply: () => void;
  onExpressionChange: (expression: FilterExpression) => void;
  onApplyPullbackPreset: () => void;
  onApplySupportPreset: () => void;
  onApplyEarningsPreset: () => void;
  onSortKeyChange: (key: SortKey) => void;
  onSortDirectionChange: (direction: SortDirection) => void;
  onClear: () => void;
  onSavedFilter: (filter: SavedFilter) => void;
}) {
  const [saveName, setSaveName] = useState(() => personalization?.savedFilters.find((filter) => filter.id === activeSavedFilterId)?.name ?? "My stock filter");
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const busyRef = useRef(false);
  useEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog?.showModal();
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [open]);

  if (!open) return null;
  const count = activeFilterCount(expression);
  const builtInPreset = builtInPresetFor(expression);
  const builtInName = builtInPresetName(builtInPreset);
  const activeSavedFilter = personalization?.savedFilters.find((item) => item.id === activeSavedFilterId) ?? null;

  const close = () => {
    if (!busyRef.current) onClose();
  };

  const submitSavedFilter = async () => {
    if (!personalization?.signedIn || !saveName.trim() || count === 0 || busyRef.current) return;
    busyRef.current = true;
    setSaveBusy(true);
    setSaveError(null);
    try {
      const saved = await personalization.onSaveFilter({
        id: activeSavedFilter?.id,
        name: saveName.trim(),
        expression,
        sortKey,
        sortDirection,
      });
      onSavedFilter(saved);
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not save this filter.");
    } finally {
      busyRef.current = false;
      setSaveBusy(false);
    }
  };

  const requestSignIn = async () => {
    if (!personalization || busyRef.current) return;
    busyRef.current = true;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await personalization.onRequestSignIn();
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not start Google sign-in.");
    } finally {
      busyRef.current = false;
      setSaveBusy(false);
    }
  };

  const updateGroup = (groupId: string, update: (group: FilterGroup) => FilterGroup) => {
    onExpressionChange({
      ...expression,
      groups: expression.groups.map((group) => group.id === groupId ? update(group) : group),
    });
  };

  const addGroup = () => {
    onExpressionChange({ ...expression, groups: [...expression.groups, createFilterGroup()] });
  };

  const removeGroup = (groupId: string) => {
    onExpressionChange({ ...expression, groups: expression.groups.filter((group) => group.id !== groupId) });
  };

  const addCondition = (group: FilterGroup) => {
    const nextField = FILTER_DEFINITIONS.find(
      (definition) => !group.conditions.some((condition) => condition.field === definition.key),
    )?.key ?? "revenue";
    updateGroup(group.id, (current) => ({
      ...current,
      conditions: [...current.conditions, createCondition(nextField)],
    }));
  };

  const updateCondition = (groupId: string, conditionId: string, field: FilterKey, value?: string) => {
    const definition = FILTER_DEFINITIONS.find((item) => item.key === field) ?? FILTER_DEFINITIONS[0];
    updateGroup(groupId, (group) => ({
      ...group,
      conditions: group.conditions.map((condition) => condition.id === conditionId
        ? { ...condition, field, value: value ?? definition.options[0].label }
        : condition),
    }));
  };

  const removeCondition = (groupId: string, conditionId: string) => {
    const group = expression.groups.find((item) => item.id === groupId);
    if (!group || group.conditions.length === 1) {
      removeGroup(groupId);
      return;
    }
    updateGroup(groupId, (current) => ({
      ...current,
      conditions: current.conditions.filter((condition) => condition.id !== conditionId),
    }));
  };

  return (
    <dialog ref={dialogRef} className="mobile-builder-dialog" aria-label={activeSavedFilter ? "Edit filter" : "New filter"}
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClick={(event) => { if (event.currentTarget === event.target) close(); }}>
      <section className="mobile-filter-sheet">
        <div className="mobile-sheet-handle" aria-hidden="true" />
        <header className="mobile-sheet-header">
          <div>
            <h2>{activeSavedFilter ? "Edit filter" : "New filter"}</h2>
            <p>Combine metrics to narrow the list.</p>
          </div>
          <button type="button" className="mobile-icon-button" onClick={close} disabled={saveBusy} aria-label="Cancel filter editing">
            <X size={20} />
          </button>
        </header>

        <div className="mobile-sheet-scroll">
          {personalization && (
            <section className="mobile-filter-section mobile-saved-filter-section">
              <div className="mobile-filter-title-row">
                <h3>{activeSavedFilter ? "My filter" : "Save filter"}</h3>
              </div>

              {!personalization.signedIn ? (
                <>
                  <button type="button" className="mobile-signin-filter" disabled={saveBusy} onClick={() => void requestSignIn()}>
                    <LogIn size={18} />
                    <span><strong>Sign in to save filters</strong><small>Sync views and see daily new-match badges.</small></span>
                    <ChevronRight size={17} />
                  </button>
                  {saveError && <p className="mobile-personal-error" role="alert">{saveError}</p>}
                </>
              ) : (
                <div className="mobile-save-filter-form">
                  <label>
                    <span>Filter name</span>
                    <input
                      type="text"
                      value={saveName}
                      onChange={(event) => setSaveName(event.target.value)}
                      maxLength={80}
                      disabled={saveBusy}
                      autoFocus
                    />
                  </label>
                  {saveError && <p className="mobile-personal-error" role="alert">{saveError}</p>}
                  <div className="mobile-save-filter-actions">
                    <button type="button" onClick={close} disabled={saveBusy}>Cancel</button>
                    <button type="button" className="primary" onClick={() => void submitSavedFilter()} disabled={saveBusy || !saveName.trim() || count === 0}>
                      <Save size={16} />{activeSavedFilter ? "Update" : "Save"}
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}

          <section className="mobile-sort-section">
            <div className="mobile-sheet-section-heading">
              <h3>Sort by</h3>
              <div className="mobile-sort-direction" aria-label="Sort direction">
                <button
                  type="button"
                  className={sortDirection === "asc" ? "active" : ""}
                  onClick={() => onSortDirectionChange("asc")}
                  aria-label="Sort ascending"
                  title="Sort ascending"
                >
                  <ArrowUp size={16} />
                </button>
                <button
                  type="button"
                  className={sortDirection === "desc" ? "active" : ""}
                  onClick={() => onSortDirectionChange("desc")}
                  aria-label="Sort descending"
                  title="Sort descending"
                >
                  <ArrowDown size={16} />
                </button>
              </div>
            </div>
            <div className="mobile-chip-scroll">
              {SORT_OPTIONS.filter((option) => option.key !== "watchlist_order" || watchlistView).map((option) => (
                <button
                  type="button"
                  key={option.key}
                  className={`mobile-choice-chip ${sortKey === option.key ? "active" : ""}`}
                  onClick={() => onSortKeyChange(option.key)}
                >
                  {sortKey === option.key && <Check size={14} />}
                  {option.label}
                </button>
              ))}
            </div>
          </section>

          <section className="mobile-filter-section mobile-logic-section">
            <div className="mobile-filter-title-row">
              <h3>Conditions</h3>
              {count > 0 && <span>{count} condition{count === 1 ? "" : "s"}</span>}
            </div>

            <div className="mobile-filter-name">
              <span>{activeSavedFilter ? "Saved filter" : builtInPreset ? "Built-in filter" : "Filter"}</span>
              <strong>{activeSavedFilter?.name ?? builtInName ?? (count > 0 ? "Custom filter" : "No filter selected")}</strong>
              {builtInPreset && <p>{builtInPresetSummary(builtInPreset)}</p>}
            </div>

            {expression.groups.length > 0 ? (
              <>
                {expression.groups.length > 1 && (
                  <div className="mobile-logic-scope">
                    <div>
                      <strong>Between groups</strong>
                      <span>{expression.operator === "and" ? "Every group must match" : "At least one group must match"}</span>
                    </div>
                    <div className="mobile-logic-toggle" aria-label="Logic between condition groups">
                      <button
                        type="button"
                        className={expression.operator === "and" ? "active" : ""}
                        onClick={() => onExpressionChange({ ...expression, operator: "and" })}
                      >
                        AND
                      </button>
                      <button
                        type="button"
                        className={expression.operator === "or" ? "active" : ""}
                        onClick={() => onExpressionChange({ ...expression, operator: "or" })}
                      >
                        OR
                      </button>
                    </div>
                  </div>
                )}

                <div className="mobile-condition-builder">
                  {expression.groups.map((group, groupIndex) => (
                    <div className="mobile-condition-block" key={group.id}>
                      {groupIndex > 0 && <div className="mobile-logic-connector"><span>{expression.operator.toUpperCase()}</span></div>}
                      <article className="mobile-condition-group">
                        <header>
                          <div>
                            <span>Group {groupIndex + 1}</span>
                            <strong>{group.operator === "or" ? "Match any condition" : "Match every condition"}</strong>
                          </div>
                          <button
                            type="button"
                            className="mobile-delete-group"
                            onClick={() => removeGroup(group.id)}
                            aria-label={`Delete group ${groupIndex + 1}`}
                            title="Delete group"
                          >
                            <Trash2 size={16} />
                          </button>
                        </header>

                        <div className="mobile-group-logic">
                          <span>Inside this group</span>
                          <div className="mobile-logic-toggle" aria-label={`Logic inside group ${groupIndex + 1}`}>
                            <button
                              type="button"
                              className={group.operator === "or" ? "active" : ""}
                              onClick={() => updateGroup(group.id, (current) => ({ ...current, operator: "or" }))}
                            >
                              OR
                            </button>
                            <button
                              type="button"
                              className={group.operator === "and" ? "active" : ""}
                              onClick={() => updateGroup(group.id, (current) => ({ ...current, operator: "and" }))}
                            >
                              AND
                            </button>
                          </div>
                        </div>

                        <div className="mobile-condition-list">
                          {group.conditions.map((condition, conditionIndex) => {
                            const definition = FILTER_DEFINITIONS.find((item) => item.key === condition.field) ?? FILTER_DEFINITIONS[0];
                            return (
                              <div className="mobile-condition-wrap" key={condition.id}>
                                {conditionIndex > 0 && <div className="mobile-condition-connector"><span>{group.operator.toUpperCase()}</span></div>}
                                <div className="mobile-condition-row">
                                  <label>
                                    <span>Metric</span>
                                    <select
                                      value={condition.field}
                                      onChange={(event) => updateCondition(group.id, condition.id, event.target.value as FilterKey)}
                                    >
                                      {FILTER_DEFINITIONS.map((item) => <option key={item.key} value={item.key}>{item.shortLabel}</option>)}
                                    </select>
                                  </label>
                                  <label>
                                    <span>Condition</span>
                                    <select
                                      className={`mobile-condition-value metric-status-color metric-tone-${metricSignal(condition.value).tone}`}
                                      value={condition.value}
                                      onChange={(event) => updateCondition(group.id, condition.id, condition.field, event.target.value)}
                                    >
                                      {definition.options.map((option) => <option key={option.label} value={option.label} className={`metric-status-color metric-tone-${option.tone}`}>{option.label}</option>)}
                                    </select>
                                  </label>
                                  <button
                                    type="button"
                                    className="mobile-delete-condition"
                                    onClick={() => removeCondition(group.id, condition.id)}
                                    aria-label={`Remove ${definition.shortLabel} condition`}
                                    title="Remove condition"
                                  >
                                    <X size={16} />
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <button type="button" className="mobile-add-condition" onClick={() => addCondition(group)}>
                          <Plus size={16} />
                          Add condition to group
                        </button>
                      </article>
                    </div>
                  ))}
                </div>

                <button type="button" className="mobile-add-group" onClick={addGroup}>
                  <Plus size={17} />
                  Add another group
                </button>
              </>
            ) : (
              <div className="mobile-filter-empty">
                <Plus size={22} />
                <strong>Build a filter with clear logic</strong>
                <p>Use groups for parentheses, then choose whether groups and conditions use AND or OR.</p>
                <div>
                  <button type="button" onClick={addGroup}><Plus size={16} />New filter</button>
                  <button type="button" onClick={onApplyEarningsPreset}>Use Earnings preset</button>
                  <button type="button" onClick={onApplySupportPreset}>Use Support preset</button>
                  <button type="button" onClick={onApplyPullbackPreset}>Use Pullback preset</button>
                </div>
              </div>
            )}
          </section>

          {actions && (
            <section className="mobile-filter-section mobile-list-management">
              <h3>Watchlist</h3>
              {actions}
            </section>
          )}
        </div>

        <footer className="mobile-sheet-footer">
          <button type="button" className="mobile-clear-button" onClick={onClear} disabled={count === 0}>
            <RotateCcw size={16} />
            Clear
          </button>
          <button type="button" className="mobile-done-button" onClick={onApply} disabled={saveBusy}>
            Show stocks
          </button>
        </footer>
      </section>
    </dialog>
  );
}

function WatchlistSheet({
  snapshots, items, groups, groupId, onClose, onAdd,
}: {
  snapshots: OpenDataStockSnapshot[];
  items: WatchlistItem[];
  groups: WatchlistGroup[];
  groupId: string | null;
  onClose: () => void;
  onAdd: (ticker: string, groupId: string | null) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [targetGroup, setTargetGroup] = useState<string | null>(groupId);
  const [busyTicker, setBusyTicker] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const needle = query.trim().toLowerCase();
  const rows = snapshots.filter((snapshot) => !needle || [snapshot.ticker, snapshot.name, snapshot.sector, snapshot.industry]
    .filter(Boolean).some((value) => String(value).toLowerCase().includes(needle)));
  const groupName = groups.find((group) => group.id === targetGroup)?.name ?? "My Watchlist";
  const add = async (ticker: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyTicker(ticker);
    setError(null);
    try { await onAdd(ticker, targetGroup); }
    catch (exc) { setError(exc instanceof Error ? exc.message : `Could not add ${ticker}.`); }
    finally { busyRef.current = false; setBusyTicker(null); }
  };
  return (
    <WatchlistDialog title="Add symbols" className="watchlist-picker-dialog" onClose={() => { if (!busyRef.current) onClose(); }}>
      <label className="watchlist-picker-target">Add to
        <select value={targetGroup ?? ""} disabled={busyTicker !== null} onChange={(event) => setTargetGroup(event.target.value || null)} aria-label="Destination group">
          {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
          <option value="">My Watchlist</option>
        </select>
      </label>
      <label className="mobile-watchlist-search">
        <Search size={18} />
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a symbol or company"
          aria-label="Find stocks for watchlist" autoFocus autoComplete="off" autoCorrect="off" autoCapitalize="none" enterKeyHint="search" inputMode="search" spellCheck={false} />
        {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear watchlist search"><X size={16} /></button>}
      </label>
      {error && <p className="watchlist-error" role="alert">{error}</p>}
      <div className="mobile-watchlist-picker">
        {rows.map((snapshot) => {
          const item = items.find((entry) => entry.ticker === snapshot.ticker);
          const isAdded = Boolean(item && item.group_id === targetGroup);
          const otherGroup = item ? groups.find((group) => group.id === item.group_id)?.name ?? "My Watchlist" : null;
          return (
            <div className="mobile-watchlist-option" key={snapshot.ticker}>
              <span><strong>{snapshot.ticker}</strong><small>{snapshot.name ?? snapshot.industry ?? ""}</small>
                {otherGroup && !isAdded && <small>In {otherGroup}</small>}
              </span>
              <button type="button" className={isAdded ? "remove" : "add"} disabled={busyTicker !== null || isAdded}
                onClick={() => void add(snapshot.ticker)} aria-label={isAdded ? `${snapshot.ticker} is in ${groupName}` : `${item ? "Move" : "Add"} ${snapshot.ticker} to ${groupName}`}>
                {busyTicker === snapshot.ticker ? "Saving…" : isAdded ? <><Check size={16} />Added</> : item ? "Move" : <><Plus size={16} />Add</>}
              </button>
            </div>
          );
        })}
        {rows.length === 0 && <p className="mobile-watchlist-no-results">No stocks match your search.</p>}
      </div>
      <footer className="mobile-watchlist-footer"><button type="button" disabled={busyTicker !== null} onClick={onClose}>Done</button></footer>
    </WatchlistDialog>
  );
}

function dateValue(value: string) {
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) ? parsed : null;
}

function pointsForRange(points: OpenDataPricePoint[], range: ChartRange) {
  const sorted = points
    .filter((point) => point.close > 0 && Number.isFinite(point.close) && dateValue(point.date) != null)
    .sort((left, right) => (dateValue(left.date) ?? 0) - (dateValue(right.date) ?? 0));
  const days = CHART_RANGES.find((option) => option.key === range)?.days;
  if (days == null) return sorted;
  const latest = sorted[sorted.length - 1];
  if (!latest) return [];
  const cutoff = (dateValue(latest.date) ?? 0) - days * 86_400_000;
  const ranged = sorted.filter((point) => (dateValue(point.date) ?? 0) >= cutoff);
  return ranged.length >= 2 ? ranged : sorted.slice(-2);
}

function supportKeyForRange(range: ChartRange) {
  if (range === "1W" || range === "1M") return "support_1m_distance";
  if (range === "3M") return "support_3m_distance";
  if (range === "6M") return "support_6m_distance";
  if (range === "1Y") return "support_1y_distance";
  if (range === "2Y") return "support_2y_distance";
  return "support_5y_distance";
}

function supportFirstTouchDate(metric?: OpenDataMetric) {
  const match = metric?.notes.match(/first touch (\d{4}-\d{2}-\d{2})/i);
  return match?.[1] ?? null;
}

function PriceChart({ snapshot, points, loading, error }: {
  snapshot: OpenDataStockSnapshot;
  points: OpenDataPricePoint[];
  loading: boolean;
  error: string | null;
}) {
  const [range, setRange] = useState<ChartRange>("1Y");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const ranged = pointsForRange(points, range);
  const width = 720;
  const height = 360;
  const padding = { top: 26, right: 68, bottom: 40, left: 12 };
  const supportKey = supportKeyForRange(range);
  const currentPrice = snapshot.price_opportunity.current_price?.value;
  const supportMetric = snapshot.price_opportunity[supportKey];
  const supportDistance = supportMetric?.value;
  const supportLevel = inferredSupportLevel(currentPrice, supportDistance);
  const values = [...ranged.map((point) => point.close), ...(supportLevel == null ? [] : [supportLevel])];
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const spread = Math.max(max - min, max * 0.02, 1);
  const yMin = min - spread * 0.12;
  const yMax = max + spread * 0.12;
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const xFor = (index: number) => padding.left + (index / Math.max(ranged.length - 1, 1)) * innerWidth;
  const xForDate = (date: string) => {
    const firstDate = ranged[0] ? dateValue(ranged[0].date) : null;
    const lastDate = ranged[ranged.length - 1] ? dateValue(ranged[ranged.length - 1].date) : null;
    const targetDate = dateValue(date);
    if (firstDate == null || lastDate == null || targetDate == null || firstDate === lastDate) return padding.left;
    const clampedDate = Math.max(firstDate, Math.min(lastDate, targetDate));
    return padding.left + ((clampedDate - firstDate) / (lastDate - firstDate)) * innerWidth;
  };
  const yFor = (value: number) => padding.top + ((yMax - value) / Math.max(yMax - yMin, 1)) * innerHeight;
  const path = ranged.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(2)},${yFor(point.close).toFixed(2)}`).join(" ");
  const first = ranged[0];
  const last = ranged[ranged.length - 1];
  const change = first && last ? ((last.close - first.close) / first.close) * 100 : null;
  const selected = ranged[hoverIndex ?? Math.max(ranged.length - 1, 0)];
  const guideParts = [0.25, 0.5, 0.75];
  const dateGuideIndices = Array.from(new Set([0, Math.round((ranged.length - 1) / 2), ranged.length - 1]));
  const supportStartDate = supportFirstTouchDate(supportMetric);
  const supportStartX = supportStartDate ? xForDate(supportStartDate) : padding.left;
  const supportLabelX = Math.min(width - padding.right - 8, supportStartX + 6);
  const dateFormatter = new Intl.DateTimeFormat(undefined, range === "2Y" || range === "5Y" || range === "ALL"
    ? { month: "short", year: "2-digit" }
    : { month: "short", day: "numeric" });

  const onPointerMove = (event: React.PointerEvent<SVGRectElement>) => {
    if (ranged.length === 0) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const relativeX = Math.max(0, Math.min(bounds.width, event.clientX - bounds.left));
    setHoverIndex(Math.round((relativeX / Math.max(bounds.width, 1)) * (ranged.length - 1)));
  };

  const onPointerDown = (event: React.PointerEvent<SVGRectElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    onPointerMove(event);
  };

  const releasePointer = (event: React.PointerEvent<SVGRectElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <section className="mobile-chart-section">
      <div className="mobile-chart-heading">
        <div>
          <span>{range} performance</span>
          <strong className={change != null && change < 0 ? "negative" : "positive"}>{formatPercent(change, true)}</strong>
        </div>
        {selected && (
          <div className="mobile-chart-selection">
            <strong>{formatPrice(selected.close)}</strong>
            <span>{new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${selected.date}T00:00:00Z`))}</span>
          </div>
        )}
      </div>
      {loading ? (
        <div className="mobile-chart-placeholder">Loading price history...</div>
      ) : error ? (
        <div className="mobile-chart-placeholder">{error}</div>
      ) : ranged.length < 2 ? (
        <div className="mobile-chart-placeholder">Price history is unavailable for this range.</div>
      ) : (
        <svg
          className="mobile-price-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${snapshot.ticker} ${range} price chart`}
          onContextMenu={(event) => event.preventDefault()}
        >
          {guideParts.map((part) => (
            <g key={part}>
              <line className="mobile-chart-gridline" x1={padding.left} x2={width - padding.right} y1={padding.top + innerHeight * part} y2={padding.top + innerHeight * part} />
              <text className="mobile-chart-axis-label" x={width - 4} y={padding.top + innerHeight * part}>
                {formatChartPrice(yMax - (yMax - yMin) * part)}
              </text>
            </g>
          ))}
          {supportLevel != null && (
            <g className="mobile-support-line">
              <line x1={supportStartX} x2={width - padding.right} y1={yFor(supportLevel)} y2={yFor(supportLevel)} />
              <text x={supportLabelX} y={yFor(supportLevel) - 7}>{range === "ALL" ? "5Y" : supportKey.split("_")[1].toUpperCase()} support {formatPrice(supportLevel)}</text>
            </g>
          )}
          <path className={`mobile-price-path ${change != null && change < 0 ? "negative" : "positive"}`} d={path} />
          {selected && hoverIndex != null && (
            <g className="mobile-chart-cursor">
              <line x1={xFor(hoverIndex)} x2={xFor(hoverIndex)} y1={padding.top} y2={height - padding.bottom} />
              <circle cx={xFor(hoverIndex)} cy={yFor(selected.close)} r="5" />
            </g>
          )}
          {dateGuideIndices.map((index) => (
            <text
              key={`${ranged[index].date}-${index}`}
              className="mobile-chart-date"
              textAnchor={index === 0 ? "start" : index === ranged.length - 1 ? "end" : "middle"}
              x={xFor(index)}
              y={height - 9}
            >
              {dateFormatter.format(new Date(`${ranged[index].date}T00:00:00Z`))}
            </text>
          ))}
          <rect
            className="mobile-chart-hit"
            x={padding.left}
            y={padding.top}
            width={innerWidth}
            height={innerHeight}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={releasePointer}
            onPointerCancel={releasePointer}
            onPointerLeave={() => setHoverIndex(null)}
          />
        </svg>
      )}
      <div className="mobile-range-control" aria-label="Price chart range">
        {CHART_RANGES.map((option) => (
          <button type="button" key={option.key} className={range === option.key ? "active" : ""} onClick={() => setRange(option.key)}>
            {option.key === "ALL" ? "All" : option.key}
          </button>
        ))}
      </div>
    </section>
  );
}

function GrowthChart({
  title,
  points,
  selectedPeriods,
}: {
  title: string;
  points: Array<{ period: string; value: number }>;
  selectedPeriods?: string[];
}) {
  const [activePoint, setActivePoint] = useState<{ period: string; value: number; x: number; y: number } | null>(null);
  const visible = points.slice(-8);
  if (visible.length === 0) {
    return (
      <article className="mobile-growth-chart">
        <h3>{title}</h3>
        <p>No comparable quarterly history.</p>
      </article>
    );
  }
  const width = 620;
  const height = 220;
  const pad = { top: 26, right: 8, bottom: 34, left: 8 };
  const values = visible.map((point) => point.value);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const spread = Math.max(max - min, 1);
  const yFor = (value: number) => pad.top + ((max - value) / spread) * (height - pad.top - pad.bottom);
  const zeroY = yFor(0);
  const slot = (width - pad.left - pad.right) / visible.length;
  const barWidth = Math.min(slot * 0.62, 48);
  const tooltipWidth = 116;
  const tooltipHeight = 42;
  const tooltipX = activePoint ? Math.min(width - tooltipWidth - 6, Math.max(6, activePoint.x - tooltipWidth / 2)) : 0;
  const tooltipY = activePoint ? Math.max(8, activePoint.y - tooltipHeight - 8) : 0;
  const pointForIndex = (index: number) => {
    const point = visible[index];
    const x = pad.left + slot * index + slot / 2;
    const valueY = yFor(point.value);
    const y = point.value >= 0 ? valueY : zeroY;
    return { period: point.period, value: point.value, x, y: Math.min(y, zeroY) };
  };
  const pointForClientX = (clientX: number, svg: SVGSVGElement) => {
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * width;
    const index = Math.min(visible.length - 1, Math.max(0, Math.floor((x - pad.left) / slot)));
    return pointForIndex(index);
  };

  return (
    <article className="mobile-growth-chart">
      <div className="mobile-growth-heading">
        <h3>{title}</h3>
        <strong className={visible[visible.length - 1].value < 0 ? "negative" : "positive"}>{formatPercent(visible[visible.length - 1].value, true)}</strong>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title} quarterly chart`}>
        <line className="mobile-bar-zero" x1={pad.left} x2={width - pad.right} y1={zeroY} y2={zeroY} />
        {visible.map((point, index) => {
          const x = pad.left + slot * index + (slot - barWidth) / 2;
          const valueY = yFor(point.value);
          const y = point.value >= 0 ? valueY : zeroY;
          const barHeight = Math.max(Math.abs(zeroY - valueY), 2);
          const pointLabel = point.period.replace("FY", "").split(" ");
          const barClassName = [
            point.value >= 0 ? "positive" : "negative",
            selectedPeriods?.includes(point.period) ? "selected" : "",
          ].filter(Boolean).join(" ");
          return (
            <g key={point.period}>
              <rect className={barClassName} x={x} y={y} width={barWidth} height={barHeight} rx="4" />
              <rect
                className="mobile-growth-hit"
                x={pad.left + slot * index}
                y={pad.top}
                width={slot}
                height={height - pad.top - pad.bottom}
                tabIndex={0}
                aria-label={`${point.period}: ${formatPercent(point.value, true)}`}
                onFocus={() => setActivePoint(pointForIndex(index))}
                onBlur={() => setActivePoint(null)}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  setActivePoint(pointForIndex(index));
                }}
                onPointerMove={(event) => {
                  if (event.buttons === 0 && event.pointerType !== "touch") return;
                  const svg = event.currentTarget.ownerSVGElement;
                  if (svg) setActivePoint(pointForClientX(event.clientX, svg));
                }}
                onPointerUp={(event) => {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }}
                onPointerCancel={(event) => {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                  setActivePoint(null);
                }}
              />
              <text x={x + barWidth / 2} y={height - 18} textAnchor="middle">
                <tspan x={x + barWidth / 2}>{pointLabel[0]}</tspan>
                <tspan x={x + barWidth / 2} dy="11">{pointLabel[1]}</tspan>
              </text>
            </g>
          );
        })}
        {activePoint && (
          <g className="mobile-growth-tooltip" transform={`translate(${tooltipX} ${tooltipY})`} pointerEvents="none">
            <rect width={tooltipWidth} height={tooltipHeight} rx="8" />
            <text x="10" y="16" className="tooltip-period">{activePoint.period}</text>
            <text x="10" y="32" className={activePoint.value < 0 ? "negative" : "positive"}>
              {formatPercent(activePoint.value, true)}
            </text>
          </g>
        )}
      </svg>
    </article>
  );
}

function MobileGrowthSignalButton({
  active,
  label,
  signal,
  value,
  onClick,
  className = "",
}: {
  active: boolean;
  label: string;
  signal: Signal;
  value: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button type="button" className={`mobile-growth-signal ${active ? "active" : ""} ${className}`.trim()} onClick={onClick}>
      <span>{label}</span>
      <span className="mobile-growth-signal-summary">
        <StockStatus signal={signal} />
        <strong>{value}</strong>
      </span>
    </button>
  );
}

function MobileGrowthDetailPanel({ snapshot, detailKey }: { snapshot: OpenDataStockSnapshot; detailKey: GrowthDetailKey }) {
  const copy = GROWTH_DETAIL_COPY[detailKey];
  const revenueDetail = revenueGrowthDetail(snapshot);
  const momentum = revenueMomentum(snapshot);
  const epsGaap = epsGaapMetric(snapshot);
  const fcfMarginMetric = snapshot.business_health.fcf_margin;
  const upcomingEarnings = upcomingEarningsMetric(snapshot);
  const support = closestSupport(snapshot);
  const supports = supportWindows(snapshot);
  const currentPrice = finiteNumber(snapshot.price_opportunity.current_price?.value);
  const supportLevel = support ? inferredSupportLevel(currentPrice, support.value) : null;
  if (detailKey === "support") {
    const detailText = support
      ? [
          `Nearest window: ${support.window}.`,
          `Distance from support: ${formatPercent(support.value, true)}.`,
          supportLevel != null && currentPrice != null
            ? `Inferred support level ${formatPrice(supportLevel)} vs current price ${formatPrice(currentPrice)}.`
            : null,
        ].filter(Boolean).join(" ")
      : "No usable support zone was detected from the available open/free price history.";

    return (
      <section className="mobile-growth-detail-panel mobile-support-detail-panel">
        <div className="mobile-growth-copy">
          <span>Metric definition</span>
          <h2>{copy.title}</h2>
          <p className="metric-question">{copy.question}</p>
          <p>{copy.description}</p>
        </div>
        <div className="mobile-growth-formula">
          <span>Current value</span>
          <strong>{formatPercent(support?.value, true)}</strong>
          <StockStatus signal={supportSignal(support?.value)} context={support?.window} />
          <small>{detailText}</small>
          {supports.length > 0 && (
            <div className="mobile-support-window-list" aria-label="All support proximities">
              {supports.map((item) => {
                const level = inferredSupportLevel(currentPrice, item.value);
                return (
                  <div className="mobile-support-window-row" key={item.key}>
                    <StockStatus signal={supportSignal(item.value)} context={item.window} />
                    <strong>{formatPercent(item.value, true)}</strong>
                    <small>{level == null ? "No level" : formatPrice(level)}</small>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    );
  }

  if (detailKey === "forward_pe") {
    const valuationStatus = valuationSignal(snapshot);

    return (
      <section className="mobile-growth-detail-panel">
        <div className="mobile-growth-copy">
          <span>Metric definition</span>
          <h2>{copy.title}</h2>
          <p className="metric-question">{copy.question}</p>
          <p>{copy.description}</p>
        </div>
        <div className="mobile-growth-formula">
          <span>Current value</span>
          <strong>{formatMetric(snapshot.valuation.forward_pe, "ratio")}</strong>
          <StockStatus signal={valuationStatus} />
          <small>{valuationDetailText(snapshot)}</small>
        </div>
      </section>
    );
  }

  if (detailKey === "upcoming_earnings") {
    const signal = upcomingEarningsSignal(upcomingEarnings);
    const days = finiteNumber(upcomingEarnings?.value);
    const detailText = days == null
      ? upcomingEarnings?.notes ?? "The next expected earnings release date is unavailable from the open/free earnings calendar."
      : `${signal.label}: next expected earnings release is in ${formatNumber(days)} days. ${upcomingEarnings?.notes ?? ""}`.trim();

    return (
      <section className="mobile-growth-detail-panel">
        <div className="mobile-growth-copy">
          <span>Metric definition</span>
          <h2>{copy.title}</h2>
          <p className="metric-question">{copy.question}</p>
          <p>{copy.description}</p>
        </div>
        <div className="mobile-growth-formula">
          <span>Current value</span>
          <strong>{formatMetric(upcomingEarnings, "days")}</strong>
          <StockStatus signal={signal} />
          <small>{detailText}</small>
        </div>
      </section>
    );
  }

  const metric = detailKey === "eps_gaap"
    ? epsGaap
    : detailKey === "fcf_margin"
      ? fcfMarginMetric
      : detailKey === "revenue"
        ? snapshot.business_health.revenue_growth_yoy
        : undefined;
  const currentValue = detailKey === "momentum"
    ? formatMomentumPp(momentum.change)
    : formatMetric(metric, "percent");
  const signal = detailKey === "momentum" ? momentum
    : detailKey === "fcf_margin" ? fcfMarginSignal(fcfMarginMetric?.value)
    : detailKey === "eps_gaap" ? growthSignal(epsGaap)
    : revenueGrowthSignal(snapshot.business_health.revenue_growth_yoy);
  const detailText = detailKey === "momentum"
    ? revenueMomentumDetail(momentum)
    : detailKey === "fcf_margin"
      ? fcfMarginMetric?.notes ?? "Trailing-12-month free cash flow margin is unavailable."
    : detailKey === "eps_gaap"
      ? epsGaap?.notes ?? "Comparable quarterly GAAP EPS growth is unavailable."
    : detailKey === "revenue" && revenueDetail?.latestRevenue != null && revenueDetail?.priorRevenue != null
      ? `${revenueDetail.latest.period}: ${formatCompact(revenueDetail.latestRevenue)} vs ${formatCompact(revenueDetail.priorRevenue)} one year earlier.`
      : metric?.notes ?? "Comparable quarterly data is unavailable.";
  const chartTitle = detailKey === "eps_gaap"
    ? "GAAP EPS growth YoY"
    : detailKey === "fcf_margin"
      ? "Quarterly FCF margin"
      : "Revenue growth YoY";
  const chartPoints = detailKey === "eps_gaap"
    ? quarterlyGrowthPoints(snapshot, "eps_diluted")
    : detailKey === "fcf_margin"
      ? quarterlyMetricPoints(snapshot, "fcf_margin")
      : revenueGrowthPoints(snapshot);

  return (
    <section className="mobile-growth-detail-panel">
      <div className="mobile-growth-copy">
        <span>Metric definition</span>
        <h2>{copy.title}</h2>
        <p className="metric-question">{copy.question}</p>
        <p>{copy.description}</p>
      </div>
      <div className="mobile-growth-formula">
        <span>Current value</span>
        <strong>{currentValue}</strong>
        <StockStatus signal={signal} />
        <small>{detailText}</small>
      </div>
      <GrowthChart
        title={chartTitle}
        points={chartPoints}
        selectedPeriods={
          detailKey === "revenue"
            ? revenueDetail?.latest.period ? [revenueDetail.latest.period] : undefined
            : detailKey === "momentum"
              ? momentum.points.map((point) => point.period)
              : undefined
        }
      />
    </section>
  );
}

function StockDetail({ snapshot, onBack }: { snapshot: OpenDataStockSnapshot; onBack: () => void }) {
  const [activeGrowthDetail, setActiveGrowthDetail] = useState<GrowthDetailKey>("revenue");
  const [points, setPoints] = useState<OpenDataPricePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentPrice = snapshot.price_opportunity.current_price?.value;
  const dailyChange = snapshot.price_opportunity.change_1d?.value;
  const revenueSignal = revenueGrowthSignal(snapshot.business_health.revenue_growth_yoy);
  const epsGaap = epsGaapMetric(snapshot);
  const epsGaapSignal = growthSignal(epsGaap);
  const fcfMarginMetric = snapshot.business_health.fcf_margin;
  const fcfMarginStatus = fcfMarginSignal(fcfMarginMetric?.value);
  const valuationStatus = valuationSignal(snapshot);
  const upcomingEarnings = upcomingEarningsMetric(snapshot);
  const upcomingEarningsStatus = upcomingEarningsSignal(upcomingEarnings);
  const momentum = revenueMomentum(snapshot);
  const support = closestSupport(snapshot);
  const supportStatus = supportSignal(support?.value);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setPoints([]);
    fetchOpenDataStockPriceHistory(snapshot.ticker)
      .then((next) => {
        if (active) setPoints(next);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Price history unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [snapshot.ticker]);

  return (
    <div className="mobile-stock-detail">
      <header className="mobile-detail-nav">
        <button type="button" onClick={onBack} className="mobile-back-button">
          <ArrowLeft size={20} />
          Stocks
        </button>
        <span>{snapshot.exchange ?? snapshot.sector ?? "Stock"}</span>
      </header>

      <main className="mobile-detail-main">
        <section className="mobile-detail-hero">
          <div>
            <span>{snapshot.name ?? snapshot.ticker}</span>
            <h1>{snapshot.ticker}</h1>
            <p>{snapshot.industry ?? snapshot.sector ?? ""}</p>
          </div>
          <div className="mobile-detail-price">
            <strong>{formatPrice(currentPrice)}</strong>
            <span className={dailyChange == null || dailyChange === 0 ? undefined : dailyChange < 0 ? "negative" : "positive"}>{formatPercent(dailyChange, true)} today</span>
          </div>
	        </section>
	
	        <PriceChart snapshot={snapshot} points={points} loading={loading} error={error} />

	        <section className="mobile-signal-strip" aria-label="Current growth signals">
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "revenue"}
            label="Latest Revenue Growth YoY"
            signal={revenueSignal}
            value={formatPercent(snapshot.business_health.revenue_growth_yoy?.value, true)}
            onClick={() => setActiveGrowthDetail("revenue")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "momentum"}
            label="Revenue Growth Momentum"
            signal={momentum}
            value={formatMomentumPp(momentum.change)}
            onClick={() => setActiveGrowthDetail("momentum")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "eps_gaap"}
            label="GAAP EPS Growth YoY"
            signal={epsGaapSignal}
            value={formatPercent(epsGaap?.value, true)}
            onClick={() => setActiveGrowthDetail("eps_gaap")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "fcf_margin"}
            label="Free Cash Flow Margin"
            signal={fcfMarginStatus}
            value={formatPercent(fcfMarginMetric?.value, true)}
            onClick={() => setActiveGrowthDetail("fcf_margin")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "forward_pe"}
            label="Forward P/E"
            signal={valuationStatus}
            value={formatMetric(snapshot.valuation.forward_pe, "ratio")}
            onClick={() => setActiveGrowthDetail("forward_pe")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "upcoming_earnings"}
            label="Upcoming Earnings"
            signal={upcomingEarningsStatus}
            value={formatMetric(upcomingEarnings, "days")}
            onClick={() => setActiveGrowthDetail("upcoming_earnings")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "support"}
            className="mobile-support-signal"
            label="Proximity to Support"
            signal={supportStatus}
            value={support?.window ?? "No zone"}
            onClick={() => setActiveGrowthDetail("support")}
          />
        </section>

        <MobileGrowthDetailPanel snapshot={snapshot} detailKey={activeGrowthDetail} />

        <footer className="mobile-detail-footer">
          <span>Updated {new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(snapshot.generated_at))}</span>
          <span>{snapshot.source}</span>
        </footer>
      </main>
    </div>
  );
}

export function MobileStockExplorer({
  snapshots,
  selectedTicker,
  loading,
  onSelectTicker,
  routeDetailOpen,
  onCloseDetail,
  actions,
  headerActions,
  editMode = false,
  removingTicker,
  onRemoveStock,
  personalization,
}: Props) {
  const [query, setQuery] = useState("");
  const [filterExpression, setFilterExpression] = useState<FilterExpression>(() => createEmptyFilterExpression());
  const [sortKey, setSortKey] = useState<SortKey>("support_best");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [filterDraft, setFilterDraft] = useState<{
    expression: FilterExpression;
    sortKey: SortKey;
    sortDirection: SortDirection;
    savedFilterId: string | null;
  }>({ expression: createEmptyFilterExpression(), sortKey: "support_best", sortDirection: "asc", savedFilterId: null });
  const [watchlistOpen, setWatchlistOpen] = useState(false);
  const [watchlistTargetGroup, setWatchlistTargetGroup] = useState<string | null>(null);
  const [spaceTab, setSpaceTab] = useState<SpaceTab>("explore");
  const listViews = useRef<Partial<Record<StockListTab, StockListView>>>({});
  const restoringListPage = useRef<number | null>(null);
  const [savingTicker, setSavingTicker] = useState<string | null>(null);
  const savingWatchlist = useRef(false);
  const [watchlistSaveError, setWatchlistSaveError] = useState<string | null>(null);
  const [addedTicker, setAddedTicker] = useState<string | null>(null);
  const [revealTicker, setRevealTicker] = useState<string | null>(null);
  const currentUser = useRef(personalization?.userId);
  currentUser.current = personalization?.userId;
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeSavedFilterId, setActiveSavedFilterId] = useState<string | null>(null);
  const [analysisMode, setAnalysisMode] = useState(false);
  const [analysisSelection, setAnalysisSelection] = useState<string[]>([]);
  const [analysisBrief, setAnalysisBrief] = useState<StockAnalysisBrief | null>(null);
  const [analysisCopyStatus, setAnalysisCopyStatus] = useState<AnalysisCopyStatus>("copying");
  const analysisCopyRevision = useRef(0);
  const [page, setPage] = useState(1);
  const listTopRef = useRef<HTMLDivElement | null>(null);
  const analysisPrepareRef = useRef<HTMLButtonElement | null>(null);
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.ticker === selectedTicker) ?? null;
  const builtInPreset = builtInPresetFor(filterExpression);
  const activeSavedFilter = personalization?.savedFilters.find((item) => item.id === activeSavedFilterId) ?? null;
  const relevantSupportKeys = builtInPreset === "support"
    ? SUPPORT_PRESET_FILTER_KEYS
    : builtInPreset === "pullback"
      ? PULLBACK_SUPPORT_FILTER_KEYS
      : SUPPORT_FILTER_KEYS;
  const signedIn = personalization?.signedIn ?? false;
  const isWatchlistView = signedIn && spaceTab === "watchlist";
  const watchlistTickers = personalization?.watchlistTickers ?? [];
  const watchlist = useMemo(() => new Set(watchlistTickers), [watchlistTickers]);
  const watchlistItems = personalization?.watchlistItems ?? [];
  const watchlistGroups = personalization?.watchlistGroups ?? [];
  const watchlistOrder = useMemo(() => new Map(watchlistItems.map((item) => [item.ticker, item])), [personalization?.watchlistItems]);
  const groupOrder = useMemo(() => new Map([...watchlistGroups].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))
    .map((group, index) => [group.id, index])), [personalization?.watchlistGroups]);
  const baseSnapshots = useMemo(
    () => isWatchlistView ? snapshots.filter((snapshot) => watchlist.has(snapshot.ticker)) : snapshots,
    [isWatchlistView, snapshots, watchlist],
  );

  const visibleSnapshots = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return baseSnapshots
      .filter((snapshot) => {
        const matchesSearch = !needle || [snapshot.ticker, snapshot.name, snapshot.sector, snapshot.industry]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(needle));
        return matchesSearch && filterExpressionMatches(snapshot, filterExpression);
      })
      .sort((left, right) => {
        if (isWatchlistView) {
          const leftItem = watchlistOrder.get(left.ticker);
          const rightItem = watchlistOrder.get(right.ticker);
          const rank = (id?: string | null) => id ? groupOrder.get(id) ?? groupOrder.size : groupOrder.size;
          const groupDifference = rank(leftItem?.group_id) - rank(rightItem?.group_id);
          if (groupDifference) return groupDifference;
          if (sortKey === "watchlist_order") return ((leftItem?.position ?? 0) - (rightItem?.position ?? 0)) * (sortDirection === "asc" ? 1 : -1) || left.ticker.localeCompare(right.ticker);
        }
        const leftValue = sortValue(left, sortKey, relevantSupportKeys);
        const rightValue = sortValue(right, sortKey, relevantSupportKeys);
        if (leftValue == null && rightValue == null) return left.ticker.localeCompare(right.ticker);
        if (leftValue == null) return 1;
        if (rightValue == null) return -1;
        const comparison = typeof leftValue === "number" && typeof rightValue === "number"
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue), undefined, { numeric: true, sensitivity: "base" });
        return (sortDirection === "asc" ? comparison : -comparison) || left.ticker.localeCompare(right.ticker);
      });
  }, [baseSnapshots, filterExpression, query, relevantSupportKeys, sortDirection, sortKey, isWatchlistView, watchlistOrder, groupOrder]);
  const expandedSnapshots = useMemo(() => {
    const collapsed = new Set(watchlistGroups.filter((group) => group.collapsed).map((group) => group.id));
    return isWatchlistView ? visibleSnapshots.filter((snapshot) => !collapsed.has(watchlistOrder.get(snapshot.ticker)?.group_id ?? "")) : visibleSnapshots;
  }, [visibleSnapshots, isWatchlistView, personalization?.watchlistGroups, watchlistOrder]);
  const totalPages = Math.max(1, Math.ceil(expandedSnapshots.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = expandedSnapshots.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(currentPage * PAGE_SIZE, expandedSnapshots.length);
  const pagedSnapshots = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return expandedSnapshots.slice(start, start + PAGE_SIZE);
  }, [currentPage, expandedSnapshots]);
  const listSummaryLabel = totalPages > 1
    ? `${pageStart}–${pageEnd} of ${expandedSnapshots.length} stocks`
    : `${visibleSnapshots.length} stock${visibleSnapshots.length === 1 ? "" : "s"}`;

  const filterCount = activeFilterCount(filterExpression);
  const latestMarketDate = snapshots.reduce((latest, snapshot) => {
    const asOf = snapshot.price_opportunity.current_price?.as_of?.slice(0, 10) ?? "";
    return asOf > latest ? asOf : latest;
  }, "");
  const dateLabel = latestMarketDate
    ? new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" })
      .format(new Date(`${latestMarketDate}T12:00:00Z`))
    : "";

  useEffect(() => {
    setPage(restoringListPage.current ?? 1);
    restoringListPage.current = null;
  }, [filterExpression, query, sortDirection, sortKey, spaceTab]);

  useEffect(() => {
    listViews.current = {};
    restoringListPage.current = null;
    setSpaceTab("explore");
    setQuery("");
    setPage(1);
    setSortKey("support_best");
    setSortDirection("asc");
    setFilterExpression(createEmptyFilterExpression());
    setActiveSavedFilterId(null);
    setSheetOpen(false);
    setWatchlistOpen(false);
    setSavingTicker(null);
    setWatchlistSaveError(null);
    setAddedTicker(null);
    setRevealTicker(null);
    setAnalysisMode(false);
    setAnalysisSelection([]);
    setAnalysisBrief(null);
    analysisCopyRevision.current++;
  }, [personalization?.userId]);

  useEffect(() => {
    if (!revealTicker || !isWatchlistView) return;
    const index = expandedSnapshots.findIndex((snapshot) => snapshot.ticker === revealTicker);
    if (index < 0) return;
    setPage(Math.floor(index / PAGE_SIZE) + 1);
    setRevealTicker(null);
  }, [revealTicker, isWatchlistView, expandedSnapshots]);

  useEffect(() => {
    if (!addedTicker) return;
    const timeout = window.setTimeout(() => setAddedTicker(null), 6000);
    return () => window.clearTimeout(timeout);
  }, [addedTicker]);

  useEffect(() => {
    const availableTickers = new Set(snapshots.map((snapshot) => snapshot.ticker));
    setAnalysisSelection((tickers) => tickers.filter((ticker) => availableTickers.has(ticker)));
  }, [snapshots]);

  useEffect(() => {
    setPage((value) => Math.min(value, totalPages));
  }, [totalPages]);

  useEffect(() => {
    if (routeDetailOpen === undefined) return;
    setDetailOpen(routeDetailOpen);
  }, [routeDetailOpen]);

  const goToPage = (nextPage: number) => {
    const boundedPage = Math.max(1, Math.min(totalPages, nextPage));
    if (boundedPage === currentPage) return;
    setPage(boundedPage);
    window.requestAnimationFrame(() => {
      listTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const clearFilter = () => {
    setFilterExpression(createEmptyFilterExpression());
    setActiveSavedFilterId(null);
  };

  const applyBuiltInPreset = (preset: BuiltInPreset) => {
    setFilterExpression(createBuiltInPresetExpression(preset));
    setSortKey(preset === "earnings" ? "upcoming_earnings" : preset === "pullback" ? "support_1m" : "support_best");
    setSortDirection("asc");
    setActiveSavedFilterId(null);
  };

  const savedExpression = (filter: SavedFilter): FilterExpression => ({
    ...filter.expression,
    groups: filter.expression.groups.map((group) => ({
      ...group,
      conditions: group.conditions.map((condition) => ({
        ...condition,
        // Preserve filters saved before metric-specific labels were introduced.
        value: condition.value === "Mixed" && condition.field === "eps" ? "Modest"
          : condition.value === "Mixed" && condition.field === "fcf_margin" ? "Thin"
            : condition.value,
      })),
    })),
  });

  const selectSavedFilter = (filter: SavedFilter) => {
    setFilterExpression(savedExpression(filter));
    setSortKey(filter.sort_key === "watchlist_order" && !isWatchlistView ? "support_best" : filter.sort_key);
    setSortDirection(filter.sort_direction);
    setActiveSavedFilterId(filter.id);
  };

  const openFilterBuilder = (filter?: SavedFilter) => {
    setFilterDraft({
      expression: filter ? savedExpression(filter) : { operator: "and", groups: [createFilterGroup()] },
      sortKey: filter?.sort_key === "watchlist_order" && !isWatchlistView ? "support_best" : filter?.sort_key ?? sortKey,
      sortDirection: filter?.sort_direction ?? sortDirection,
      savedFilterId: filter?.id ?? null,
    });
    setSheetOpen(true);
  };

  const applyFilterDraft = () => {
    const saved = personalization?.savedFilters.find((filter) => filter.id === filterDraft.savedFilterId);
    setFilterExpression(filterDraft.expression);
    setSortKey(filterDraft.sortKey === "watchlist_order" && !isWatchlistView ? "support_best" : filterDraft.sortKey);
    setSortDirection(filterDraft.sortDirection);
    setActiveSavedFilterId(saved && JSON.stringify(savedExpression(saved)) === JSON.stringify(filterDraft.expression) ? saved.id : null);
    setSheetOpen(false);
  };

  const applyDraftPreset = (preset: BuiltInPreset) => {
    setFilterDraft((draft) => ({ ...draft, expression: createBuiltInPresetExpression(preset) }));
  };

  const defaultShortcuts: Array<FilterShortcut & { preset: BuiltInPreset }> = [
    { key: SUPPORT_FILTER_KEY, name: BUILT_IN_PRESET_COPY.support.name, isDefault: true, preset: "support" },
    { key: PULLBACK_FILTER_KEY, name: BUILT_IN_PRESET_COPY.pullback.name, isDefault: true, preset: "pullback" },
    { key: EARNINGS_THIS_WEEK_FILTER_KEY, name: BUILT_IN_PRESET_COPY.earnings.name, isDefault: true, preset: "earnings" },
  ];
  const filterShortcuts: FilterShortcut[] = [
    ...defaultShortcuts,
    ...(personalization?.savedFilters ?? []).map((filter) => ({ key: savedFilterKey(filter.id), name: filter.name, isDefault: false })),
  ].map((filter) => ({ ...filter, badgeCount: personalization?.filterBadgeCounts[filter.key] }));
  const activeShortcutKey = activeSavedFilter ? savedFilterKey(activeSavedFilter.id)
    : defaultShortcuts.find((filter) => filter.preset === builtInPreset)?.key ?? null;
  const activeFilterName = filterCount > 0 ? activeSavedFilter?.name ?? builtInPresetName(builtInPreset) ?? "Custom filter" : null;

  const startAnalysis = () => {
    setAnalysisSelection([]);
    setAnalysisMode(true);
  };

  const cancelAnalysis = () => {
    setAnalysisMode(false);
    setAnalysisSelection([]);
    setAnalysisBrief(null);
    analysisCopyRevision.current++;
  };

  const selectSpaceTab = (tab: SpaceTab) => {
    if (tab === spaceTab) return;
    if (spaceTab !== "portfolio") {
      listViews.current[spaceTab] = {
        query, expression: filterExpression, sortKey, sortDirection,
        savedFilterId: activeSavedFilterId, page: currentPage,
      };
    }
    setSpaceTab(tab);
    cancelAnalysis();
    setWatchlistSaveError(null);
    if (tab === "portfolio") return;
    const view = listViews.current[tab];
    restoringListPage.current = view?.page ?? 1;
    setQuery(view?.query ?? "");
    setFilterExpression(view?.expression ?? createEmptyFilterExpression());
    setSortKey(view?.sortKey ?? (tab === "watchlist" ? "watchlist_order" : "support_best"));
    setSortDirection(view?.sortDirection ?? "asc");
    setActiveSavedFilterId(view?.savedFilterId ?? null);
    setPage(view?.page ?? 1);
  };

  const toggleWatchlistFromExplore = async (ticker: string) => {
    if (!personalization || savingWatchlist.current) return;
    const isSaved = watchlist.has(ticker);
    const userId = personalization.userId;
    savingWatchlist.current = true;
    setSavingTicker(ticker);
    setWatchlistSaveError(null);
    setAddedTicker(null);
    try {
      if (isSaved) await personalization.onRemoveFromWatchlist(ticker);
      else await personalization.onAddToWatchlist(ticker);
      if (!isSaved && currentUser.current === userId) setAddedTicker(ticker);
    } catch (exc) {
      if (currentUser.current === userId) setWatchlistSaveError(exc instanceof Error ? exc.message : `Could not ${isSaved ? "remove" : "add"} ${ticker}. Please try again.`);
    } finally {
      savingWatchlist.current = false;
      if (currentUser.current === userId) setSavingTicker(null);
    }
  };

  const viewAddedStock = () => {
    selectSpaceTab("watchlist");
    setQuery("");
    clearFilter();
    setSortKey("watchlist_order");
    setSortDirection("asc");
    setRevealTicker(addedTicker);
    setAddedTicker(null);
    document.getElementById("space-watchlist-tab")?.focus();
  };

  const toggleAnalysisSelection = (ticker: string) => {
    setAnalysisSelection((tickers) => (
      tickers.includes(ticker)
        ? tickers.filter((item) => item !== ticker)
        : [...tickers, ticker]
    ));
  };

  const copyAnalysisPrompt = async (prompt: string) => {
    const revision = ++analysisCopyRevision.current;
    setAnalysisCopyStatus("copying");
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard is unavailable.");
      await navigator.clipboard.writeText(prompt);
      if (revision === analysisCopyRevision.current) setAnalysisCopyStatus("copied");
    } catch {
      if (revision === analysisCopyRevision.current) setAnalysisCopyStatus("error");
    }
  };

  const closeAnalysisBrief = () => {
    analysisCopyRevision.current++;
    setAnalysisBrief(null);
  };

  const prepareSelectedStocks = () => {
    const selectedSnapshots = analysisSelection.flatMap((ticker) => {
      const snapshot = snapshots.find((item) => item.ticker === ticker);
      return snapshot ? [snapshot] : [];
    });
    if (selectedSnapshots.length === 0) return;
    analysisPrepareRef.current?.focus({ preventScroll: true });
    const brief = prepareStockAnalysis(selectedSnapshots, activeFilterName ?? "All stocks");
    setAnalysisBrief(brief);
    // Start the clipboard write in the tap handler so mobile browsers retain user activation.
    void copyAnalysisPrompt(brief.prompt);
  };

  const openDetail = (ticker: string) => {
    onSelectTicker(ticker);
    setDetailOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const closeDetail = () => {
    setDetailOpen(false);
    onCloseDetail?.();
  };

  const renderStockRow = (snapshot: OpenDataStockSnapshot) => {
    const metric = rowMetric(snapshot, sortKey, relevantSupportKeys);
    const analysisSelected = analysisSelection.includes(snapshot.ticker);
    return (
      <article className={`mobile-stock-row ${analysisSelected ? "analysis-selected" : ""}`} key={snapshot.ticker}>
        <button
          type="button"
          className={`mobile-stock-row-main ${analysisMode ? "analysis-selecting" : ""}`}
          onClick={() => analysisMode ? toggleAnalysisSelection(snapshot.ticker) : openDetail(snapshot.ticker)}
          aria-pressed={analysisMode ? analysisSelected : undefined}
        >
          {analysisMode && (
            <span className={`mobile-analysis-check ${analysisSelected ? "selected" : ""}`} aria-hidden="true">
              {analysisSelected && <Check size={14} />}
            </span>
          )}
          <div className="mobile-stock-identity">
            <strong>{snapshot.ticker}</strong>
            <span>{snapshot.name ?? snapshot.industry ?? ""}</span>
          </div>
          <div className="mobile-stock-value">
            <strong>{metric.value}</strong>
            <StockStatus signal={metric.signal} context={metric.secondary} compact />
          </div>
        </button>
        {signedIn && spaceTab === "explore" && !analysisMode && !editMode && (
          <button type="button" className={`mobile-watchlist-bookmark${watchlist.has(snapshot.ticker) || savingTicker === snapshot.ticker ? " saved" : ""}`}
            onClick={() => void toggleWatchlistFromExplore(snapshot.ticker)}
            disabled={savingTicker !== null || personalization?.watchlistLoading || Boolean(personalization?.watchlistLoadError)}
            aria-label={savingTicker === snapshot.ticker ? watchlist.has(snapshot.ticker) ? `Removing ${snapshot.ticker} from Watchlist` : `Saving ${snapshot.ticker} to Watchlist` : watchlist.has(snapshot.ticker) ? `Remove ${snapshot.ticker} from Watchlist` : `Add ${snapshot.ticker} to Watchlist`}
            aria-pressed={watchlist.has(snapshot.ticker)}
            aria-busy={savingTicker === snapshot.ticker}
            title={watchlist.has(snapshot.ticker) ? "Remove from Watchlist" : "Add to Watchlist"}>
            {watchlist.has(snapshot.ticker) || savingTicker === snapshot.ticker ? <BookmarkCheck size={21} /> : <BookmarkPlus size={21} />}
          </button>
        )}
        {editMode && !analysisMode && (
          <button
            type="button"
            className="mobile-remove-stock"
            onClick={() => onRemoveStock?.(snapshot.ticker)}
            disabled={removingTicker === snapshot.ticker}
            aria-label={`Remove ${snapshot.ticker}`}
            title={`Remove ${snapshot.ticker}`}
          >
            <X size={17} />
          </button>
        )}
      </article>
    );
  };
  const openWatchlistPicker = (groupId: string | null = null) => {
    setWatchlistTargetGroup(groupId);
    setWatchlistOpen(true);
  };
  const pagination = totalPages > 1 && (
    <nav className="mobile-pagination" aria-label="Stocks pagination">
      <button type="button" onClick={() => goToPage(currentPage - 1)} disabled={currentPage === 1} aria-label="Previous page" title="Previous page"><ChevronLeft size={19} /></button>
      <strong>{currentPage} / {totalPages}</strong>
      <button type="button" onClick={() => goToPage(currentPage + 1)} disabled={currentPage === totalPages} aria-label="Next page" title="Next page"><ChevronRight size={19} /></button>
    </nav>
  );

  if (detailOpen && selectedSnapshot) {
    return (
      <div className="mobile-stock-app">
        <StockDetail snapshot={selectedSnapshot} onBack={closeDetail} />
      </div>
    );
  }

  return (
    <div className="mobile-stock-app">
      <main className={`mobile-stock-main${analysisMode ? " analysis-selecting" : ""}`}>
        <header className="mobile-stock-header">
          <div>
            <h1>{signedIn ? "My space" : "Stocks"}</h1>
            {!signedIn && <p>{dateLabel}</p>}
          </div>
          <div className="mobile-header-actions">
            {headerActions?.(openDetail)}
          </div>
        </header>

        {signedIn && (
          <div className="my-space-tabs" role="tablist" aria-label="My space">
            {SPACE_TABS.map((tab, index) => (
              <button type="button" key={tab} role="tab" id={`space-${tab}-tab`} aria-controls={`space-${tab}`}
                aria-selected={spaceTab === tab} tabIndex={spaceTab === tab ? 0 : -1}
                onClick={() => selectSpaceTab(tab)}
                onKeyDown={(event) => {
                  if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                    event.preventDefault();
                    const next = event.key === "Home" ? "explore" : event.key === "End" ? "portfolio"
                      : SPACE_TABS[(index + (event.key === "ArrowRight" ? 1 : -1) + SPACE_TABS.length) % SPACE_TABS.length];
                    selectSpaceTab(next);
                    document.getElementById(`space-${next}-tab`)?.focus();
                  }
                }}>
                {tab === "explore" ? "Explore" : tab === "watchlist" ? "Watchlist" : "Portfolio"}
              </button>
            ))}
          </div>
        )}
        {signedIn && spaceTab === "portfolio" && personalization?.userId ? (
          <MoneyPanel key={personalization.userId} userId={personalization.userId} />
        ) : (
        <div id={isWatchlistView ? "space-watchlist" : "space-explore"} role={signedIn ? "tabpanel" : undefined} aria-labelledby={signedIn ? `space-${spaceTab}-tab` : undefined}>
        <label className="mobile-stock-search">
          <Search size={20} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search companies"
            aria-label="Search stocks"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={17} /></button>
          )}
        </label>

        <FilterSelector key={personalization?.userId ?? "guest"}
          userId={personalization?.userId ?? null}
          scopeLabel={isWatchlistView ? "Watchlist" : "Stocks"}
          filters={filterShortcuts}
          activeKey={activeShortcutKey}
          activeName={activeFilterName}
          onClear={clearFilter}
          onSelect={(key) => {
            const preset = defaultShortcuts.find((filter) => filter.key === key)?.preset;
            if (preset) applyBuiltInPreset(preset);
            else {
              const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
              if (filter) selectSavedFilter(filter);
            }
          }}
          onCreate={() => openFilterBuilder()}
          onEditCurrent={() => {
            setFilterDraft({ expression: filterExpression, sortKey, sortDirection, savedFilterId: null });
            setSheetOpen(true);
          }}
          onEdit={(key) => {
            const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
            if (filter) openFilterBuilder(filter);
          }}
          onDelete={async (key) => {
            const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
            if (!filter || !personalization) return;
            await personalization.onDeleteFilter(filter.id);
            if (activeSavedFilterId === filter.id) clearFilter();
          }}
        />

        <div className="mobile-list-summary" ref={listTopRef}>
          <span>{listSummaryLabel}</span>
          <div className="mobile-list-actions">
            {analysisMode ? (
              <button type="button" onClick={cancelAnalysis}>Cancel</button>
            ) : (
              <button type="button" className="stock-analysis-trigger" onClick={startAnalysis} disabled={visibleSnapshots.length === 0}>
                <Sparkles size={17} aria-hidden="true" />Analyze<ChevronRight size={15} aria-hidden="true" />
              </button>
            )}
            {!analysisMode && isWatchlistView && (
              <button type="button" disabled={personalization?.watchlistLoading} onClick={() => openWatchlistPicker()}>
                <Plus size={15} />Add
              </button>
            )}
          </div>
        </div>
        {analysisMode && (
          <p className="stock-analysis-selection-hint">Select companies to compare, then generate an AI brief.</p>
        )}
        {watchlistSaveError && <p className="mobile-personal-error" role="alert">{watchlistSaveError}</p>}
        {!isWatchlistView && signedIn && personalization?.watchlistLoadError && (
          <p className="mobile-personal-error" role="alert">Could not load your watchlist. <button type="button" onClick={() => void personalization.onReloadWatchlist()}>Try again</button></p>
        )}

        {isWatchlistView && personalization?.watchlistLoadError ? (
          <div className="mobile-list-state" role="alert">
            <strong>Could not load your watchlist</strong>
            <p>{personalization.watchlistLoadError}</p>
            <button type="button" className="mobile-empty-watchlist-button" onClick={() => void personalization.onReloadWatchlist()}>Try again</button>
          </div>
        ) : loading || (isWatchlistView && personalization?.watchlistLoading) ? (
          <div className="mobile-list-state">Loading stock insights...</div>
        ) : isWatchlistView && personalization ? (
          <>
            <WatchlistGroups key={personalization.userId ?? "watchlist"}
              groups={watchlistGroups} items={watchlistItems}
              matchingSnapshots={visibleSnapshots} pagedSnapshots={pagedSnapshots}
              renderRow={renderStockRow} onAdd={openWatchlistPicker}
              onRevealGroup={(groupId) => {
                const index = expandedSnapshots.findIndex((snapshot) => (watchlistOrder.get(snapshot.ticker)?.group_id ?? null) === groupId);
                if (index >= 0) goToPage(Math.floor(index / PAGE_SIZE) + 1);
              }}
              onManualOrder={() => { setSortKey("watchlist_order"); setSortDirection("asc"); }}
              onRemove={personalization.onRemoveFromWatchlist} actions={personalization} />
            {pagination}
          </>
        ) : visibleSnapshots.length === 0 ? (
          <div className="mobile-list-state">
            <strong>{snapshots.length === 0 ? "No stock metrics loaded" : "No stocks match"}</strong>
            <p>{snapshots.length === 0 ? "The data bundle is empty." : "Try removing a filter or changing the search."}</p>
          </div>
        ) : (
          <>
            <section className="mobile-stock-list" aria-label="Stocks">
              {pagedSnapshots.map(renderStockRow)}
            </section>
            {pagination}
          </>
        )}
        {analysisMode && (
          <div className="stock-analysis-selection-bar">
            <div><strong role="status">{analysisSelection.length} stock{analysisSelection.length === 1 ? "" : "s"} selected</strong></div>
            <button ref={analysisPrepareRef} type="button" className="stock-analysis-prepare" onClick={prepareSelectedStocks} disabled={analysisSelection.length === 0}><Sparkles size={17} aria-hidden="true" />Generate AI brief</button>
          </div>
        )}
        </div>
        )}
      </main>

      {signedIn && addedTicker && (
        <div className="mobile-watchlist-confirmation">
          <span role="status" aria-live="polite">Added to Watchlist</span><span aria-hidden="true">·</span>
          <button type="button" onClick={viewAddedStock}>View</button>
        </div>
      )}

      {analysisBrief && <StockAnalysisDialog brief={analysisBrief} copyStatus={analysisCopyStatus}
        onCopy={() => void copyAnalysisPrompt(analysisBrief.prompt)} onClose={closeAnalysisBrief} />}

      {sheetOpen && <FilterSheet
        open={sheetOpen}
        expression={filterDraft.expression}
        sortKey={filterDraft.sortKey}
        sortDirection={filterDraft.sortDirection}
        actions={actions}
        personalization={personalization}
        watchlistView={isWatchlistView}
        activeSavedFilterId={filterDraft.savedFilterId}
        onClose={() => setSheetOpen(false)}
        onApply={applyFilterDraft}
        onExpressionChange={(expression) => setFilterDraft((draft) => ({ ...draft, expression }))}
        onApplyPullbackPreset={() => applyDraftPreset("pullback")}
        onApplySupportPreset={() => applyDraftPreset("support")}
        onApplyEarningsPreset={() => applyDraftPreset("earnings")}
        onSortKeyChange={(sortKey) => setFilterDraft((draft) => ({ ...draft, sortKey }))}
        onSortDirectionChange={(sortDirection) => setFilterDraft((draft) => ({ ...draft, sortDirection }))}
        onSavedFilter={(filter) => { selectSavedFilter(filter); setSheetOpen(false); }}
        onClear={() => setFilterDraft((draft) => ({ ...draft, expression: createEmptyFilterExpression() }))}
      />}
      {personalization?.signedIn && watchlistOpen && (
        <WatchlistSheet key={`${personalization.userId}:${watchlistTargetGroup ?? "ungrouped"}`}
          snapshots={snapshots} items={watchlistItems} groups={watchlistGroups}
          groupId={watchlistTargetGroup}
          onClose={() => setWatchlistOpen(false)}
          onAdd={personalization.onAddToWatchlist}
        />
      )}
    </div>
  );
}
