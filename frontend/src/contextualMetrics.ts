import type { OpenDataMetric, OpenDataStockSnapshot, ResearchMetric } from "./api";
import { industryStrengthContext } from "./industryStrength";
import { researchMetric } from "./stockMetrics";

// These definitions intentionally have no status, tag, threshold or filter options.
export type ContextualMetricDefinition = {
  key: string;
  title: string;
  question: string;
  description: string;
  formula: string;
  interpretation: string;
  format: "percent" | "ratio" | "compact" | "pp";
  projection?: "metrics" | "financial_details";
  rawKey?: string;
  historyKey?: string;
  historySeries?: string;
  historyTitle?: string;
};

export const CONTEXTUAL_METRICS: ContextualMetricDefinition[] = [
  { key: "fcf_margin", title: "Free Cash Flow Margin", format: "percent", projection: "metrics",
    question: "How much of the company's sales remains as free cash flow?",
    description: "Measures the share of trailing twelve-month revenue left after operating cash flow pays for capital expenditure. Cash flow can vary with working capital, investment timing and the business model.",
    formula: "(TTM operating cash flow − abs(TTM capex)) / TTM revenue × 100",
    interpretation: "A positive TTM margin can conceal negative recent cash flow. Review working capital, stock compensation and reinvestment needs. Financial businesses are not comparable.",
    historyKey: "fcf_margin", historySeries: "quarterly_fundamentals", historyTitle: "Quarterly Free Cash Flow Margin (separate from TTM)" },
  { key: "forward_pe", title: "Forward P/E", format: "ratio", projection: "metrics",
    question: "How much does the share price imply for each unit of forecast earnings?",
    description: "Divides the current listing share price by a sourced annual forward EPS estimate. The estimate's horizon, date and accounting adjustments affect the comparison.",
    formula: "current listing share price / positive annual forward EPS estimate",
    interpretation: "A Forward P/E of 40 does not automatically mean expensive, and 10 does not automatically mean cheap. Growth expectations, risk and forecast reliability matter. A sourced forecast horizon and matching currency are required; quote and estimate must be no older than seven days. Historical EPS extrapolation is excluded." },
  { key: "balance_sheet", title: "Balance Sheet / Net Cash", format: "compact", projection: "metrics",
    question: "How do the company's cash holdings compare with its debt?",
    description: "Shows cash and cash equivalents, investments and debt separately. Net cash uses unrestricted cash equivalents less complete debt at the same reporting date and in the same currency.",
    formula: "cash and cash equivalents − complete debt; investments excluded",
    interpretation: "Cash restrictions, investment liquidity, leases and borrowing scope require review. Missing components are never zero. Partial debt cannot establish net cash; investments do not automatically count as liquid cash." },
  { key: "gross_margin", title: "Gross Margin", format: "percent", projection: "financial_details",
    question: "How much revenue remains after the direct cost of sales?",
    description: "Measures quarterly gross profit as a percentage of revenue. It helps explain production and service costs before operating expenses.",
    formula: "quarterly gross profit / same-quarter revenue × 100",
    interpretation: "Business models, cost classifications and capital intensity differ. A margin level alone does not establish profitability or business quality.",
    historyKey: "gross_margin", historySeries: "quarterly_fundamentals" },
  { key: "price_to_sales", title: "Price / Sales", format: "ratio", projection: "financial_details",
    question: "How much market value is assigned to each unit of sales?",
    description: "Compares current market capitalization with compatible trailing twelve-month revenue. Sales do not account for costs or reinvestment.",
    formula: "current market capitalization / compatible TTM revenue",
    interpretation: "Margins, growth, dilution and capital intensity affect interpretation. Require aligned reporting currency and a fresh market quote. Historical points use annual sales and year-end market capitalization.",
    historyKey: "price_to_sales", historySeries: "valuation_history", historyTitle: "Annual Price / Sales (year-end basis)" },
  { key: "fcf_yield", title: "Free Cash Flow Yield", format: "percent", projection: "financial_details",
    question: "How much free cash flow does the business generate relative to its market value?",
    description: "Expresses compatible trailing twelve-month free cash flow as a percentage of current market capitalization.",
    formula: "compatible TTM free cash flow / current market capitalization × 100",
    interpretation: "Working capital, capex timing and share-count estimates can distort the yield. Financial businesses are not comparable. Historical points use annual cash flow and year-end market capitalization.",
    historyKey: "fcf_yield", historySeries: "valuation_history", historyTitle: "Annual Free Cash Flow Yield (year-end basis)" },
  { key: "eps_gaap_growth_yoy", title: "GAAP EPS Growth YoY", format: "percent", rawKey: "eps_gaap_growth_yoy",
    question: "How have reported earnings per share changed from a year ago?",
    description: "Compares GAAP diluted EPS in the latest quarter with the same fiscal quarter one year earlier, requiring positive comparable endpoints.",
    formula: "(latest-quarter diluted EPS / same-quarter prior-year diluted EPS − 1) × 100",
    interpretation: "Investment gains, tax benefits, buybacks and a small earnings base can dominate this rate. Review unusual items alongside operating performance." },
  { key: "eps_cagr_3y", title: "EPS CAGR 3Y", format: "percent", rawKey: "eps_cagr_3y",
    question: "How quickly have reported earnings per share grown over three years?",
    description: "Expresses the change between comparable positive EPS endpoints three years apart as an annual compound growth rate.",
    formula: "((latest EPS / EPS three years earlier) ** (1/3) − 1) × 100",
    interpretation: "Exceptional endpoint gains, losses, cyclicality and share-count changes can dominate the result. Historical growth is not a forecast." },
  { key: "net_margin", title: "Net Margin", format: "percent", rawKey: "net_margin",
    question: "What share of revenue becomes reported net income?",
    description: "Measures quarterly GAAP net income as a percentage of quarterly revenue, including non-operating items and taxes.",
    formula: "quarterly GAAP net income / same-quarter revenue × 100",
    interpretation: "Investment gains, tax effects and other unusual items can overwhelm core profitability. Compare net income with operating income and reconcile exceptional items.",
    historyKey: "net_margin", historySeries: "quarterly_fundamentals" },
  { key: "roe", title: "ROE (annualized quarterly)", format: "percent", rawKey: "roe",
    question: "How does reported profit compare with shareholder equity?",
    description: "The saved quarterly calculation annualizes one quarter of net income against quarter-end equity. It differs from a return measured using annual earnings and average equity.",
    formula: "quarterly net income × 4 / quarter-end shareholder equity × 100",
    interpretation: "Unusual gains, buybacks and small or negative equity can inflate or invert returns. Compare earnings quality, average equity and sector-specific accounting.",
    historyKey: "roe", historySeries: "quarterly_fundamentals" },
  { key: "roic", title: "ROIC Proxy", format: "percent", rawKey: "roic",
    question: "How does operating profit compare with the capital invested in the business?",
    description: "The saved proxy annualizes quarterly operating income against quarter-end debt plus equity less cash. It does not apply a NOPAT tax adjustment.",
    formula: "quarterly operating income × 4 / (debt + equity − cash) × 100",
    interpretation: "This proxy differs from standard ROIC. Debt scope, leases, cash treatment and near-zero or negative invested capital limit comparability.",
    historyKey: "roic", historySeries: "quarterly_fundamentals" },
  { key: "peg", title: "PEG (historical growth proxy)", format: "ratio", rawKey: "peg_proxy",
    question: "How does trailing P/E compare with historical EPS growth?",
    description: "Divides trailing GAAP P/E by historical three-year EPS CAGR expressed as a percentage number. It uses historical growth rather than a forward forecast.",
    formula: "trailing P/E / historical three-year EPS CAGR (%)",
    interpretation: "Distorted GAAP earnings affect both parts of this ratio. A low result does not establish cheapness, and historical growth may not persist." },
  { key: "pe", title: "Trailing GAAP P/E", format: "ratio", rawKey: "pe_ttm",
    question: "How much market value is assigned to each unit of reported earnings?",
    description: "Compares current market capitalization with positive trailing twelve-month GAAP net income, using compatible listing currency.",
    formula: "current market capitalization / positive TTM GAAP net income",
    interpretation: "Exceptional or cyclically inflated earnings can make the multiple look low. Negative or tiny earnings defeat ordinary comparisons. Historical points use annual earnings and year-end market capitalization.",
    historyKey: "pe", historySeries: "valuation_history", historyTitle: "Annual GAAP P/E (year-end basis)" },
  { key: "ev_to_ebitda", title: "EV / EBITDA Proxy", format: "ratio", rawKey: "ev_to_ebitda_proxy",
    question: "How does enterprise value compare with an estimate of operating cash earnings?",
    description: "Compares market capitalization plus debt less cash with operating income plus depreciation and amortization.",
    formula: "(market capitalization + debt − cash) / (operating income + depreciation/amortization)",
    interpretation: "Approximate EBITDA, incomplete debt, cash definitions, leases and mixed periods limit comparison. This proxy is especially unsuitable for financial businesses. Historical points use annual EBITDA and year-end enterprise value.",
    historyKey: "ev_to_ebitda", historySeries: "valuation_history", historyTitle: "Annual EV / EBITDA Proxy (year-end basis)" },
  { key: "industry_strength", title: "Industry Relative Strength", format: "pp",
    question: "How has the stock's industry performed compared with the wider market?",
    description: "Compares the equal-weight one-year price return of tracked industry peers with the broad-market benchmark, excluding the selected stock from the peer basket.",
    formula: "equal-weight tracked peer 1Y price return − market benchmark 1Y price return, pp",
    interpretation: "Sparse peers, a selected universe, classification differences and date or currency gaps can distort the comparison. Review both absolute returns; relative performance can be positive while prices fall.",
    historyTitle: "Tracked industry minus market (pp since comparison start)" },
];

