import type { OpenDataMetric, OpenDataStockSnapshot, ResearchMetric } from "./api";
import { metricSignal, type MetricSignal } from "./metricStatus";
import { REVENUE_MOMENTUM_DESCRIPTION } from "./revenueGrowthMomentum";

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
  return field === "momentum" && value === "Stable" ? "Steady" : value;
}
export function hasDisabledFilter(expression: { groups: { conditions: { field: string; value?: string }[] }[] }) {
  return expression.groups.some(group => group.conditions.some(c => {
    const metric = stockMetricForField(c.field);
    return DISABLED_FILTER_FIELDS.includes(c.field) || !metric || (c.value != null && !(metric.options as readonly string[]).includes(normalizedFilterValue(c.field, c.value)));
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
  return { metric, signal: metricSignal(quote.value <= high ? "Inside Support Zone" : metric.value <= 6 ? "Near Support" : "Above Support") };
}
export function businessMetric(snapshot: OpenDataStockSnapshot, key: string): ResearchMetric | undefined {
  const metric = researchMetric(snapshot, key);
  const definition = stockMetricForField(key);
  const deadline = metric?.valid_until;
  const today = new Date(Date.now()).toISOString().slice(0, 10);
  if (!metric?.validated || !definition || definition.context || validDay(deadline) == null || !deadline || deadline < today
      || typeof metric.value !== "number" || !Number.isFinite(metric.value)
      || !(definition.options as readonly string[]).includes(metric.status)) return undefined;
  return metric;
}
export function visibleStockMetrics(snapshot: OpenDataStockSnapshot, context: boolean) {
  return STOCK_METRICS.filter(metric => metric.context === context && metric.getValue(snapshot) != null);
}
export function metricEvidence(metric?: ResearchMetric, includeWarnings = true): string {
  if (!metric) return "Unknown: comparable financial inputs are unavailable.";
  return [metric.period, metric.currency, `As of ${metric.as_of || "Unknown"}`, metric.estimate_as_of ? `Estimate dated ${metric.estimate_as_of}` : "", metric.formula, metric.notes, `Source: ${metric.source}`, ...(includeWarnings ? metric.warnings : [])].filter(Boolean).join(" · ");
}
type Definition = {
  key: string; field: string; title: string; shortLabel: string; question: string; description: string;
  format: "percent" | "ratio" | "days" | "pp" | "support" | "compact";
  context: boolean; options: string[];
  getSignal: (s: OpenDataStockSnapshot) => MetricSignal;
  getValue: (s: OpenDataStockSnapshot) => number | null;
};
const financialMetric = (key: string) => ({
  getSignal: (s: OpenDataStockSnapshot) => metricSignal(businessMetric(s, key)?.status ?? "Unknown"),
  getValue: (s: OpenDataStockSnapshot) => businessMetric(s, key)?.value ?? null,
});
export const STOCK_METRICS = [
  { key: "revenue", field: "revenue", title: "Revenue Growth YoY", shortLabel: "Revenue YoY", format: "percent", context: false,
    question: "How did quarterly sales change?", description: "Latest fiscal quarter versus the equivalent prior-year quarter. Labels describe revenue growth, not investment quality.",
    options: ["Growing", "Flat", "Declining"], ...financialMetric("revenue") },
  { key: "momentum", field: "momentum", title: "Revenue Growth Momentum", shortLabel: "Momentum", format: "pp", context: false,
    question: "Is revenue growth accelerating or decelerating?", description: REVENUE_MOMENTUM_DESCRIPTION,
    options: ["Accelerating", "Steady", "Decelerating"], ...financialMetric("momentum") },
  { key: "operating_margin", field: "operating_margin", title: "Operating Margin", shortLabel: "Operating margin", format: "percent", context: false,
    question: "What portion of quarterly sales becomes operating profit?", description: "Latest-quarter core operating income divided by revenue, with the change versus the same quarter last year when comparable.",
    options: ["Profitable", "Loss-making"], ...financialMetric("operating_margin") },
  { key: "operating_margin_trend", field: "operating_margin_trend", title: "Operating Margin Trend", shortLabel: "Margin trend", format: "pp", context: false,
    question: "How did operating profitability change year over year?", description: "Latest-quarter operating margin minus the same fiscal quarter last year, in percentage points. A positive change is Improving, zero is Stable, and a negative change is Declining.",
    options: ["Improving", "Stable", "Declining"], ...financialMetric("operating_margin_trend") },
  { key: "upcoming_earnings", field: "upcoming_earnings", title: "Upcoming Earnings", shortLabel: "Earnings", format: "days", context: true,
    question: "When is the next expected report?", description: "Source-provided earnings date or window. An expected date is an estimate unless confirmed by the issuer.",
    options: ["This week", "Next 30 days", "Later"], getSignal: (s) => upcomingEarningsSignal(upcomingEarningsMetric(s)), getValue: s => { const m = upcomingEarningsMetric(s); return upcomingEarningsSignal(m).label === "Unknown" ? null : m?.value ?? null; } },
  { key: "support", field: "support", title: "Proximity to Support", shortLabel: "Support", format: "support", context: true,
    question: "Where is the latest price relative to a detected support zone?", description: "Technical context from clustered swing lows in saved price history. It does not predict future returns.",
    options: ["Inside Support Zone", "Near Support", "Above Support"], getSignal: s => SUPPORT_TIMEFRAMES.map(t => supportMetric(s, t.field)).find(Boolean)?.signal ?? metricSignal("Unknown"), getValue: s => SUPPORT_TIMEFRAMES.map(t => supportMetric(s, t.field)).find(Boolean)?.metric.value ?? null },
] as const satisfies readonly Definition[];
export type StockMetricKey = typeof STOCK_METRICS[number]["key"];
export type StockMetricField = Exclude<typeof STOCK_METRICS[number]["field"], "support"> | SupportFilterKey;
export const STOCK_METRIC_BY_KEY = Object.fromEntries(STOCK_METRICS.map(m => [m.key, m])) as Record<StockMetricKey, typeof STOCK_METRICS[number]>;
export function stockMetricForField(field: string) { return STOCK_METRICS.find(m => m.field === (isSupportField(field) ? "support" : field)); }
