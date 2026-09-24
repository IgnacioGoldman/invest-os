import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Bookmark,
  Check,
  ChevronLeft,
  ChevronRight,
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
  type OpenDataMetric,
  type OpenDataPricePoint,
  type OpenDataStockSnapshot,
} from "../api";
import {
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
  actions?: ReactNode;
  headerActions?: (openTicker: (ticker: string) => void) => ReactNode;
  editMode?: boolean;
  removingTicker?: string | null;
  onRemoveStock?: (ticker: string) => void;
  personalization?: {
    signedIn: boolean;
    savedFilters: SavedFilter[];
    watchlistTickers: string[];
    filterBadgeCounts: Record<string, number>;
    onRequestSignIn: () => Promise<void>;
    onSaveFilter: (input: Omit<SaveFilterInput, "userId">) => Promise<SavedFilter>;
    onDeleteFilter: (filterId: string) => Promise<void>;
    onAddToWatchlist: (ticker: string) => Promise<void>;
    onRemoveFromWatchlist: (ticker: string) => Promise<void>;
  };
};

type Tone = "positive" | "warning" | "negative" | "neutral" | "info";
type GrowthDetailKey = "revenue" | "momentum" | "eps";
export type FilterKey =
  | "revenue"
  | "momentum"
  | "eps"
  | "support_1m"
  | "support_3m"
  | "support_6m"
  | "support_1y"
  | "support_2y"
  | "support_5y";
export type SortKey = "symbol" | "support_best" | FilterKey;
export type SortDirection = "asc" | "desc";
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
type MetricKind = "percent" | "ratio" | "compact" | "price";

type Signal = {
  label: string;
  tone: Tone;
};

const GROWTH_DETAIL_COPY: Record<GrowthDetailKey, { title: string; question: string; description: string }> = {
  revenue: {
    title: "Latest revenue growth YoY",
    question: "Is the business growing right now?",
    description:
      "Compares the latest quarter's revenue with the same quarter last year. It tells you whether customers are spending more with the company and whether the overall business is expanding. For example, +15% means the company generated 15% more revenue than one year ago.",
  },
  momentum: {
    title: "Revenue growth momentum",
    question: "Is the company's growth getting stronger or weaker?",
    description:
      "Compares the latest revenue growth rate with the previous quarter's growth rate. A positive percentage-point change means growth is accelerating; a negative change means it is decelerating.",
  },
  eps: {
    title: "Latest EPS growth YoY",
    question: "Is the company converting growth into earnings?",
    description:
      "Compares latest-quarter diluted earnings per share with the same quarter last year. It helps separate revenue growth from profitable growth.",
  },
};

type FilterDefinition = {
  key: FilterKey;
  label: string;
  shortLabel: string;
  section: "Growth" | "Support";
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
const LONG_SUPPORT_FILTER_KEYS = ["support_3m", "support_6m", "support_1y", "support_2y", "support_5y"] as const;
type SupportFilterKey = typeof SUPPORT_FILTER_KEYS[number];
type BuiltInPreset = "pullback" | "support";

const FILTER_DEFINITIONS: FilterDefinition[] = [
  {
    key: "revenue",
    label: "Latest revenue growth YoY",
    shortLabel: "Revenue YoY",
    section: "Growth",
    description: "Year-over-year revenue growth in the latest reported quarter.",
    options: [
      { label: "Strong", tone: "positive" },
      { label: "Solid", tone: "positive" },
      { label: "Mixed", tone: "warning" },
      { label: "Weak", tone: "negative" },
      { label: "Unclear", tone: "neutral" },
    ],
  },
  {
    key: "momentum",
    label: "Revenue growth momentum",
    shortLabel: "Momentum",
    section: "Growth",
    description: "Change in revenue growth rate versus the previous quarter.",
    options: [
      { label: "Accelerating", tone: "positive" },
      { label: "Stable", tone: "warning" },
      { label: "Decelerating", tone: "negative" },
      { label: "Unclear", tone: "neutral" },
    ],
  },
  {
    key: "eps",
    label: "Latest EPS growth YoY",
    shortLabel: "EPS YoY",
    section: "Growth",
    description: "Year-over-year earnings-per-share growth in the latest quarter.",
    options: [
      { label: "Strong", tone: "positive" },
      { label: "Solid", tone: "positive" },
      { label: "Mixed", tone: "warning" },
      { label: "Weak", tone: "negative" },
      { label: "Unclear", tone: "neutral" },
    ],
  },
  ...(["1m", "3m", "6m", "1y", "2y", "5y"] as const).map((range) => ({
    key: `support_${range}` as FilterKey,
    label: `Near ${range.toUpperCase()} support`,
    shortLabel: `${range.toUpperCase()} support`,
    section: "Support" as const,
    description: `Distance from the ${range.toUpperCase()} support level. Closer to 0% means nearer support.`,
    options: [
      { label: "At support", tone: "positive" as const },
      { label: "Near support", tone: "warning" as const },
      { label: "Above support", tone: "neutral" as const },
      { label: "Far", tone: "info" as const },
    ],
  })),
];

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "symbol", label: "Symbol" },
  { key: "support_best", label: "Closest support" },
  ...FILTER_DEFINITIONS.map(({ key, shortLabel }) => ({ key, label: shortLabel })),
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
  return formatNumber(value);
}