export const CONTEXTUAL_METRIC_BY_KEY = Object.fromEntries(CONTEXTUAL_METRICS.map(metric => [metric.key, metric]));

export function contextualMetric(snapshot: OpenDataStockSnapshot, definition: ContextualMetricDefinition): OpenDataMetric | ResearchMetric | undefined {
  if (definition.key === "industry_strength") {
    const context = industryStrengthContext(snapshot);
    return context ? { value: context.value, as_of: context.end_date ?? "", source: context.source,
      tier: "computed_from_public_facts", period: `${context.start_date} to ${context.end_date}`,
      notes: [context.reason, `${context.peer_count} of ${context.tracked_peer_count} tracked peers`,
        `Industry return ${context.industry_return ?? "unavailable"}%; market return ${context.market_return ?? "unavailable"}%`].filter(Boolean).join(" · ") } : undefined;
  }
  // Never fall back from a rejected projection to a less reliable raw ratio.
  if (definition.projection === "metrics") return researchMetric(snapshot, definition.key);
  if (definition.projection === "financial_details") return snapshot.screening?.financial_details?.[definition.key];
  return snapshot.metrics[definition.rawKey ?? definition.key];
}

export function contextualValue(metric?: OpenDataMetric): number | null {
  return typeof metric?.value === "number" && Number.isFinite(metric.value) ? metric.value : null;
}

