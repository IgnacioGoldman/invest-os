import type { OpenDataMetric, OpenDataStockSnapshot, ResearchMetric } from "./api";
import { metricSignal, supportSignal, type MetricSignal } from "./metricStatus";
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
export const DISABLED_FILTER_FIELDS = ["eps", "industry_strength", "valuation"];
export function normalizedFilterValue(field: string, value: string) {
  return field === "revenue" ? ({ Strong: "High Growth", Solid: "Moderate Growth", Weak: "Declining", Unclear: "Unknown", Unavailable: "Unknown" } as Record<string, string>)[value] ?? value
    : field === "momentum" && value === "Stable" ? "Steady" : value;
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
  const value = match && freshDay(raw.as_of) ? Math.round((Date.parse(`${match[1]}T00:00:00Z`) - Date.parse(`${new Date().toISOString().slice(0, 10)}T00:00:00Z`)) / 86400000) : null;
  return { ...raw, value: value != null && value >= 0 ? value : null };
}
export function upcomingEarningsSignal(metric?: OpenDataMetric): MetricSignal {
  const days = metric?.value;
  return metricSignal(days == null || !Number.isFinite(days) || days < 0 ? "Unknown" : days <= 7 ? "This week" : days <= 30 ? "Next 30 days" : "Later");
}
function freshDay(value?: string | null) {
  const age = (Date.now() - Date.parse(`${value?.slice(0, 10)}T00:00:00Z`)) / 86400000;
  return age >= 0 && age < 8;
}
export function researchMetric(snapshot: OpenDataStockSnapshot, key: string): ResearchMetric | undefined {
  const metric = snapshot.screening?.metrics[key];
  if (key === "forward_pe" && metric && (!freshDay(metric.estimate_as_of) || !freshDay(metric.price_as_of))) {
    return { ...metric, value: null, status: "Unknown", warnings: [...metric.warnings, "The estimate or market price is stale."] };
  }
  return metric;
}
export function financialDetail(snapshot: OpenDataStockSnapshot, key: string): ResearchMetric | undefined {
  const metric = snapshot.screening?.financial_details[key];
  return metric && key !== "gross_margin" && !freshDay(snapshot.price_opportunity.current_price?.as_of)
    ? { ...metric, value: null, status: "Unknown", warnings: [...metric.warnings, "The market price is stale."] } : metric;
}
export function metricEvidence(metric?: ResearchMetric, includeWarnings = true): string {
  if (!metric) return "Unknown: comparable financial inputs are unavailable.";
  return [metric.kind, metric.period, metric.currency, `As of ${metric.as_of || "Unknown"}`, metric.estimate_as_of ? `Estimate dated ${metric.estimate_as_of}` : "", metric.formula, metric.notes, `Source: ${metric.source}`, ...(includeWarnings ? metric.warnings : [])].filter(Boolean).join(" · ");
}
type Definition = {
  key: string; field: string; title: string; shortLabel: string; question: string; description: string;
  format: "percent" | "ratio" | "days" | "pp" | "support" | "compact";
  context: boolean; options: string[];
  getSignal: (s: OpenDataStockSnapshot) => MetricSignal;
  getValue: (s: OpenDataStockSnapshot) => number | null;
};
const financialMetric = (key: string) => ({
  getSignal: (s: OpenDataStockSnapshot) => metricSignal(researchMetric(s, key)?.status ?? "Unknown"),
  getValue: (s: OpenDataStockSnapshot) => researchMetric(s, key)?.value ?? null,
});
export const STOCK_METRICS = [
  { key: "revenue", field: "revenue", title: "Revenue Growth YoY", shortLabel: "Revenue YoY", format: "percent", context: false,
    question: "How did quarterly sales change?", description: "Latest fiscal quarter versus the equivalent prior-year quarter. Labels describe revenue growth, not investment quality.",
    options: ["High Growth", "Moderate Growth", "Flat", "Declining", "Unknown", "Needs Review"], ...financialMetric("revenue") },
  { key: "momentum", field: "momentum", title: "Revenue Growth Momentum", shortLabel: "Momentum", format: "pp", context: false,
    question: "Is revenue growth accelerating or decelerating?", description: REVENUE_MOMENTUM_DESCRIPTION,
    options: ["Accelerating", "Steady", "Decelerating", "Unknown", "Needs Review"], ...financialMetric("momentum") },
  { key: "operating_margin", field: "operating_margin", title: "Operating Margin", shortLabel: "Operating margin", format: "percent", context: false,
    question: "What portion of quarterly sales becomes operating profit?", description: "Latest-quarter core operating income divided by revenue, with the change versus the same quarter last year when comparable.",
    options: ["Computed Metric", "Unknown", "Needs Review"], ...financialMetric("operating_margin") },
  { key: "fcf_margin", field: "fcf_margin", title: "Free Cash Flow Margin", shortLabel: "FCF margin", format: "percent", context: false,
    question: "How much revenue became free cash flow over twelve months?", description: "TTM operating cash flow minus capex, divided by TTM revenue. Recent-quarter cash flow and deterioration warnings are separate context.",
    options: ["Computed Metric", "Unknown", "Needs Review"], ...financialMetric("fcf_margin") },
  { key: "forward_pe", field: "forward_pe", title: "Forward P/E", shortLabel: "Forward P/E", format: "ratio", context: false,
    question: "What multiple of estimated earnings does the price represent?", description: "Estimate only: requires positive, sourced annual forward EPS with an identifiable forecast horizon, estimate date and compatible currency. Historical EPS extrapolations are excluded.",
    options: ["Estimate", "Unknown", "Needs Review"], ...financialMetric("forward_pe") },
  { key: "balance_sheet", field: "balance_sheet", title: "Balance Sheet", shortLabel: "Net cash/debt", format: "compact", context: false,
    question: "What are the reported cash, investments and debt?", description: "Net cash/debt uses only compatible unrestricted cash equivalents and complete debt. Investments are disclosed separately and excluded from net cash.",
    options: ["Computed Metric", "Unknown", "Needs Review"], ...financialMetric("balance_sheet") },
  { key: "upcoming_earnings", field: "upcoming_earnings", title: "Upcoming Earnings", shortLabel: "Earnings", format: "days", context: true,
    question: "When is the next expected report?", description: "Source-provided earnings date or window. An expected date is an estimate unless confirmed by the issuer.",
    options: ["This week", "Next 30 days", "Later", "Unknown"], getSignal: (s) => upcomingEarningsSignal(upcomingEarningsMetric(s)), getValue: s => { const m = upcomingEarningsMetric(s); return upcomingEarningsSignal(m).label === "Unknown" ? null : m?.value ?? null; } },
  { key: "support", field: "support", title: "Proximity to Support", shortLabel: "Support", format: "support", context: true,
    question: "Where is the latest price relative to a detected support zone?", description: "Technical context from clustered swing lows in saved price history. It does not predict future returns.",
    options: ["Inside Support Zone", "Near Support", "Above Support", "Unknown"], getSignal: s => supportSignal(s.price_opportunity.support_1m_distance?.value), getValue: s => s.price_opportunity.support_1m_distance?.value ?? null },
] as const satisfies readonly Definition[];
export type StockMetricKey = typeof STOCK_METRICS[number]["key"];
export type StockMetricField = Exclude<typeof STOCK_METRICS[number]["field"], "support"> | SupportFilterKey;
export const STOCK_METRIC_BY_KEY = Object.fromEntries(STOCK_METRICS.map(m => [m.key, m])) as Record<StockMetricKey, typeof STOCK_METRICS[number]>;
export function stockMetricForField(field: string) { return STOCK_METRICS.find(m => m.field === (isSupportField(field) ? "support" : field)); }