function growthSignal(value?: number | null): Signal {
  if (value == null) return { label: "Unclear", tone: "neutral" };
  if (value >= 20) return { label: "Strong", tone: "positive" };
  if (value >= 8) return { label: "Solid", tone: "positive" };
  if (value >= 0) return { label: "Mixed", tone: "warning" };
  return { label: "Weak", tone: "negative" };
}

function supportSignal(value?: number | null): Signal {
  if (value == null || value > 25) return { label: "Far", tone: "info" };
  if (value <= 2.5) return { label: "At support", tone: "positive" };
  if (value <= 6) return { label: "Near support", tone: "warning" };
  return { label: "Above support", tone: "neutral" };
}

function historicalRows(snapshot: OpenDataStockSnapshot, series: string) {
  return [...(snapshot.historical_series[series] ?? [])].sort((left, right) =>
    left.period.localeCompare(right.period, undefined, { numeric: true, sensitivity: "base" }),
  );
}

function metricValue(row: OpenDataStockSnapshot["historical_series"][string][number], key: string) {
  return finiteNumber(row.metrics[key]?.value);
}

function revenueGrowthPoints(snapshot: OpenDataStockSnapshot) {
  return historicalRows(snapshot, "quarterly_revenue")
    .map((row) => ({ period: row.period, value: metricValue(row, "revenue_growth_yoy") }))
    .filter((point): point is { period: string; value: number } => point.value != null);
}

