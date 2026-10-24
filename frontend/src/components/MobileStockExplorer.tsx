import { calculateRevenueGrowthMomentum, formatMomentumPp } from "../revenueGrowthMomentum";
import { MoneyPanel } from "./MoneyPanel";
import { useStockDetails } from "../useStockDetails";
import { prepareStockAnalysis, type StockAnalysisBrief } from "../aiAnalysis";
import { StockAnalysisDialog, type AnalysisCopyStatus } from "./StockAnalysisDialog";
import { FilterSelector, type FilterShortcut } from "./FilterSelector";
import { WatchlistGroups, type WatchlistGroupActions } from "./WatchlistGroups";
import type { WatchlistGroup, WatchlistItem } from "../watchlist";
import { MetricStatus } from "./MetricStatus";
import { metricSignal, supportSignal, type MetricSignal as Signal, type MetricTone as Tone } from "../metricStatus";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Bookmark,
  BookmarkCheck,
  BookmarkPlus,
  ArrowDownWideNarrow,
  ChevronDown,
  MoreHorizontal,
  Check,
  ChevronLeft,
  ChevronRight,
  ListTree,
  Sparkles,
  LogIn,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { FILTER_ICONS, filterIcon, type FilterIconName } from "../filterIcons";
import "../filterBuilder.css";
import { expressionFromMetricRules, groupSupportTimeframes, metricRuleFields, metricRulesFromExpression } from "../metricFilterRules";
import { STOCK_METRICS, STOCK_METRIC_BY_KEY, SUPPORT_KEYS, SUPPORT_FILTER_KEYS, SUPPORT_TIMEFRAMES,
  upcomingEarningsMetric, upcomingEarningsSignal, isSupportField, stockMetricForField, researchMetric, metricEvidence, hasDisabledFilter, normalizedFilterValue, financialDetail,
  type StockMetricKey, type StockMetricField, type SupportFilterKey } from "../stockMetrics";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchOpenDataStockPriceHistory,
  type OpenDataMetric,
  type OpenDataPricePoint,
  type OpenDataStockSnapshot,
} from "../api";
import {
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

type GrowthDetailKey = StockMetricKey;
export type FilterKey = StockMetricField | "valuation" | "eps" | "industry_strength";
export type SortKey = "watchlist_order" | "symbol" | "support_best" | Exclude<FilterKey, "forward_pe" | "industry_strength">;
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
  icon?: FilterIconName;
  operator: LogicOperator;
  groups: FilterGroup[];
};
type ChartRange = "1W" | "1M" | "3M" | "6M" | "1Y" | "2Y" | "5Y" | "ALL";
type MetricKind = "percent" | "ratio" | "compact" | "price" | "days";


type FilterDefinition = {
  key: FilterKey;
  label: string;
  shortLabel: string;
  section: "Growth" | "Quality" | "Catalyst" | "Support";
  description: string;
  options: Array<{ label: string; tone: Tone }>;
};

const AVAILABLE_FILTER_DEFINITIONS: FilterDefinition[] = STOCK_METRICS.flatMap((metric): FilterDefinition[] => {
  const base = { label: metric.title, shortLabel: metric.shortLabel, description: metric.description, options: metric.options.map(metricSignal) };
  return metric.field === "support"
    ? SUPPORT_TIMEFRAMES.map((timeframe) => ({ ...base, key: timeframe.field, shortLabel: `${timeframe.label} support`, section: "Support" }))
    : [{ ...base, key: metric.field, section: "Growth" }];
});
// Retired saved rules stay visible for editing, but cannot match stocks.
const FILTER_DEFINITIONS: FilterDefinition[] = [...AVAILABLE_FILTER_DEFINITIONS,
  ...(["valuation", "eps", "industry_strength"] as const).map(key => ({ key, label: `${key} (disabled)`, shortLabel: `${key} (disabled)`, section: "Quality" as const,
    description: "This metric has been retired from screening. Remove this rule before using the filter.", options: [metricSignal("Needs Review")] })),
];
const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "watchlist_order", label: "Group order" },
  { key: "symbol", label: "Symbol" },
  { key: "support_best", label: "Priority support" },
  ...AVAILABLE_FILTER_DEFINITIONS.flatMap(({ key, label, shortLabel }) => key === "forward_pe" || key === "industry_strength"
    ? [] : [{ key, label: isSupportField(key) ? shortLabel : label }]),
];