export function formatContextualValue(value: number | null, definition: Pick<ContextualMetricDefinition, "format">, currency?: string | null): string {
  if (value == null) return "—";
  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2,
    ...(definition.format === "compact" ? { notation: "compact" as const } : {}) }).format(value);
  return definition.format === "percent" ? `${number}%` : definition.format === "ratio" ? `${number}×`
    : definition.format === "pp" ? `${number} pp` : [currency, number].filter(Boolean).join(" ");
}

export function contextualHistory(snapshot: OpenDataStockSnapshot, definition: ContextualMetricDefinition): Array<{ period: string; value: number }> {
  if (definition.key === "industry_strength") return (industryStrengthContext(snapshot)?.chart ?? [])
    .filter(point => Number.isFinite(point.industry) && Number.isFinite(point.market))
    .map(point => ({ period: point.date, value: point.industry - point.market }));
  if (["eps_gaap_growth_yoy", "eps_cagr_3y"].includes(definition.key)) {
    const rows = snapshot.historical_series.quarterly_fundamentals ?? [];
    const years = definition.key === "eps_cagr_3y" ? 3 : 1;
    return [...rows].sort((a, b) => a.as_of.localeCompare(b.as_of)).flatMap(row => {
      const match = /^FY(\d{4}) Q([1-4])$/.exec(row.period);
      const previous = match ? rows.filter(candidate => candidate.period === `FY${Number(match[1]) - years} Q${match[2]}`) : [];
      const currentEPS = row.metrics.eps_diluted;
      const priorEPS = previous.length === 1 ? previous[0].metrics.eps_diluted : undefined;
      const current = contextualValue(currentEPS), prior = contextualValue(priorEPS);
      const unit = (metric?: OpenDataMetric) => metric?.currency ?? /:([A-Z]{3})\/shares:/.exec(metric?.source ?? "")?.[1];
      const gap = previous.length === 1 ? (Date.parse(row.as_of) - Date.parse(previous[0].as_of)) / 86400000 : NaN;
      if (current == null || prior == null || current <= 0 || prior <= 0 || !unit(currentEPS)
          || unit(currentEPS) !== unit(priorEPS) || Math.abs(gap - years * 365.25) > 16) return [];
      const value = ((current / prior) ** (1 / years) - 1) * 100;
      return Number.isFinite(value) ? [{ period: row.period, value }] : [];
    });
  }
  if (!definition.historySeries || !definition.historyKey) return [];
  return [...(snapshot.historical_series[definition.historySeries] ?? [])]
    .sort((a, b) => a.as_of.localeCompare(b.as_of))
    .flatMap(row => {
      const value = contextualValue(row.metrics[definition.historyKey!]);
      return value == null ? [] : [{ period: row.period, value }];
    });
}