function sourceFacts(source?: string) {
  return (source ?? "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
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

function revenueMomentum(snapshot: OpenDataStockSnapshot) {
  const points = revenueGrowthPoints(snapshot);
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  if (!latest || !previous) return { label: "Unclear", tone: "neutral" as Tone, change: null, period: null };
  const change = latest.value - previous.value;
  if (change >= 3) return { label: "Accelerating", tone: "positive" as Tone, change, period: previous.period };
  if (change <= -3) return { label: "Decelerating", tone: "negative" as Tone, change, period: previous.period };
  return { label: "Stable", tone: "warning" as Tone, change, period: previous.period };
}

function inferredSupportLevel(currentPrice?: number | null, supportDistance?: number | null) {
  if (currentPrice == null || supportDistance == null) return null;
  const divisor = 1 + supportDistance / 100;
  return divisor > 0 ? currentPrice / divisor : null;
}

function signalFor(snapshot: OpenDataStockSnapshot, key: FilterKey): Signal {
  if (key === "revenue") return growthSignal(snapshot.business_health.revenue_growth_yoy?.value);
  if (key === "eps") return growthSignal(snapshot.business_health.eps_growth_yoy?.value);
  if (key === "momentum") return revenueMomentum(snapshot);
  return supportSignal(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value);
}

function closestSupport(snapshot: OpenDataStockSnapshot, keys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS) {
  return keys
    .map((key) => ({
      key,
      label: FILTER_DEFINITIONS.find((definition) => definition.key === key)?.shortLabel ?? key,
      value: finiteNumber(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value),
    }))
    .filter((item): item is { key: SupportFilterKey; label: string; value: number } => item.value != null)
    .sort((left, right) => left.value - right.value)[0] ?? null;
}

function sortValue(
  snapshot: OpenDataStockSnapshot,
  key: SortKey,
  supportKeys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS,
): number | string | null {
  if (key === "symbol") return snapshot.ticker;
  if (key === "support_best") return closestSupport(snapshot, supportKeys)?.value ?? null;
  if (key === "revenue") return finiteNumber(snapshot.business_health.revenue_growth_yoy?.value);
  if (key === "eps") return finiteNumber(snapshot.business_health.eps_growth_yoy?.value);
  if (key === "momentum") return revenueMomentum(snapshot).change;
  return finiteNumber(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value);
}

function rowMetric(
  snapshot: OpenDataStockSnapshot,
  key: SortKey,
  supportKeys: readonly SupportFilterKey[] = SUPPORT_FILTER_KEYS,
) {
  if (key === "symbol") {
    const dailyChange = snapshot.price_opportunity.change_1d?.value;
    const dailySignal: Signal = dailyChange == null
      ? { label: "Unavailable", tone: "neutral" }
      : dailyChange > 0
        ? { label: "Up today", tone: "positive" }
        : dailyChange < 0
          ? { label: "Down today", tone: "negative" }
          : { label: "Flat today", tone: "neutral" };
    return {
      value: formatPrice(snapshot.price_opportunity.current_price?.value),
      signal: dailySignal,
      secondary: formatPercent(dailyChange, true),
    };
  }
  if (key === "revenue" || key === "eps") {
    const metric = key === "revenue" ? snapshot.business_health.revenue_growth_yoy : snapshot.business_health.eps_growth_yoy;
    return { value: formatPercent(metric?.value, true), signal: growthSignal(metric?.value), secondary: null };
  }
  if (key === "momentum") {
    const momentum = revenueMomentum(snapshot);
    return {
      value: momentum.change == null ? "-" : `${momentum.change > 0 ? "+" : ""}${formatNumber(momentum.change)} pp`,
      signal: momentum,
      secondary: null,
    };
  }
  if (key === "support_best") {
    const support = closestSupport(snapshot, supportKeys);
    return {
      value: formatPercent(support?.value, true),
      signal: supportSignal(support?.value),
      secondary: support?.label ?? null,
    };
  }
  const value = snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value;
  return { value: formatPercent(value, true), signal: supportSignal(value), secondary: null };
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

function createStrongYoyExpression(preset: BuiltInPreset): FilterExpression {
  const supportFields = preset === "pullback" ? (["support_1m"] as const) : LONG_SUPPORT_FILTER_KEYS;
  return {
    operator: "and",
    groups: [
      {
        id: nextFilterId("group"),
        operator: "or",
        conditions: createSupportConditions(supportFields),
      },
      {
        id: nextFilterId("group"),
        operator: "or",
        conditions: [createCondition("revenue", "Strong"), createCondition("revenue", "Solid")],
      },
    ],
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
  if (expression.operator !== "and" || expression.groups.length !== 2) return null;
  const signatures = expression.groups.map((group) => ({
    operator: group.operator,
    conditions: group.conditions.map((condition) => `${condition.field}:${condition.value}`).sort(),
  }));
  const growthSignature = ["revenue:Solid", "revenue:Strong"];
  const hasGrowthGroup = signatures.some(
    (group) => group.operator === "or" && group.conditions.join("|") === growthSignature.join("|"),
  );
  if (!hasGrowthGroup) return null;
  const supportSignature = (fields: readonly Extract<FilterKey, `support_${string}`>[]) => fields
    .flatMap((key) => [`${key}:At support`, `${key}:Near support`])
    .sort()
    .join("|");
  if (signatures.some((group) => group.operator === "or" && group.conditions.join("|") === supportSignature(["support_1m"]))) {
    return "pullback";
  }
  if (signatures.some((group) => group.operator === "or" && group.conditions.join("|") === supportSignature(LONG_SUPPORT_FILTER_KEYS))) {
    return "support";
  }
  return null;
}

function builtInPresetName(preset: BuiltInPreset | null) {
  if (preset === "pullback") return "Strong YoY and on pullback";
  if (preset === "support") return "Strong YoY and on support";
  return null;
}

function StockStatus({ signal }: { signal: Signal }) {
  return <span className={`mobile-status ${signal.tone}`}>{signal.label}</span>;
}

function FilterNewBadge({ count }: { count?: number }) {
  if (!count) return null;
  return <span className="mobile-filter-new-badge">+{count}</span>;
}

function FilterSheet({
  open,
  expression,
  sortKey,
  sortDirection,
  actions,
  personalization,
  activeSavedFilterId,
  onClose,
  onExpressionChange,
  onApplyPullbackPreset,
  onApplySupportPreset,
  onSortKeyChange,
  onSortDirectionChange,
  onClear,
  onSelectSavedFilter,
  onSavedFilter,
}: {
  open: boolean;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
  actions?: ReactNode;
  personalization?: Props["personalization"];
  activeSavedFilterId: string | null;
  onClose: () => void;
  onExpressionChange: (expression: FilterExpression) => void;
  onApplyPullbackPreset: () => void;
  onApplySupportPreset: () => void;
  onSortKeyChange: (key: SortKey) => void;
  onSortDirectionChange: (direction: SortDirection) => void;
  onClear: () => void;
  onSelectSavedFilter: (filter: SavedFilter) => void;
  onSavedFilter: (filter: SavedFilter | null) => void;
}) {
  const [saveFormOpen, setSaveFormOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  const count = activeFilterCount(expression);
  const builtInPreset = builtInPresetFor(expression);
  const builtInName = builtInPresetName(builtInPreset);
  const activeSavedFilter = personalization?.savedFilters.find((item) => item.id === activeSavedFilterId) ?? null;

  const openSaveForm = () => {
    setSaveName(activeSavedFilter?.name ?? builtInName ?? "My stock filter");
    setSaveError(null);
    setSaveFormOpen(true);
  };

  const submitSavedFilter = async () => {
    if (!personalization || !saveName.trim() || count === 0) return;
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
      setSaveFormOpen(false);
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not save this filter.");
    } finally {
      setSaveBusy(false);
    }
  };

  const requestSignIn = async () => {
    if (!personalization) return;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await personalization.onRequestSignIn();
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not start Google sign-in.");
      setSaveBusy(false);
    }
  };

  const removeSavedFilter = async () => {
    if (!personalization || !activeSavedFilter) return;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await personalization.onDeleteFilter(activeSavedFilter.id);
      onSavedFilter(null);
      setSaveFormOpen(false);
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not delete this filter.");
    } finally {
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
    <div className="mobile-sheet-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <section className="mobile-filter-sheet" role="dialog" aria-modal="true" aria-label="Filter and sort stocks">
        <div className="mobile-sheet-handle" aria-hidden="true" />
        <header className="mobile-sheet-header">
          <div>
            <h2>Filter &amp; sort</h2>
            <p>Combine metrics to narrow the list.</p>
          </div>
          <button type="button" className="mobile-icon-button" onClick={onClose} aria-label="Close filter and sort">
            <X size={20} />
          </button>
        </header>

        <div className="mobile-sheet-scroll">
          {personalization && (
            <section className="mobile-filter-section mobile-saved-filter-section">
              <div className="mobile-filter-title-row">
                <h3>Saved filters</h3>
                {personalization.signedIn && count > 0 && (
                  <button type="button" className="mobile-save-filter-trigger" onClick={openSaveForm}>
                    <Save size={15} />{activeSavedFilter ? "Save changes" : "Save current"}
                  </button>
                )}
              </div>

              {!personalization.signedIn ? (
                <>
                  <button type="button" className="mobile-signin-filter" disabled={saveBusy} onClick={() => void requestSignIn()}>
                    <LogIn size={18} />
                    <span><strong>Sign in to save filters</strong><small>Sync views and see daily new-match badges.</small></span>
                    <ChevronRight size={17} />
                  </button>
                  {saveError && <p className="mobile-personal-error">{saveError}</p>}
                </>
              ) : (
                <>
                  {personalization.savedFilters.length > 0 ? (
                    <div className="mobile-saved-filter-list">
                      {personalization.savedFilters.map((filter) => (
                        <button
                          type="button"
                          key={filter.id}
                          className={activeSavedFilterId === filter.id ? "active" : ""}
                          onClick={() => onSelectSavedFilter(filter)}
                        >
                          <Bookmark size={15} fill={activeSavedFilterId === filter.id ? "currentColor" : "none"} />
                          <span>{filter.name}</span>
                          <FilterNewBadge count={personalization.filterBadgeCounts[savedFilterKey(filter.id)]} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="mobile-saved-filter-hint">Build conditions below, then save the view for quick access.</p>
                  )}

                  {saveFormOpen && (
                    <div className="mobile-save-filter-form">
                      <label>
                        <span>Filter name</span>
                        <input
                          type="text"
                          value={saveName}
                          onChange={(event) => setSaveName(event.target.value)}
                          maxLength={80}
                          autoFocus
                        />
                      </label>
                      {saveError && <p className="mobile-personal-error">{saveError}</p>}
                      <div className="mobile-save-filter-actions">
                        {activeSavedFilter && (
                          <button type="button" className="danger" disabled={saveBusy} onClick={() => void removeSavedFilter()}>
                            <Trash2 size={16} />Delete
                          </button>
                        )}
                        <button type="button" onClick={() => setSaveFormOpen(false)} disabled={saveBusy}>Cancel</button>
                        <button type="button" className="primary" onClick={() => void submitSavedFilter()} disabled={saveBusy || !saveName.trim()}>
                          <Save size={16} />{activeSavedFilter ? "Update" : "Save"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
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
              {SORT_OPTIONS.map((option) => (
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
                                      value={condition.value}
                                      onChange={(event) => updateCondition(group.id, condition.id, condition.field, event.target.value)}
                                    >
                                      {definition.options.map((option) => <option key={option.label} value={option.label}>{option.label}</option>)}
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
                <SlidersHorizontal size={22} />
                <strong>Build a filter with clear logic</strong>
                <p>Use groups for parentheses, then choose whether groups and conditions use AND or OR.</p>
                <div>
                  <button type="button" onClick={addGroup}><Plus size={16} />New filter</button>
                  <button type="button" onClick={onApplyPullbackPreset}>Use Pullback preset</button>
                  <button type="button" onClick={onApplySupportPreset}>Use Support preset</button>
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
          <button type="button" className="mobile-done-button" onClick={onClose}>
            Show stocks{count > 0 ? ` (${count} condition${count === 1 ? "" : "s"})` : ""}
          </button>
        </footer>
      </section>
    </div>
  );
}

function WatchlistSheet({
  open,
  snapshots,
  watchlistTickers,
  onClose,
  onAdd,
  onRemove,
}: {
  open: boolean;
  snapshots: OpenDataStockSnapshot[];
  watchlistTickers: string[];
  onClose: () => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [busyTicker, setBusyTicker] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose, open]);

  if (!open) return null;
  const watched = new Set(watchlistTickers);
  const needle = query.trim().toLowerCase();
  const rows = snapshots.filter((snapshot) => !needle || [snapshot.ticker, snapshot.name, snapshot.sector, snapshot.industry]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(needle)));

  const update = async (ticker: string, action: (symbol: string) => Promise<void>) => {
    setBusyTicker(ticker);
    setError(null);
    try {
      await action(ticker);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : `Could not update ${ticker}.`);
    } finally {
      setBusyTicker(null);
    }
  };

  return (
    <div className="mobile-sheet-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <section className="mobile-watchlist-sheet" role="dialog" aria-modal="true" aria-label="Manage watchlist">
        <div className="mobile-sheet-handle" aria-hidden="true" />
        <header className="mobile-sheet-header">
          <div><h2>Watchlist</h2><p>{watchlistTickers.length} symbol{watchlistTickers.length === 1 ? "" : "s"} saved</p></div>
          <button type="button" className="mobile-icon-button" onClick={onClose} aria-label="Close watchlist">
            <X size={20} />
          </button>
        </header>
        <label className="mobile-watchlist-search">
          <Search size={18} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a symbol or company"
            aria-label="Find stocks for watchlist"
            autoFocus
          />
          {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear watchlist search"><X size={16} /></button>}
        </label>
        {error && <p className="mobile-watchlist-error">{error}</p>}
        <div className="mobile-watchlist-picker">
          {rows.map((snapshot) => {
            const isWatched = watched.has(snapshot.ticker);
            return (
              <div className="mobile-watchlist-option" key={snapshot.ticker}>
                <span><strong>{snapshot.ticker}</strong><small>{snapshot.name ?? snapshot.industry ?? ""}</small></span>
                <button
                  type="button"
                  className={isWatched ? "remove" : "add"}
                  disabled={busyTicker === snapshot.ticker}
                  onClick={() => void update(snapshot.ticker, isWatched ? onRemove : onAdd)}
                  aria-label={`${isWatched ? "Remove" : "Add"} ${snapshot.ticker} ${isWatched ? "from" : "to"} watchlist`}
                  title={`${isWatched ? "Remove from" : "Add to"} watchlist`}
                >
                  {isWatched ? <><Check size={16} />Added</> : <><Plus size={16} />Add</>}
                </button>
              </div>
            );
          })}
          {rows.length === 0 && <p className="mobile-watchlist-no-results">No stocks match your search.</p>}
        </div>
        <footer className="mobile-watchlist-footer">
          <button type="button" onClick={onClose}>Done</button>
        </footer>
      </section>
    </div>
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
  const supportDistance = snapshot.price_opportunity[supportKey]?.value;
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
  const yFor = (value: number) => padding.top + ((yMax - value) / Math.max(yMax - yMin, 1)) * innerHeight;
  const path = ranged.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(2)},${yFor(point.close).toFixed(2)}`).join(" ");
  const first = ranged[0];
  const last = ranged[ranged.length - 1];
  const change = first && last ? ((last.close - first.close) / first.close) * 100 : null;
  const selected = ranged[hoverIndex ?? Math.max(ranged.length - 1, 0)];
  const guideParts = [0.25, 0.5, 0.75];
  const dateGuideIndices = Array.from(new Set([0, Math.round((ranged.length - 1) / 2), ranged.length - 1]));
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
              <line x1={padding.left} x2={width - padding.right} y1={yFor(supportLevel)} y2={yFor(supportLevel)} />
              <text x={padding.left + 6} y={yFor(supportLevel) - 7}>{range === "ALL" ? "5Y" : supportKey.split("_")[1].toUpperCase()} support {formatPrice(supportLevel)}</text>
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
  selectedPeriod,
}: {
  title: string;
  points: Array<{ period: string; value: number }>;
  selectedPeriod?: string;
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
            point.period === selectedPeriod ? "selected" : "",
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
}: {
  active: boolean;
  label: string;
  signal: Signal;
  value: string;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`mobile-growth-signal ${active ? "active" : ""}`} onClick={onClick}>
      <span>{label}</span>
      <StockStatus signal={signal} />
      <strong>{value}</strong>
    </button>
  );
}

function MobileGrowthDetailPanel({ snapshot, detailKey }: { snapshot: OpenDataStockSnapshot; detailKey: GrowthDetailKey }) {
  const copy = GROWTH_DETAIL_COPY[detailKey];
  const revenueDetail = revenueGrowthDetail(snapshot);
  const momentum = revenueMomentum(snapshot);
  const epsMetric = snapshot.business_health.eps_growth_yoy;
  const metric = detailKey === "eps" ? epsMetric : detailKey === "revenue" ? revenueDetail?.growth : undefined;
  const facts = sourceFacts(metric?.source);
  const currentValue = detailKey === "momentum"
    ? momentum.change == null ? "-" : `${momentum.change > 0 ? "+" : ""}${formatNumber(momentum.change)} pp`
    : formatMetric(metric, "percent");
  const detailText = detailKey === "momentum"
    ? momentum.change == null ? "Needs at least two comparable quarterly revenue YoY points." : `${momentum.label} versus ${momentum.period ?? "the prior quarter"}.`
    : detailKey === "revenue" && revenueDetail?.latestRevenue != null && revenueDetail?.priorRevenue != null
      ? `${revenueDetail.latest.period}: ${formatCompact(revenueDetail.latestRevenue)} vs ${formatCompact(revenueDetail.priorRevenue)} one year earlier.`
      : metric?.notes ?? "Comparable quarterly data is unavailable.";

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
        <small>{detailText}</small>
      </div>
      {facts.length > 0 && (
        <div className="mobile-source-list">
          <span>Source facts</span>
          {facts.map((fact) => (
            <code key={fact}>{fact}</code>
          ))}
        </div>
      )}
      <GrowthChart
        title={detailKey === "eps" ? "EPS growth YoY" : "Revenue growth YoY"}
        points={detailKey === "eps" ? quarterlyGrowthPoints(snapshot, "eps_diluted") : revenueGrowthPoints(snapshot)}
        selectedPeriod={detailKey === "revenue" ? revenueDetail?.latest.period : undefined}
      />
    </section>
  );
}

function StockDetail({ snapshot, onBack }: { snapshot: OpenDataStockSnapshot; onBack: () => void }) {
  const [activeGrowthDetail, setActiveGrowthDetail] = useState<GrowthDetailKey>("revenue");
  const currentPrice = snapshot.price_opportunity.current_price?.value;
  const dailyChange = snapshot.price_opportunity.change_1d?.value;
  const revenueSignal = growthSignal(snapshot.business_health.revenue_growth_yoy?.value);
  const epsSignal = growthSignal(snapshot.business_health.eps_growth_yoy?.value);
  const momentum = revenueMomentum(snapshot);

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
            <span className={dailyChange != null && dailyChange < 0 ? "negative" : "positive"}>{formatPercent(dailyChange, true)} today</span>
          </div>
        </section>

        <section className="mobile-signal-strip" aria-label="Current growth signals">
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "revenue"}
            label="Latest revenue growth YoY"
            signal={revenueSignal}
            value={formatPercent(snapshot.business_health.revenue_growth_yoy?.value, true)}
            onClick={() => setActiveGrowthDetail("revenue")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "momentum"}
            label="Revenue growth momentum"
            signal={momentum}
            value={momentum.change == null ? "-" : `${momentum.change > 0 ? "+" : ""}${formatNumber(momentum.change)} pp`}
            onClick={() => setActiveGrowthDetail("momentum")}
          />
          <MobileGrowthSignalButton
            active={activeGrowthDetail === "eps"}
            label="Latest EPS growth YoY"
            signal={epsSignal}
            value={formatPercent(snapshot.business_health.eps_growth_yoy?.value, true)}
            onClick={() => setActiveGrowthDetail("eps")}
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
  actions,
  headerActions,
  editMode = false,
  removingTicker,
  onRemoveStock,
  personalization,
}: Props) {
  const [query, setQuery] = useState("");
  const [filterExpression, setFilterExpression] = useState<FilterExpression>(() => createStrongYoyExpression("support"));
  const [sortKey, setSortKey] = useState<SortKey>("support_best");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [watchlistOpen, setWatchlistOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeSavedFilterId, setActiveSavedFilterId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const listTopRef = useRef<HTMLDivElement | null>(null);
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.ticker === selectedTicker) ?? null;
  const builtInPreset = builtInPresetFor(filterExpression);
  const builtInName = builtInPresetName(builtInPreset);
  const relevantSupportKeys = builtInPreset === "support" ? LONG_SUPPORT_FILTER_KEYS : SUPPORT_FILTER_KEYS;
  const signedIn = personalization?.signedIn ?? false;
  const watchlistTickers = personalization?.watchlistTickers ?? [];
  const watchlist = useMemo(() => new Set(watchlistTickers), [watchlistTickers]);
  const baseSnapshots = useMemo(
    () => signedIn ? snapshots.filter((snapshot) => watchlist.has(snapshot.ticker)) : snapshots,
    [signedIn, snapshots, watchlist],
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
  }, [baseSnapshots, filterExpression, query, relevantSupportKeys, sortDirection, sortKey]);
  const totalPages = Math.max(1, Math.ceil(visibleSnapshots.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = visibleSnapshots.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(currentPage * PAGE_SIZE, visibleSnapshots.length);
  const pagedSnapshots = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return visibleSnapshots.slice(start, start + PAGE_SIZE);
  }, [currentPage, visibleSnapshots]);
  const listSummaryLabel = visibleSnapshots.length === 0
    ? signedIn ? `0 of ${baseSnapshots.length} watched` : `0 of ${snapshots.length} stocks`
    : signedIn
      ? `${pageStart}-${pageEnd} of ${visibleSnapshots.length} watched`
      : `${pageStart}-${pageEnd} of ${visibleSnapshots.length} stocks`;

  const filterCount = activeFilterCount(filterExpression);
  const sortLabel = SORT_OPTIONS.find((option) => option.key === sortKey)?.label ?? "Symbol";
  const sortSummary = sortKey === "support_best"
    ? builtInPreset === "support"
      ? sortDirection === "asc" ? "Closest long-term support" : "Farthest long-term support"
      : sortDirection === "asc" ? "Closest support" : "Farthest support"
    : `${sortDirection === "asc" ? "Lowest" : "Highest"} ${sortLabel}`;
  const latestMarketDate = snapshots.reduce((latest, snapshot) => {
    const asOf = snapshot.price_opportunity.current_price?.as_of?.slice(0, 10) ?? "";
    return asOf > latest ? asOf : latest;
  }, "");
  const dateLabel = latestMarketDate
    ? new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", timeZone: "UTC" })
      .format(new Date(`${latestMarketDate}T12:00:00Z`))
    : "";

  useEffect(() => {
    setPage(1);
  }, [filterExpression, query, signedIn, sortDirection, sortKey, watchlistTickers]);

  useEffect(() => {
    setPage((value) => Math.min(value, totalPages));
  }, [totalPages]);

  const goToPage = (nextPage: number) => {
    const boundedPage = Math.max(1, Math.min(totalPages, nextPage));
    if (boundedPage === currentPage) return;
    setPage(boundedPage);
    window.requestAnimationFrame(() => {
      listTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const toggleBuiltInPreset = (preset: BuiltInPreset) => {
    setFilterExpression(builtInPreset === preset
      ? { operator: "and", groups: [] }
      : createStrongYoyExpression(preset));
    setSortKey(preset === "pullback" ? "support_1m" : "support_best");
    setSortDirection("asc");
    setActiveSavedFilterId(null);
  };

  const selectSavedFilter = (filter: SavedFilter) => {
    setFilterExpression(filter.expression);
    setSortKey(filter.sort_key);
    setSortDirection(filter.sort_direction);
    setActiveSavedFilterId(filter.id);
  };

  const openDetail = (ticker: string) => {
    onSelectTicker(ticker);
    setDetailOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (detailOpen && selectedSnapshot) {
    return (
      <div className="mobile-stock-app">
        <StockDetail snapshot={selectedSnapshot} onBack={() => setDetailOpen(false)} />
      </div>
    );
  }

  return (
    <div className="mobile-stock-app">
      <main className="mobile-stock-main">
        <header className="mobile-stock-header">
          <div>
            <h1>{signedIn ? "Watchlist" : "Stocks"}</h1>
            <p>{signedIn ? `My stocks${dateLabel ? ` · ${dateLabel}` : ""}` : dateLabel}</p>
          </div>
          <div className="mobile-header-actions">
            {headerActions?.(openDetail)}
            <button
              type="button"
              className={`mobile-options-button ${filterCount > 0 ? "active" : ""}`}
              onClick={() => setSheetOpen(true)}
              aria-label="Open filter and sort options"
              title="Filter and sort"
            >
              <SlidersHorizontal size={22} />
              {filterCount > 0 && <span>{filterCount}</span>}
            </button>
          </div>
        </header>

        <label className="mobile-stock-search">
          <Search size={20} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Symbol, name or sector"
            aria-label="Search stocks"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={17} /></button>
          )}
        </label>

        <div className="mobile-quick-filters" aria-label="Quick filters">
          <button type="button" className={builtInPreset === "pullback" ? "active" : ""} onClick={() => toggleBuiltInPreset("pullback")}>
            {builtInPreset === "pullback" && <Check size={15} />}
            Strong YoY and on pullback
            <FilterNewBadge count={personalization?.filterBadgeCounts[PULLBACK_FILTER_KEY]} />
          </button>
          <button type="button" className={builtInPreset === "support" ? "active" : ""} onClick={() => toggleBuiltInPreset("support")}>
            {builtInPreset === "support" && <Check size={15} />}
            Strong YoY and on support
            <FilterNewBadge count={personalization?.filterBadgeCounts[SUPPORT_FILTER_KEY]} />
          </button>
          {personalization?.signedIn && personalization.savedFilters.map((filter) => (
            <button
              type="button"
              key={filter.id}
              className={activeSavedFilterId === filter.id ? "active" : ""}
              onClick={() => selectSavedFilter(filter)}
            >
              {activeSavedFilterId === filter.id && <Check size={15} />}
              {filter.name}
              <FilterNewBadge count={personalization.filterBadgeCounts[savedFilterKey(filter.id)]} />
            </button>
          ))}
        </div>

        {filterCount > 0 && (
          <div className="mobile-filter-expression-summary" aria-label="Active filter logic">
            <button type="button" onClick={() => setSheetOpen(true)}>
              <span>{personalization?.savedFilters.find((item) => item.id === activeSavedFilterId)?.name ?? builtInName ?? "Custom filter"}</span>
              <small>
                {filterExpression.groups.length} group{filterExpression.groups.length === 1 ? "" : "s"}
                {filterExpression.groups.length > 1 ? ` joined by ${filterExpression.operator.toUpperCase()}` : ""}
                {` · ${filterCount} condition${filterCount === 1 ? "" : "s"}`}
              </small>
            </button>
            <button
              type="button"
              onClick={() => {
                setFilterExpression({ operator: "and", groups: [] });
                setActiveSavedFilterId(null);
              }}
              aria-label="Clear filter"
              title="Clear filter"
            >
              <X size={16} />
            </button>
          </div>
        )}

        <div className="mobile-list-summary" ref={listTopRef}>
          <span>{listSummaryLabel}</span>
          <div className="mobile-list-actions">
            {signedIn && (
              <button type="button" onClick={() => setWatchlistOpen(true)}>
                <Plus size={15} />Manage
              </button>
            )}
            <button type="button" onClick={() => setSheetOpen(true)}>{sortSummary}</button>
          </div>
        </div>

        {loading ? (
          <div className="mobile-list-state">Loading stock insights...</div>
        ) : visibleSnapshots.length === 0 ? (
          <div className="mobile-list-state">
            <strong>{snapshots.length === 0 ? "No stock metrics loaded" : signedIn && baseSnapshots.length === 0 ? "Your watchlist is empty" : "No stocks match"}</strong>
            <p>{snapshots.length === 0 ? "The data bundle is empty." : signedIn && baseSnapshots.length === 0 ? "Add symbols to build your personal list." : "Try removing a filter or changing the search."}</p>
            {signedIn && baseSnapshots.length === 0 && (
              <button type="button" className="mobile-empty-watchlist-button" onClick={() => setWatchlistOpen(true)}>
                <Plus size={17} />Add symbols
              </button>
            )}
          </div>
        ) : (
          <>
            <section className="mobile-stock-list" aria-label="Stocks">
              {pagedSnapshots.map((snapshot) => {
                const metric = rowMetric(snapshot, sortKey, relevantSupportKeys);
                return (
                  <article className="mobile-stock-row" key={snapshot.ticker}>
                    <button type="button" className="mobile-stock-row-main" onClick={() => openDetail(snapshot.ticker)}>
                      <div className="mobile-stock-identity">
                        <strong>{snapshot.ticker}<ChevronRight size={18} /></strong>
                        <span>{snapshot.name ?? snapshot.industry ?? ""}</span>
                      </div>
                      <div className="mobile-stock-value">
                        <strong>{metric.value}</strong>
                        <StockStatus signal={metric.signal} />
                        {metric.secondary && <small>{metric.secondary}</small>}
                      </div>
                    </button>
                    {editMode && (
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
              })}
            </section>
            {visibleSnapshots.length > PAGE_SIZE && (
              <nav className="mobile-pagination" aria-label="Stocks pagination">
                <button
                  type="button"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  aria-label="Previous page"
                  title="Previous page"
                >
                  <ChevronLeft size={19} />
                </button>
                <strong>{currentPage} / {totalPages}</strong>
                <button
                  type="button"
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  aria-label="Next page"
                  title="Next page"
                >
                  <ChevronRight size={19} />
                </button>
              </nav>
            )}
          </>
        )}
      </main>

      <FilterSheet
        open={sheetOpen}
        expression={filterExpression}
        sortKey={sortKey}
        sortDirection={sortDirection}
        actions={actions}
        personalization={personalization}
        activeSavedFilterId={activeSavedFilterId}
        onClose={() => setSheetOpen(false)}
        onExpressionChange={setFilterExpression}
        onApplyPullbackPreset={() => toggleBuiltInPreset("pullback")}
        onApplySupportPreset={() => toggleBuiltInPreset("support")}
        onSortKeyChange={setSortKey}
        onSortDirectionChange={setSortDirection}
        onSelectSavedFilter={selectSavedFilter}
        onSavedFilter={(filter) => setActiveSavedFilterId(filter?.id ?? null)}
        onClear={() => {
          setFilterExpression({ operator: "and", groups: [] });
          setActiveSavedFilterId(null);
        }}
      />
      {personalization?.signedIn && (
        <WatchlistSheet
          open={watchlistOpen}
          snapshots={snapshots}
          watchlistTickers={personalization.watchlistTickers}
          onClose={() => setWatchlistOpen(false)}
          onAdd={personalization.onAddToWatchlist}
          onRemove={personalization.onRemoveFromWatchlist}
        />
      )}
    </div>
  );
}