function supportedSortKey(key: SortKey, watchlistView: boolean): SortKey {
  if (!SORT_OPTIONS.some(option => option.key === key)) return "symbol";
  return key === "watchlist_order" && !watchlistView ? "support_best" : key;
}

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
  if (["valuation", "eps", "industry_strength"].includes(key)) return metricSignal("Needs Review");
  if (isSupportField(key)) return supportSignal(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value);
  return stockMetricForField(key)?.getSignal(snapshot) ?? metricSignal("Unclear");
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
  const definition = stockMetricForField(key);
  if (definition && !isSupportField(key)) return definition.getValue(snapshot);
  if (key === "eps" || key === "valuation") return null;
  if (key === "upcoming_earnings") return finiteNumber(upcomingEarningsMetric(snapshot)?.value);
  return isSupportField(key) ? finiteNumber(snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value) : null;
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
  const definition = stockMetricForField(key);
  if (definition && !definition.context) {
    const value = definition.getValue(snapshot);
    return { value: definition.format === "pp" ? formatMomentumPp(value) : definition.format === "compact" ? formatCompact(value) : definition.format === "ratio" ? formatNumber(value) : formatPercent(value, true),
      signal: definition.getSignal(snapshot), secondary: researchMetric(snapshot, definition.key)?.period ?? null };
  }
  if (key === "eps" || key === "valuation") return { value: "Unknown", signal: metricSignal("Needs Review"), secondary: "Disabled metric" };
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
  const value = isSupportField(key) ? snapshot.price_opportunity[SUPPORT_KEYS[key]]?.value : null;
  return { value: formatPercent(value, true), signal: supportSignal(value), secondary: key.replace("support_", "").toUpperCase() };
}

