import type { OpenDataMetric, OpenDataStockSnapshot, ResearchMetric } from "./api";
import { metricSignal, type MetricSignal } from "./metricStatus";

export const SUPPORT_TIMEFRAMES = [
  { field: "support_1m", label: "1M", metric: "support_1m_distance" },
  { field: "support_3m", label: "3M", metric: "support_3m_distance" },
  { field: "support_6m", label: "6M", metric: "support_6m_distance" },
  { field: "support_1y", label: "1Y", metric: "support_1y_distance" },
  { field: "support_2y", label: "2Y", metric: "support_2y_distance" },
  { field: "support_5y", label: "5Y", metric: "support_5y_distance" },
] as const;
export type SupportFilterKey = typeof SUPPORT_TIMEFRAMES[number]["field"];
export const SUPPORT_FILTER_KEYS = SUPPORT_TIMEFRAMES.map(({ field }) => field);
export const SUPPORT_KEYS = Object.fromEntries(SUPPORT_TIMEFRAMES.map(({ field, metric }) => [field, metric])) as Record<SupportFilterKey, string>;
export function isSupportField(field: string): field is SupportFilterKey { return SUPPORT_TIMEFRAMES.some(t => t.field === field); }
export const DISABLED_FILTER_FIELDS = ["eps", "industry_strength", "valuation", "fcf_margin", "forward_pe", "balance_sheet"];
export function normalizedFilterValue(field: string, value: string) {
  if (isSupportField(field) && value === "Inside Support Zone") return "At Support";
  return field === "revenue" ? ({ "High Growth": "Strong", "Moderate Growth": "Solid", "Weak": "Weak" } as Record<string, string>)[value] ?? value : field === "momentum" && value === "Stable" ? "Steady" : value;
}
export const NUMERIC_FIELDS = ["revenue", "momentum", "operating_margin", "operating_margin_trend", "red_flag_count"];
export const NUMERIC_COMPARISONS = ["lt", "lte", "eq", "gte", "gt"] as const;
export type NumericComparison = typeof NUMERIC_COMPARISONS[number];
export function validNumericCondition(condition: { field: string; value?: string; comparison?: string }) {
  if (!NUMERIC_FIELDS.includes(condition.field) || !NUMERIC_COMPARISONS.some(c => c === condition.comparison)
      || typeof condition.value !== "string" || !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(condition.value.trim())
      || !Number.isFinite(Number(condition.value))) return false;
  return condition.field !== "red_flag_count" || (Number.isInteger(Number(condition.value)) && Number(condition.value) >= 0);
}
export function hasDisabledFilter(expression: { groups: { conditions: { field: string; value?: string; comparison?: string }[] }[] }) {
  return expression.groups.some(group => group.conditions.some(c => {
    const metric = stockMetricForField(c.field);
    return DISABLED_FILTER_FIELDS.includes(c.field) || !metric
      || (c.comparison != null ? !validNumericCondition(c) : c.field === "red_flag_count"
        || (c.value != null && !(metric.options as readonly string[]).includes(normalizedFilterValue(c.field, c.value))));
  }));
}
export function upcomingEarningsMetric(snapshot: OpenDataStockSnapshot): OpenDataMetric | undefined {
  const raw = snapshot.price_opportunity.days_to_next_earnings ?? snapshot.metrics.days_to_next_earnings;
  if (!raw) return undefined;
  const match = /:(\d{4}-\d{2}-\d{2})(?:\/(\d{4}-\d{2}-\d{2}))?$/.exec(raw.source ?? "");
  const start = match ? validDay(match[1]) : null;
  const end = match?.[2] ? validDay(match[2]) : start;
  const validWindow = start != null && end != null && end >= start;
  const value = match && validWindow && freshDay(raw.as_of) ? Math.round((Date.parse(`${match[1]}T00:00:00Z`) - Date.parse(`${new Date(Date.now()).toISOString().slice(0, 10)}T00:00:00Z`)) / 86400000) : null;
  return { ...raw, period: match ? match[0].slice(1) : undefined, value: value != null && value > 0 ? value : null };
}
export function upcomingEarningsSignal(metric?: OpenDataMetric): MetricSignal {
  const days = metric?.value;
  return metricSignal(days == null || !Number.isFinite(days) || days <= 0 ? "Unknown" : days <= 7 ? "This week" : days <= 30 ? "Next 30 days" : "Later");
}
function validDay(value?: string | null): number | null {
  const day = value?.slice(0, 10);
  const timestamp = Date.parse(`${day}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === day ? timestamp : null;
}
function freshDay(value?: string | null) {
  const timestamp = validDay(value);
  const age = timestamp == null ? -1 : (Date.now() - timestamp) / 86400000;
  return age >= 0 && age < 8;
}
export function researchMetric(snapshot: OpenDataStockSnapshot, key: string): ResearchMetric | undefined {
  const metric = snapshot.screening?.metrics[key];
  if (key === "forward_pe" && metric && (!freshDay(metric.estimate_as_of) || !freshDay(metric.price_as_of))) {
    return { ...metric, value: null, status: "Unknown", warnings: [...metric.warnings, "The estimate or market price is stale."] };
  }
  return metric;
}
// A valid zone must come from the detector and match a current saved quote.
export function supportMetric(snapshot: OpenDataStockSnapshot, field: SupportFilterKey = "support_1m") {
  const metric = snapshot.price_opportunity[SUPPORT_KEYS[field]];
  const quote = snapshot.price_opportunity.current_price;
  const zone = /Support zone: \$?([\d,.]+)-\$?([\d,.]+)/.exec(metric?.notes ?? "");
  const low = zone ? Number(zone[1].replace(/,/g, "")) : NaN;
  const high = zone ? Number(zone[2].replace(/,/g, "")) : NaN;
  if (typeof metric?.value !== "number" || !Number.isFinite(metric.value) || metric.tier !== "computed_from_public_facts"
      || !metric.source || metric.as_of !== quote?.as_of || !freshDay(metric.as_of)
      || !(low > 0 && high >= low) || typeof quote?.value !== "number" || !Number.isFinite(quote.value) || quote.value < low) return null;
  return { metric, signal: metricSignal(quote.value <= high ? "At Support" : metric.value <= 6 ? "Near Support" : "Above Support") };
}
export function businessMetric(snapshot: OpenDataStockSnapshot, key: string): ResearchMetric | undefined {
  const metric = researchMetric(snapshot, key);
  const definition = stockMetricForField(key);
  const deadline = metric?.valid_until;
  const today = new Date(Date.now()).toISOString().slice(0, 10);
  if (!metric?.validated || !definition || definition.context || validDay(deadline) == null || !deadline || deadline < today
      || (definition.format !== "label" && (typeof metric.value !== "number" || !Number.isFinite(metric.value)))
      || !(definition.options as readonly string[]).includes(metric.status)) return undefined;
  return metric;
}
export function visibleStockMetrics(snapshot: OpenDataStockSnapshot, context: boolean) {
  return STOCK_METRICS.filter(metric => metric.context === context
    && (metric.key === "red_flag_count" ? redFlagMetric(snapshot) != null : (metric.format === "label" ? businessMetric(snapshot, metric.key) != null : metric.getValue(snapshot) != null)));
}
export function redFlagMetric(snapshot: OpenDataStockSnapshot): ResearchMetric | undefined {
  const metric = researchMetric(snapshot, "red_flag_count");
  const today = new Date(Date.now()).toISOString().slice(0, 10);
  if (metric?.assessment_version !== 2 || !metric.coverage || !metric.valid_until
      || !["Complete assessment", "Partial assessment", "Not assessed"].includes(metric.status)
      || validDay(metric.valid_until) == null || metric.valid_until < today) return undefined;
  return metric;
}
export function redFlagValue(snapshot: OpenDataStockSnapshot): number | null {
  const metric = redFlagMetric(snapshot);
  return metric?.validated && metric.status === "Complete assessment" && metric.coverage?.complete && Number.isInteger(metric.value)
    && metric.value != null && metric.value >= 0 && metric.value <= (metric.max_count ?? 0) ? metric.value : null;
}
export function redFlagDisplay(snapshot: OpenDataStockSnapshot): string {
  const metric = redFlagMetric(snapshot);
  const value = redFlagValue(snapshot);
  return value != null ? String(value) : metric?.observed_count ? `≥${metric.observed_count}` : "Not fully assessed";
}
export function metricEvidence(metric?: ResearchMetric, includeWarnings = true): string {
  if (!metric) return "Unknown: comparable financial inputs are unavailable.";
  return [metric.period, metric.currency, `As of ${metric.as_of || "Unknown"}`, metric.estimate_as_of ? `Estimate dated ${metric.estimate_as_of}` : "", metric.formula, metric.notes, `Source: ${metric.source}`, ...(includeWarnings ? metric.warnings : [])].filter(Boolean).join(" · ");
}
type Definition = {
  key: string; field: string; title: string; shortLabel: string; question: string; description: string;
  format: "percent" | "ratio" | "days" | "pp" | "support" | "compact" | "count" | "label";
  context: boolean; options: string[];
  getSignal: (s: OpenDataStockSnapshot) => MetricSignal;
  getValue: (s: OpenDataStockSnapshot) => number | null;
};
const financialMetric = (key: string) => ({
  getSignal: (s: OpenDataStockSnapshot) => metricSignal((key === "revenue" ? businessMetric(s, key)?.strength : undefined) ?? businessMetric(s, key)?.status ?? "Unknown"),
  getValue: (s: OpenDataStockSnapshot) => businessMetric(s, key)?.value ?? null,
});
export const STOCK_METRICS = [
  { key: "revenue", field: "revenue", title: "Revenue Growth YoY", shortLabel: "Revenue YoY", format: "percent", context: false,
    question: "Is the business growing right now?", description: "Compares the company's revenue in its latest reported quarter with the same quarter one year earlier. It shows how quickly the company's sales are growing or declining. For example, +15% means the company generated 15% more revenue than in the same quarter last year.",
    options: ["Strong", "Solid", "Flat growth", "Weak", "Growing", "Flat", "Declining"], ...financialMetric("revenue") },
  { key: "momentum", field: "momentum", title: "Revenue Growth Momentum", shortLabel: "Momentum", format: "pp", context: false,
    question: "Is the company's growth getting stronger or weaker?", description: "Compares the company's typical recent revenue growth with its earlier growth. It shows whether sales growth is speeding up, holding a similar pace or slowing down. For example, moving from typical growth of 10% to 16% means growth accelerated by 6 percentage points. Growth can slow down while sales are still increasing.",
    options: ["Accelerating", "Steady", "Decelerating"], ...financialMetric("momentum") },
  { key: "revenue_consistency", field: "revenue_consistency", title: "Revenue Growth Consistency", shortLabel: "Consistency", format: "label", context: false,
    question: "Has quarterly revenue growth followed a regular pattern?", description: "Looks at how smoothly the company's revenue growth has changed over recent quarters. It helps distinguish a regular trend from sudden spikes and reversals. For example, growth of 12%, 14%, 16%, 18%, 20% and 22% follows a steady pattern, while 15%, −5%, 30%, 2%, 40% and −10% is choppy. A steady pattern can include slowing growth or declining sales.",
    options: ["Steady", "Choppy"], ...financialMetric("revenue_consistency") },
  { key: "operating_margin", field: "operating_margin", title: "Operating Margin", shortLabel: "Operating margin", format: "percent", context: false,
    question: "What portion of the company's sales becomes operating profit?", description: "Shows how much of the company's quarterly revenue remains after operating expenses, before interest and taxes. It helps explain how profitably the company runs its business. For example, a 20% operating margin means the company generated 20 in operating profit for every 100 in sales.",
    options: ["Profitable", "Loss-making"], ...financialMetric("operating_margin") },
  { key: "operating_margin_trend", field: "operating_margin_trend", title: "Operating Margin Trend", shortLabel: "Margin trend", format: "pp", context: false,
    question: "Is the company keeping more or less operating profit from its sales?", description: "Compares the company's latest quarterly operating margin with the same quarter one year earlier. It shows whether operating profitability is improving, staying the same or declining. For example, a margin rising from 15% to 20% is an improvement of 5 percentage points. A company can improve its margin while still making an operating loss.",
    options: ["Improving", "Stable", "Declining"], ...financialMetric("operating_margin_trend") },
  { key: "red_flag_count", field: "red_flag_count", title: "Red Flag Count", shortLabel: "Red flags", format: "count", context: false,
    question: "Which potential financial concerns appear in the company's reported data?", description: "Counts the concern groups detected across cash generation, operating profitability, the balance sheet and valuation. It helps identify areas that deserve a closer look. For example, a count of 2 means two of the four groups triggered a warning. Zero means none of these rules detected a concern in a complete assessment; it does not mean the investment has no risks.",
    options: ["Complete assessment", "Partial assessment", "Not assessed"],
    getSignal: s => metricSignal(redFlagMetric(s)?.status ?? "Not assessed"), getValue: redFlagValue },
  { key: "support", field: "support", title: "Proximity to Support", shortLabel: "Support", format: "support", context: true,
    question: "How close is the stock's price to an area where buyers have recently stepped in?", description: "Compares the latest closing price with a detected support zone. It shows whether the stock is trading inside or above a price area where earlier declines found buyers. For example, a price of $364 and a support midpoint of $349 gives a distance of about +4.3%. A support zone is an estimate; the price can fall through it.",
    options: ["At Support", "Near Support", "Above Support"], getSignal: s => SUPPORT_TIMEFRAMES.map(t => supportMetric(s, t.field)).find(Boolean)?.signal ?? metricSignal("Unknown"), getValue: s => SUPPORT_TIMEFRAMES.map(t => supportMetric(s, t.field)).find(Boolean)?.metric.value ?? null },
  { key: "upcoming_earnings", field: "upcoming_earnings", title: "Upcoming Earnings", shortLabel: "Earnings", format: "days", context: true,
    question: "When is the company expected to report its next earnings?", description: "Shows how soon the company's next earnings release is expected. It helps identify an approaching report that may bring new information about the business. For example, 5 days means the expected release is five calendar days away. Calendar dates are estimates unless confirmed by the company.",
    options: ["This week", "Next 30 days", "Later"], getSignal: (s) => upcomingEarningsSignal(upcomingEarningsMetric(s)), getValue: s => { const m = upcomingEarningsMetric(s); return upcomingEarningsSignal(m).label === "Unknown" ? null : m?.value ?? null; } },
] as const satisfies readonly Definition[];
export type StockMetricKey = typeof STOCK_METRICS[number]["key"];
export type StockMetricField = Exclude<typeof STOCK_METRICS[number]["field"], "support"> | SupportFilterKey;
export const STOCK_METRIC_BY_KEY = Object.fromEntries(STOCK_METRICS.map(m => [m.key, m])) as Record<StockMetricKey, typeof STOCK_METRICS[number]>;
export function stockMetricForField(field: string) { return STOCK_METRICS.find(m => m.field === (isSupportField(field) ? "support" : field)); }

export function financialLabelMatches(snapshot: OpenDataStockSnapshot, field: string, value: string): boolean {
  const m = businessMetric(snapshot, field);
  if (field === "revenue" && m) {
    if (value === "Growing") return m.value! > 0;
    if (value === "Declining") return m.value! < 0;
    if (value === "Flat growth") return m.strength === "Flat";
    if (value === "Flat") return m.status === "Flat";
  }
  return stockMetricForField(field)?.getSignal(snapshot).label === normalizedFilterValue(field, value);
}
