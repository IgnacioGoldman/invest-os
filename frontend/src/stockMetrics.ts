import type { OpenDataMetric, OpenDataStockSnapshot } from "./api";
import { INDUSTRY_STRENGTH_COPY, industryStrengthContext, industryStrengthSignal } from "./industryStrength";
import { fcfMarginSignal, forwardPeSignal, growthSignal, metricSignal, revenueGrowthSignal, supportSignal, type MetricSignal } from "./metricStatus";
import { calculateRevenueGrowthMomentum, REVENUE_MOMENTUM_DESCRIPTION } from "./revenueGrowthMomentum";

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
export function isSupportField(field: string): field is SupportFilterKey {
  return SUPPORT_TIMEFRAMES.some((timeframe) => timeframe.field === field);
}

export function epsGaapMetric(snapshot: OpenDataStockSnapshot) {
  return snapshot.business_health.eps_gaap_growth_yoy ?? snapshot.business_health.eps_growth_yoy;
}
export function upcomingEarningsMetric(snapshot: OpenDataStockSnapshot) {
  return snapshot.price_opportunity.days_to_next_earnings ?? snapshot.metrics.days_to_next_earnings;
}
export function upcomingEarningsSignal(metric?: OpenDataMetric): MetricSignal {
  const days = metric?.value;
  return metricSignal(days == null || !Number.isFinite(days) ? "Unclear" : days <= 7 ? "This week" : days <= 30 ? "Next 30 days" : "Later");
}
const finite = (value?: number | null) => typeof value === "number" && Number.isFinite(value) ? value : null;

const METRIC_COPY = {
  industry_strength: INDUSTRY_STRENGTH_COPY,
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


type MetricDefinition = {
  key: string;
  field: string;
  title: string;
  shortLabel: string;
  question: string;
  description: string;
  format: "percent" | "ratio" | "days" | "pp" | "support";
  options: string[];
  getSignal: (snapshot: OpenDataStockSnapshot) => MetricSignal;
  getValue: (snapshot: OpenDataStockSnapshot) => number | null;
};

// This list renders stock cards and supplies the filter menu. Adding a card here
// requires its selectable statuses and calculation, so the two cannot drift.
export const STOCK_METRICS = [
  {
    key: "revenue", field: "revenue", ...METRIC_COPY.revenue, shortLabel: "Revenue YoY", format: "percent",
    options: ["Strong", "Solid", "Flat", "Weak", "Unclear", "Unavailable"],
    getSignal: (snapshot) => revenueGrowthSignal(snapshot.business_health.revenue_growth_yoy),
    getValue: (snapshot) => finite(snapshot.business_health.revenue_growth_yoy?.value),
  },
  {
    key: "momentum", field: "momentum", ...METRIC_COPY.momentum, shortLabel: "Momentum", format: "pp",
    options: ["Accelerating", "Stable", "Decelerating", "Unclear"],
    getSignal: (snapshot) => metricSignal(calculateRevenueGrowthMomentum(snapshot).label),
    getValue: (snapshot) => calculateRevenueGrowthMomentum(snapshot).change,
  },
  {
    key: "eps_gaap", field: "eps", ...METRIC_COPY.eps_gaap, shortLabel: "GAAP EPS", format: "percent",
    options: ["Strong", "Solid", "Modest", "Weak", "Unclear", "Unavailable"],
    getSignal: (snapshot) => growthSignal(epsGaapMetric(snapshot)),
    getValue: (snapshot) => finite(epsGaapMetric(snapshot)?.value),
  },
  {
    key: "fcf_margin", field: "fcf_margin", ...METRIC_COPY.fcf_margin, shortLabel: "FCF Mgn", format: "percent",
    options: ["Strong", "Solid", "Thin", "Weak", "Unclear"],
    getSignal: (snapshot) => fcfMarginSignal(snapshot.business_health.fcf_margin?.value),
    getValue: (snapshot) => finite(snapshot.business_health.fcf_margin?.value),
  },
  {
    key: "forward_pe", field: "forward_pe", ...METRIC_COPY.forward_pe, shortLabel: "Forward P/E", format: "ratio",
    options: ["Cheap", "Fair", "Pricey", "Very pricey", "Unclear"],
    getSignal: (snapshot) => forwardPeSignal(snapshot.valuation.forward_pe),
    getValue: (snapshot) => finite(snapshot.valuation.forward_pe?.value),
  },
  {
    key: "upcoming_earnings", field: "upcoming_earnings", ...METRIC_COPY.upcoming_earnings, shortLabel: "Earnings", format: "days",
    options: ["This week", "Next 30 days", "Later", "Unclear"],
    getSignal: (snapshot) => upcomingEarningsSignal(upcomingEarningsMetric(snapshot)),
    getValue: (snapshot) => finite(upcomingEarningsMetric(snapshot)?.value),
  },
  {
    key: "support", field: "support", ...METRIC_COPY.support, shortLabel: "Support", format: "support",
    options: ["At support", "Near support", "Above support", "Far"],
    getSignal: (snapshot) => supportSignal(snapshot.price_opportunity.support_1m_distance?.value),
    getValue: (snapshot) => finite(snapshot.price_opportunity.support_1m_distance?.value),
  },
  {
    key: "industry_strength", field: "industry_strength", ...METRIC_COPY.industry_strength, shortLabel: "Industry strength", format: "pp",
    options: ["Ahead of market", "In line with market", "Behind market", "Unclear"],
    getSignal: (snapshot) => industryStrengthSignal(industryStrengthContext(snapshot)),
    getValue: (snapshot) => industryStrengthContext(snapshot)?.value ?? null,
  },
] as const satisfies readonly MetricDefinition[];

export type StockMetricKey = typeof STOCK_METRICS[number]["key"];
export type StockMetricField = Exclude<typeof STOCK_METRICS[number]["field"], "support"> | SupportFilterKey;
export const STOCK_METRIC_BY_KEY = Object.fromEntries(STOCK_METRICS.map((metric) => [metric.key, metric])) as Record<StockMetricKey, typeof STOCK_METRICS[number]>;
export function stockMetricForField(field: string) {
  return STOCK_METRICS.find((metric) => metric.field === (isSupportField(field) ? "support" : field));
}