function nextFilterId(prefix: "group" | "condition") {
  return `${prefix}-${crypto.randomUUID()}`;
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
    operator: "and",
    conditions: [createCondition(field)],
  };
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
  if (hasDisabledFilter(expression)) return false;
  if (expression.groups.length === 0) return true;
  const groupMatches = expression.groups.map((group) => {
    if (group.conditions.length === 0) return true;
    const matches = group.conditions.map((condition) => signalFor(snapshot, condition.field).label === normalizedFilterValue(condition.field, condition.value));
    return group.operator === "and" ? matches.every(Boolean) : matches.some(Boolean);
  });
  return expression.operator === "and" ? groupMatches.every(Boolean) : groupMatches.some(Boolean);
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
  personalization,
  watchlistView = false,
  activeSavedFilterId,
  onClose,
  onApply,
  onSortKeyChange,
  onSortDirectionChange,
  onSavedFilter,
  onDeletedFilter,
}: {
  open: boolean;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
  personalization?: Props["personalization"];
  watchlistView?: boolean;
  activeSavedFilterId: string | null;
  onClose: () => void;
  onApply: (expression: FilterExpression) => void;
  onSortKeyChange: (key: SortKey) => void;
  onSortDirectionChange: (direction: SortDirection) => void;
  onSavedFilter: (filter: SavedFilter) => void;
  onDeletedFilter: (id: string) => void;
}) {
  const activeSavedFilter = personalization?.savedFilters.find((item) => item.id === activeSavedFilterId) ?? null;
  const [saveName, setSaveName] = useState(activeSavedFilter?.name ?? "");
  const [icon, setIcon] = useState<FilterIconName>(activeSavedFilter?.icon ?? (activeSavedFilter ? "sliders" : "trend"));
  const [initialRules] = useState(() => metricRulesFromExpression(expression));
  const [rules, setRules] = useState(() => groupSupportTimeframes(initialRules.rules));
  const [sortExpanded, setSortExpanded] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const busyRef = useRef(false);
  const initialState = useRef(JSON.stringify({ name: saveName.trim(), icon, rules, sortKey, sortDirection }));
  const count = rules.length;
  const hasEmptyValues = rules.some((rule) => rule.values.length === 0);
  const hasEmptyTimeframes = rules.some((rule) => metricRuleFields(rule).length === 0);
  const dirty = initialState.current !== JSON.stringify({ name: saveName.trim(), icon, rules, sortKey, sortDirection });
  const SelectedIcon = filterIcon(icon).Icon;

  useEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const viewport = window.visualViewport;
    const updateViewport = () => {
      dialog?.style.setProperty("--builder-viewport-height", `${viewport?.height ?? window.innerHeight}px`);
      dialog?.style.setProperty("--builder-viewport-top", `${viewport?.offsetTop ?? 0}px`);
      if (dialog?.contains(document.activeElement)) {
        const activeInput = document.activeElement;
        if (activeInput instanceof HTMLInputElement || activeInput instanceof HTMLSelectElement) {
          activeInput.scrollIntoView({ block: "nearest" });
        }
      }
    };
    updateViewport();
    dialog?.showModal();
    dialog?.querySelector<HTMLElement>("#filter-builder-title")?.focus({ preventScroll: true });
    viewport?.addEventListener("resize", updateViewport);
    viewport?.addEventListener("scroll", updateViewport);
    window.addEventListener("resize", updateViewport);
    return () => {
      viewport?.removeEventListener("resize", updateViewport);
      viewport?.removeEventListener("scroll", updateViewport);
      window.removeEventListener("resize", updateViewport);
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [open]);

  if (!open) return null;

  const close = () => {
    if (busyRef.current) return;
    if (!dirty || window.confirm("Discard your unsaved filter changes?")) onClose();
  };

  const submitSavedFilter = async () => {
    if (!saveName.trim() || count === 0 || hasEmptyValues || hasEmptyTimeframes || busyRef.current) return;
    const nextExpression = expressionFromMetricRules(rules, expression);
    if (!personalization) {
      onApply(nextExpression);
      return;
    }
    busyRef.current = true;
    setSaveBusy(true);
    setSaveError(null);
    try {
      if (!personalization.signedIn) {
        await personalization.onRequestSignIn();
        return;
      }
      const saved = await personalization.onSaveFilter({
        id: activeSavedFilter?.id,
        name: saveName.trim(),
        icon,
        expression: nextExpression,
        sortKey,
        sortDirection,
      });
      onSavedFilter(saved);
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not save this filter. Please try again.");
    } finally {
      busyRef.current = false;
      setSaveBusy(false);
    }
  };

  const deleteFilter = async () => {
    if (!personalization || !activeSavedFilter || busyRef.current) return;
    if (!window.confirm(`Delete “${activeSavedFilter.name}”? This cannot be undone.`)) return;
    busyRef.current = true;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await personalization.onDeleteFilter(activeSavedFilter.id);
      onDeletedFilter(activeSavedFilter.id);
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : "Could not delete this filter. Please try again.");
    } finally {
      busyRef.current = false;
      setSaveBusy(false);
    }
  };

  const addRule = () => {
    const definition = AVAILABLE_FILTER_DEFINITIONS.find((item) => !rules.some((rule) => metricRuleFields(rule).includes(item.key)));
    if (!definition) return;
    setRules([...rules, { id: nextFilterId("group"), field: definition.key, values: [definition.options[0].label] }]);
  };

  const availableMetricField = (field: string, id?: string): FilterKey | undefined => {
    const candidates = field === "support" ? SUPPORT_FILTER_KEYS : AVAILABLE_FILTER_DEFINITIONS.filter((item) => item.key === field).map((item) => item.key);
    return candidates.find((candidate) => !rules.some((rule) => rule.id !== id && metricRuleFields(rule).includes(candidate)));
  };

  const changeMetric = (id: string, selected: string) => {
    const field = availableMetricField(selected, id);
    if (!field) return;
    const definition = AVAILABLE_FILTER_DEFINITIONS.find((item) => item.key === field)!;
    setRules(rules.map((rule) => rule.id === id
      ? { ...rule, field, timeframes: isSupportField(field) ? [field] : undefined, values: [definition.options[0].label] }
      : rule));
  };

  const toggleSupportTimeframe = (id: string, field: SupportFilterKey) => {
    setRules((current) => {
      if (current.some((rule) => rule.id !== id && metricRuleFields(rule).includes(field))) return current;
      return current.map((rule) => {
        if (rule.id !== id) return rule;
        const fields = metricRuleFields(rule);
        const timeframes = SUPPORT_FILTER_KEYS.filter((item) => item === field ? !fields.includes(item) : fields.includes(item));
        return { ...rule, field: timeframes[0] ?? rule.field, timeframes };
      });
    });
  };

  const toggleValue = (id: string, value: string) => {
    setRules((current) => current.map((rule) => rule.id === id
      ? { ...rule, values: rule.values.includes(value) ? rule.values.filter((item) => item !== value) : [...rule.values, value] }
      : rule));
  };

  return (
    <dialog ref={dialogRef} className="mobile-builder-dialog" aria-labelledby="filter-builder-title"
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClick={(event) => { if (event.currentTarget === event.target) close(); }}>
      <form className="filter-builder" onSubmit={(event) => { event.preventDefault(); void submitSavedFilter(); }}>
        <header className="filter-builder-header">
          <div>
            <h2 id="filter-builder-title" tabIndex={-1}>{activeSavedFilter ? "Edit filter" : "New filter"}</h2>
            <p>Create your own stock screen</p>
          </div>
          <div className="filter-builder-header-actions">
            {activeSavedFilter && <details className="filter-builder-menu">
              <summary aria-label="Filter options"><MoreHorizontal size={20} aria-hidden="true" /></summary>
              <button type="button" onClick={() => void deleteFilter()} disabled={saveBusy}>
                <Trash2 size={16} aria-hidden="true" />Delete filter
              </button>
            </details>}
            <button type="button" className="filter-builder-icon-button" onClick={close} disabled={saveBusy} aria-label="Close filter editor">
              <X size={20} aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="filter-builder-scroll">
          <fieldset className="filter-builder-fields" disabled={saveBusy}>
            <section className="filter-builder-section" aria-labelledby="filter-builder-identity">
              <div className="filter-builder-heading">
                <h3 id="filter-builder-identity"><span aria-hidden="true">1</span>Name &amp; icon</h3>
              </div>
              <div className="filter-builder-name-row">
                <span className="filter-builder-avatar" aria-hidden="true"><SelectedIcon size={26} strokeWidth={1.8} /></span>
                <label className="filter-builder-field">
                  <span>Filter name</span>
                  <input type="text" value={saveName} onChange={(event) => setSaveName(event.target.value)}
                    placeholder="e.g. Growth near support" maxLength={80} required autoComplete="off" />
                </label>
              </div>
              <div className="filter-builder-icons-row">
                <span>Choose an icon</span>
                <div className="filter-builder-icons" role="group" aria-label="Filter icon">
                  {FILTER_ICONS.map(({ name, label, Icon }) => (
                    <button key={name} type="button" aria-label={`${label} icon`} title={label} aria-pressed={icon === name}
                      onClick={() => setIcon(name)}><Icon size={21} strokeWidth={1.8} aria-hidden="true" /></button>
                  ))}
                </div>
              </div>
            </section>

            <section className="filter-builder-section" aria-labelledby="filter-builder-conditions">
              <div className="filter-builder-heading">
                <h3 id="filter-builder-conditions"><span aria-hidden="true">2</span>Conditions</h3>
                <span>{count} {count === 1 ? "rule" : "rules"}</span>
              </div>
              <p className="filter-builder-description">Match every metric below, using any selected value.</p>
              {initialRules.logicChanged && <p className="filter-builder-hint" role="note">
                This filter used different matching rules. Saving will require every metric below to match.
              </p>}
              <div className="filter-builder-conditions">
                {rules.map((rule, index) => {
                  const definition = FILTER_DEFINITIONS.find((item) => item.key === rule.field) ?? FILTER_DEFINITIONS[0];
                  return <div className="filter-builder-condition" key={rule.id}>
                    <div className="filter-builder-condition-heading">
                      <span>Condition {index + 1}</span>
                      <button type="button" className="filter-builder-icon-button"
                        onClick={() => setRules(rules.filter((item) => item.id !== rule.id))}
                        aria-label={`Remove ${definition.shortLabel} condition`}><X size={16} aria-hidden="true" /></button>
                    </div>
                    <div className="filter-builder-condition-fields">
                      <div className="filter-builder-metric-fields">
                        <label className="filter-builder-field">
                          <span>Metric</span>
                          <select value={isSupportField(rule.field) ? "support" : rule.field}
                            onChange={(event) => changeMetric(rule.id, event.target.value)}>
                            {["eps", "valuation", "industry_strength"].includes(rule.field) && <option value={rule.field}>{rule.field} (disabled)</option>}
                            {STOCK_METRICS.map((metric) => <option key={metric.key} value={metric.field}
                              disabled={!availableMetricField(metric.field, rule.id)}>{metric.title}</option>)}
                          </select>
                        </label>
                        {isSupportField(rule.field) && <fieldset className="filter-builder-values" aria-label={`Condition ${index + 1} timeframes`}>
                          <legend>Timeframes <span>Choose one or more</span></legend>
                          <div className="filter-builder-value-options">
                            {SUPPORT_TIMEFRAMES.map((timeframe) => <label className="filter-builder-value" key={timeframe.field}>
                              <input type="checkbox" checked={metricRuleFields(rule).includes(timeframe.field)}
                                disabled={rules.some((other) => other.id !== rule.id && metricRuleFields(other).includes(timeframe.field))}
                                onChange={() => toggleSupportTimeframe(rule.id, timeframe.field)} />
                              <Check size={14} aria-hidden="true" /><span>{timeframe.label}</span>
                            </label>)}
                          </div>
                          {metricRuleFields(rule).length === 0
                            ? <p className="filter-builder-value-error" role="status">Choose at least one timeframe.</p>
                            : <p className="filter-builder-timeframe-hint">Match values in every selected timeframe.</p>}
                        </fieldset>}
                        {["eps", "valuation", "industry_strength"].includes(rule.field) && <p className="filter-builder-hint">
                          This metric is disabled for screening. Replace or remove this condition before using the filter.
                        </p>}
                      </div>
                      <fieldset className="filter-builder-values" aria-label={`${definition.shortLabel} values`}>
                        <legend>Values <span>Choose one or more</span></legend>
                        <div className="filter-builder-value-options">
                          {definition.options.map((option) => <label className="filter-builder-value" key={option.label}>
                            <input type="checkbox" checked={rule.values.includes(option.label)}
                              onChange={() => toggleValue(rule.id, option.label)} />
                            <Check size={14} aria-hidden="true" /><span>{option.label}</span>
                          </label>)}
                        </div>
                        {rule.values.length === 0 && <p className="filter-builder-value-error" role="status">Choose at least one value.</p>}
                      </fieldset>
                    </div>
                  </div>;
                })}
              </div>
              <button type="button" className="filter-builder-add" onClick={addRule} disabled={!AVAILABLE_FILTER_DEFINITIONS.some((item) => !rules.some((rule) => metricRuleFields(rule).includes(item.key)))}>
                <Plus size={18} aria-hidden="true" />Add condition
              </button>
            </section>

            <section className="filter-builder-section" aria-labelledby="filter-builder-sorting">
              <div className="filter-builder-heading">
                <h3 id="filter-builder-sorting"><span aria-hidden="true">3</span>Sorting</h3>
                <span>Optional</span>
              </div>
              <button type="button" className="filter-builder-sort-summary" aria-expanded={sortExpanded}
                aria-controls="filter-builder-sort-options" onClick={() => setSortExpanded(!sortExpanded)}>
                <ArrowDownWideNarrow size={21} aria-hidden="true" />
                <span><strong>{SORT_OPTIONS.find((option) => option.key === sortKey)?.label ?? "Symbol"}</strong>
                  <small>{sortDirection === "asc" ? "Ascending" : "Descending"} order</small></span>
                <ChevronDown size={18} aria-hidden="true" />
              </button>
              {sortExpanded && <div id="filter-builder-sort-options" className="filter-builder-sort-options">
                <label className="filter-builder-field">
                  <span>Sort by</span>
                  <select value={sortKey} onChange={(event) => onSortKeyChange(event.target.value as SortKey)}>
                    {SORT_OPTIONS.filter((option) => option.key !== "watchlist_order" || watchlistView)
                      .map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
                  </select>
                </label>
                <label className="filter-builder-field">
                  <span>Order</span>
                  <select value={sortDirection} onChange={(event) => onSortDirectionChange(event.target.value as SortDirection)}>
                    <option value="asc">Ascending</option><option value="desc">Descending</option>
                  </select>
                </label>
              </div>}
            </section>
          </fieldset>
        </div>

        <footer className="filter-builder-footer">
          {saveError && <p className="filter-builder-error" role="alert">{saveError}</p>}
          {personalization && !personalization.signedIn && <p className="filter-builder-hint">Sign in to save and sync your filters.</p>}
          {count === 0 && <p className="filter-builder-hint">Add a condition to save your filter.</p>}
          <button type="submit" className="filter-builder-save" disabled={saveBusy || !saveName.trim() || count === 0 || hasEmptyValues || hasEmptyTimeframes}>
            {personalization && !personalization.signedIn ? <LogIn size={19} aria-hidden="true" /> : <Check size={20} aria-hidden="true" />}
            {saveBusy ? "Please wait…" : !personalization ? "Apply filter" : personalization.signedIn ? "Save filter" : "Sign in to save filter"}
          </button>
        </footer>
      </form>
    </dialog>
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

function MobileGrowthDetailPanel({ snapshot, detailKey, onOpenPeer }: { snapshot: OpenDataStockSnapshot; detailKey: GrowthDetailKey; onOpenPeer: (ticker: string) => void }) {
  const copy = STOCK_METRIC_BY_KEY[detailKey];
  const momentum = revenueMomentum(snapshot);
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

  const metric = researchMetric(snapshot, detailKey);
  const value = copy.getValue(snapshot);
  const currentValue = value == null ? "Unknown" : copy.format === "pp" ? formatMomentumPp(value)
    : copy.format === "compact" ? formatCompact(value) : copy.format === "ratio" ? `${formatNumber(value)}x` : formatPercent(value, true);
  return <section className="mobile-growth-detail-panel">
    <div className="mobile-growth-copy">
      <span>Metric definition</span><h2>{copy.title}</h2>
      <p className="metric-question">{copy.question}</p><p>{copy.description}</p>
    </div>
    <div className="mobile-growth-formula">
      <span>{metric?.period || "Current value"}</span><strong>{currentValue}</strong>
      <StockStatus signal={copy.getSignal(snapshot)} />
      {detailKey === "operating_margin" && metric?.yoy_change_pp != null && <small>{formatMomentumPp(metric.yoy_change_pp)} versus the same quarter last year</small>}
      <small>{metric?.formula}</small>
      {(metric?.warnings ?? []).map(warning => <small key={warning}>{warning}</small>)}
      <details className="mobile-metric-evidence"><summary>Sources and calculation</summary><small>{metricEvidence(metric, false)}</small></details>
      {detailKey === "balance_sheet" && Object.entries(metric?.components ?? {}).map(([key, component]) => <div key={key}>
        <p>{({ cash: "Cash (see reported scope)", short_term_investments: "Short-term investments", long_term_investments: "Long-term investments", debt: "Debt (see scope below)" } as Record<string, string>)[key]}: {component.value == null ? "Unknown" : `${component.currency ?? "Currency unknown"} ${formatCompact(component.value)}`}</p>
        <details className="mobile-metric-evidence"><summary>Reported scope and source</summary><small>{metricEvidence(component)}</small></details>
      </div>)}
    </div>
    {(detailKey === "revenue" || detailKey === "momentum" || detailKey === "operating_margin") && <GrowthChart
      title={detailKey === "operating_margin" ? "Quarterly operating margin" : "Quarterly revenue growth YoY"}
      points={detailKey === "operating_margin" ? quarterlyMetricPoints(snapshot, "operating_margin") : revenueGrowthPoints(snapshot)}
      selectedPeriods={detailKey === "momentum" ? momentum.points.map(p => p.period) : undefined} />}
  </section>;
}

function StockDetail({ snapshot: summary, onBack, onOpenPeer }: { snapshot: OpenDataStockSnapshot; onBack: () => void; onOpenPeer: (ticker: string) => void }) {
  const { snapshot, loading: detailsLoading, error: detailsError, retry: retryDetails } = useStockDetails(summary);
  const [activeGrowthDetail, setActiveGrowthDetail] = useState<GrowthDetailKey>("revenue");
  const [points, setPoints] = useState<OpenDataPricePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentPrice = snapshot.price_opportunity.current_price?.value;
  const dailyChange = snapshot.price_opportunity.change_1d?.value;
  const support = closestSupport(snapshot);

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

        <section className="mobile-signal-strip" aria-label="Earnings and technical context">
          {STOCK_METRICS.filter(metric => metric.context).map(metric => <MobileGrowthSignalButton key={metric.key}
            active={activeGrowthDetail === metric.key} label={metric.title} className="mobile-support-signal"
            value={metric.key === "support" ? support?.window ?? "Unknown" : formatMetric(upcomingEarningsMetric(snapshot), "days")}
            signal={metric.key === "support" ? supportSignal(support?.value) : metric.getSignal(snapshot)}
            onClick={() => setActiveGrowthDetail(metric.key)} />)}
        </section>

	        <section className="mobile-signal-strip" aria-label="Financial research metrics">
          {STOCK_METRICS.filter(metric => !metric.context).map((metric) => {
            const value = metric.getValue(snapshot);
            const signal = metric.getSignal(snapshot);
            const balances = metric.key === "balance_sheet" ? researchMetric(snapshot, "balance_sheet")?.components : undefined;
            const displayValue = balances ? `${formatCompact(balances.cash?.value)} / ${formatCompact(balances.debt?.value)}` : value == null ? "Unknown" : metric.format === "pp" ? formatMomentumPp(value)
              : metric.format === "percent" ? formatPercent(value, true)
              : metric.format === "compact" ? formatCompact(value) : `${formatNumber(value)}x`;
            return <MobileGrowthSignalButton key={metric.key}
              active={activeGrowthDetail === metric.key}
              label={metric.key === "fcf_margin" ? `${metric.title} · TTM` : metric.key === "balance_sheet" ? "Balance Sheet · Cash / debt" : metric.title}
              signal={signal}
              value={displayValue}
              onClick={() => setActiveGrowthDetail(metric.key)} />;
          })}
        </section>


        {(snapshot.screening?.warnings ?? []).map(warning => <details key={warning} className="mobile-research-warning">
          <summary>Needs Review: reported earnings</summary><p>{warning}</p>
        </details>)}
        {detailsLoading && <p role="status">Loading financial history…</p>}
        {detailsError && <p role="alert">{detailsError} <button type="button" onClick={retryDetails}>Retry financial history</button></p>}
        <MobileGrowthDetailPanel snapshot={snapshot} detailKey={activeGrowthDetail} onOpenPeer={onOpenPeer} />

        <details className="mobile-growth-detail-panel">
          <summary>Financial Details</summary>
          {Object.keys(snapshot.screening?.financial_details ?? {}).map(key => {
            const metric = financialDetail(snapshot, key)!;
            return <div key={key}>
              <p>{({ gross_margin: "Gross Margin", price_to_sales: "Price / Sales", fcf_yield: "FCF Yield" } as Record<string, string>)[key]}: {metric.value == null ? "Unknown" : `${formatNumber(metric.value)}${key === "price_to_sales" ? "x" : "%"}`}</p>
              <small>{metric.period}</small>
              <small>{metric.formula}</small>
              {metric.warnings.map(warning => <small key={warning}>{warning}</small>)}
              <details className="mobile-metric-evidence"><summary>Sources and calculation</summary><small>{metricEvidence(metric, false)}</small></details>
            </div>;
          })}
          <p>{snapshot.screening?.verification ?? "Source identifiers preserve provenance; inputs have not been independently verified."}</p>
        </details>

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
  const [watchlistOrganizing, setWatchlistOrganizing] = useState(false);
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
  const activeSavedFilter = personalization?.savedFilters.find((item) => item.id === activeSavedFilterId) ?? null;
  const relevantSupportKeys = SUPPORT_FILTER_KEYS;
  const signedIn = personalization?.signedIn ?? false;
  const isWatchlistView = signedIn && spaceTab === "watchlist";
  const watchlistTickers = personalization?.watchlistTickers ?? [];
  const watchlist = useMemo(() => new Set(watchlistTickers), [watchlistTickers]);
  const watchlistItems = personalization?.watchlistItems ?? [];
  const watchlistGroups = personalization?.watchlistGroups ?? [];
  const watchlistReady = !loading && !personalization?.watchlistLoading && !personalization?.watchlistLoadError;
  const showListControls = !isWatchlistView || (watchlistReady && watchlistTickers.length > 0);
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
  const pagedSnapshots = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return expandedSnapshots.slice(start, start + PAGE_SIZE);
  }, [currentPage, expandedSnapshots]);
  const listSummaryLabel = `${visibleSnapshots.length} ${visibleSnapshots.length === 1 ? "company" : "companies"}`;

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
    setWatchlistOrganizing(false);
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
    if (!isWatchlistView) return;
    setAnalysisSelection((tickers) => tickers.filter((ticker) => watchlist.has(ticker)));
    if (watchlist.size === 0) setAnalysisMode(false);
  }, [isWatchlistView, watchlist]);

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

  const savedExpression = (filter: SavedFilter): FilterExpression => ({
    ...filter.expression,
    groups: filter.expression.groups.map((group) => ({
      ...group,
      conditions: group.conditions.map((condition) => ({
        ...condition,
        // Preserve filters saved before metric-specific labels were introduced.
        value: condition.field === "revenue" ? ({ Strong: "High Growth", Solid: "Moderate Growth", Weak: "Declining", Unclear: "Unknown", Unavailable: "Unknown" } as Record<string, string>)[condition.value] ?? condition.value
          : condition.field === "momentum" && condition.value === "Stable" ? "Steady" : condition.value,
      })),
    })),
  });

  const selectSavedFilter = (filter: SavedFilter) => {
    setFilterExpression(savedExpression(filter));
    setSortKey(supportedSortKey(filter.sort_key, isWatchlistView));
    setSortDirection(filter.sort_direction);
    setActiveSavedFilterId(filter.id);
  };

  const openFilterBuilder = (filter?: SavedFilter) => {
    setFilterDraft({
      expression: filter ? savedExpression(filter) : { operator: "and", groups: [createFilterGroup()] },
      sortKey: supportedSortKey(filter?.sort_key ?? sortKey, isWatchlistView),
      sortDirection: filter?.sort_direction ?? sortDirection,
      savedFilterId: filter?.id ?? null,
    });
    setSheetOpen(true);
  };

  const applyFilterDraft = (expression: FilterExpression) => {
    const saved = personalization?.savedFilters.find((filter) => filter.id === filterDraft.savedFilterId);
    setFilterExpression(expression);
    setSortKey(filterDraft.sortKey === "watchlist_order" && !isWatchlistView ? "support_best" : filterDraft.sortKey);
    setSortDirection(filterDraft.sortDirection);
    setActiveSavedFilterId(saved && JSON.stringify(savedExpression(saved)) === JSON.stringify(expression) ? saved.id : null);
    setSheetOpen(false);
  };

  const filterShortcuts: FilterShortcut[] = (personalization?.savedFilters ?? []).map((filter) => ({
    key: savedFilterKey(filter.id), name: filter.name, icon: filter.icon,
    badgeCount: personalization?.filterBadgeCounts[savedFilterKey(filter.id)],
  }));
  const activeShortcutKey = activeSavedFilter ? savedFilterKey(activeSavedFilter.id) : null;
  const activeFilterName = filterCount > 0 ? activeSavedFilter?.name ?? "Custom filter" : null;

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
    setWatchlistOrganizing(false);
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

  const openExplore = () => {
    selectSpaceTab("explore");
    document.getElementById("space-explore-tab")?.focus();
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
        <StockDetail snapshot={selectedSnapshot} onBack={closeDetail} onOpenPeer={openDetail} />
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
        {showListControls && <>
        <div className="mobile-stock-search-tools" ref={listTopRef}>
        <label className="mobile-stock-search">
          <Search size={20} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={isWatchlistView ? "Search your watchlist" : "Search companies"}
            aria-label={isWatchlistView ? "Search your watchlist" : "Search stocks"}
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={17} /></button>
          )}
        </label>

        <FilterSelector key={personalization?.userId ?? "guest"}
          compact
          userId={personalization?.userId ?? null}
          filters={filterShortcuts}
          activeKey={activeShortcutKey}
          activeName={activeFilterName}
          onClear={clearFilter}
          onSelect={(key) => {
            const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
            if (filter) selectSavedFilter(filter);
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
          onRename={async (key, name) => {
            const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
            if (!filter || !personalization) throw new Error("This filter is no longer available.");
            await personalization.onSaveFilter({
              id: filter.id,
              name,
              expression: filter.expression,
              sortKey: supportedSortKey(filter.sort_key, isWatchlistView),
              sortDirection: filter.sort_direction,
            });
          }}
          onDelete={async (key) => {
            const filter = personalization?.savedFilters.find((item) => savedFilterKey(item.id) === key);
            if (!filter || !personalization) return;
            await personalization.onDeleteFilter(filter.id);
            if (activeSavedFilterId === filter.id) clearFilter();
          }}
        />
        </div>

        {!isWatchlistView && <div className="mobile-list-summary">
          <span>{listSummaryLabel}</span>
          <div className="mobile-list-actions">
            {analysisMode ? (
              <button type="button" onClick={cancelAnalysis}>Cancel</button>
            ) : visibleSnapshots.length > 0 ? (
              <button type="button" className="stock-analysis-trigger" onClick={startAnalysis} disabled={visibleSnapshots.length === 0}>
                <Sparkles size={17} aria-hidden="true" />Analyze<ChevronRight size={15} aria-hidden="true" />
              </button>
            ) : null}
          </div>
        </div>}
        {isWatchlistView && <div className="watchlist-actions" role="group" aria-label="Watchlist actions">
          <button type="button" className="watchlist-action" onClick={openExplore}>
            <Plus size={18} aria-hidden="true" />Add stocks
          </button>
          <button type="button" className="watchlist-action" onClick={analysisMode ? cancelAnalysis : startAnalysis}
            disabled={!analysisMode && visibleSnapshots.length === 0}>
            {analysisMode ? <X size={18} aria-hidden="true" /> : <Sparkles size={18} aria-hidden="true" />}
            {analysisMode ? "Cancel" : "Analyze"}
          </button>
          <button type="button" className="watchlist-action" aria-pressed={watchlistOrganizing}
            disabled={!watchlistOrganizing && visibleSnapshots.length === 0} onClick={() => setWatchlistOrganizing((current) => !current)}>
            {watchlistOrganizing ? <Check size={18} aria-hidden="true" /> : <ListTree size={18} aria-hidden="true" />}
            {watchlistOrganizing ? "Done" : "Organize"}
          </button>
        </div>}
        {analysisMode && (
          <p className="stock-analysis-selection-hint">Select companies to compare, then generate an AI brief.</p>
        )}
        </>}
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
          watchlistTickers.length === 0 ? (
            <section className="watchlist-empty" aria-labelledby="watchlist-empty-title">
              <div className="watchlist-empty-icon" aria-hidden="true"><Bookmark size={30} strokeWidth={1.8} /></div>
              <h2 id="watchlist-empty-title">Your watchlist is empty</h2>
              <p>Add companies to track their performance and discover investment opportunities.</p>
              <button type="button" className="watchlist-add-stocks watchlist-empty-add" onClick={openExplore}>
                <Plus size={20} aria-hidden="true" />Add stocks
              </button>
              <small>Groups can be created after adding stocks</small>
            </section>
          ) : visibleSnapshots.length === 0 ? (
            <div className="mobile-list-state">
              <strong>{baseSnapshots.length === 0 ? "Stock insights are unavailable" : "No stocks match"}</strong>
              <p>{baseSnapshots.length === 0 ? "Your stocks are still saved. Their insights will appear when data is available." : "Try removing a filter or changing the search."}</p>
              {(query || filterCount > 0) && <button type="button" className="mobile-empty-watchlist-button" onClick={() => { setQuery(""); clearFilter(); }}>Clear search and filters</button>}
            </div>
          ) : (
          <>
            <WatchlistGroups key={personalization.userId ?? "watchlist"}
              groups={watchlistGroups} items={watchlistItems}
              organizing={watchlistOrganizing}
              matchingSnapshots={visibleSnapshots} pagedSnapshots={pagedSnapshots}
              renderRow={renderStockRow}
              onRevealGroup={(groupId) => {
                const index = expandedSnapshots.findIndex((snapshot) => (watchlistOrder.get(snapshot.ticker)?.group_id ?? null) === groupId);
                if (index >= 0) goToPage(Math.floor(index / PAGE_SIZE) + 1);
              }}
              onManualOrder={() => { setSortKey("watchlist_order"); setSortDirection("asc"); }}
              onRemove={personalization.onRemoveFromWatchlist} actions={personalization} />
            {pagination}
          </>
          )
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
        {analysisMode && showListControls && (
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

      {hasDisabledFilter(filterExpression) && <p role="status">This saved filter contains retired metric rules or labels. Edit or remove those conditions to use it.</p>}
      {sheetOpen && <FilterSheet
        open={sheetOpen}
        expression={filterDraft.expression}
        sortKey={filterDraft.sortKey}
        sortDirection={filterDraft.sortDirection}
        personalization={personalization}
        watchlistView={isWatchlistView}
        activeSavedFilterId={filterDraft.savedFilterId}
        onClose={() => setSheetOpen(false)}
        onApply={applyFilterDraft}
        onSortKeyChange={(sortKey) => setFilterDraft((draft) => ({ ...draft, sortKey }))}
        onSortDirectionChange={(sortDirection) => setFilterDraft((draft) => ({ ...draft, sortDirection }))}
        onSavedFilter={(filter) => { selectSavedFilter(filter); setSheetOpen(false); }}
        onDeletedFilter={(id) => {
          if (activeSavedFilterId === id) clearFilter();
          setSheetOpen(false);
        }}
      />}
    </div>
  );
}
