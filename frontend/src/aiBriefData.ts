import type { OpenDataMetric, OpenDataStockSnapshot, ResearchMetric } from "./api";
import { researchMetric, supportMetric, SUPPORT_TIMEFRAMES, upcomingEarningsMetric } from "./stockMetrics";

type Kind = "money" | "shares" | "percent" | "ratio" | "price";
type BriefFact = { v: number; t: string; s: number[]; d?: string; ccy?: string | null; period?: string | null; caution?: string };
const monetary = new Set(["revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "equity"]);
const historicalKeys = [...monetary, "shares_diluted", "eps_diluted"];
const tiers: Record<string, string> = { exact_public_fact: "r", computed_from_public_facts: "c", proxy_estimate: "p" };
function currency(metric?: OpenDataMetric): string | null {
  const codes = new Set([...(metric?.source ?? "").matchAll(/:([A-Z]{3})(?:\/shares)?:/g)].map(m => m[1]));
  return metric?.currency ?? (codes.size === 1 ? [...codes][0] : null);
}
function round(value: number, kind: Kind) {
  const scaled = kind === "money" || kind === "shares" ? value / 1e6 : value;
  return Number(scaled.toPrecision(7));
}

/** A copy-only projection. The stored snapshot and full research data stay intact. */
export function compactAnalysisStock(snapshot: OpenDataStockSnapshot) {
  const raw = snapshot.metrics;
  const quarterRows = [...(snapshot.historical_series.quarterly_fundamentals ?? [])].sort((a, b) => a.as_of.localeCompare(b.as_of));
  const latestQuarter = quarterRows[quarterRows.length - 1];
  const financialDate = raw.revenue_ttm?.as_of ?? latestQuarter?.as_of ?? "";
  const financialCurrency = currency(raw.revenue_ttm);
  const sources: string[] = [];
  const sourceIds = (source?: string): number[] => [...new Set((source ?? "").split(/;\s*/).filter(Boolean).map(source => {
    let index = sources.indexOf(source);
    if (index < 0) { index = sources.length; sources.push(source); }
    return index + 1;
  }))];
  const warnings = new Set(snapshot.screening?.warnings ?? []);
  const missing: string[] = [];
  const facts: Record<string, BriefFact> = {};
  function fact(metric: OpenDataMetric | undefined, kind: Kind, defaultDate = financialDate, declaredCurrency?: string | null): BriefFact | undefined {
    if (typeof metric?.value !== "number" || !Number.isFinite(metric.value) || !tiers[metric.tier]) return undefined;
    const ccy = declaredCurrency ?? currency(metric);
    return { v: round(metric.value, kind), t: tiers[metric.tier], s: sourceIds(metric.source),
      ...(metric.as_of !== defaultDate ? { d: metric.as_of } : {}),
      ...((kind === "money" || kind === "price") && ccy !== financialCurrency ? { ccy } : {}),
      ...(metric.period ? { period: metric.period } : defaultDate === financialDate && /latest.quarter|quarterly/i.test(metric.notes ?? "")
        && metric.as_of === latestQuarter?.as_of ? { period: latestQuarter.period } : {}),
      ...((metric.tier === "proxy_estimate" || kind === "shares" && metric.tier !== "exact_public_fact"
        || /proxy|not meaningful|negative|incomplete|restricted|mismatch|currency|converted|\bfx\b|split|restat/i.test(metric.notes ?? "")) && metric.notes ? { caution: metric.notes } : {}) };
  }
  function add(key: string, metric: OpenDataMetric | undefined, kind: Kind, declaredCurrency?: string | null) {
    const compact = fact(metric, kind, financialDate, declaredCurrency);
    if (compact) facts[key] = compact;
    else missing.push(key);
    for (const warning of (metric as ResearchMetric | undefined)?.warnings ?? []) warnings.add(warning);
  }
  for (const [field, name] of [["revenue", "revenue_growth_yoy_pct"], ["momentum", "revenue_momentum_pp"],
    ["operating_margin", "operating_margin_pct"], ["operating_margin_trend", "operating_margin_trend_pp"]]) {
    const m = researchMetric(snapshot, field);
    const fallback = field === "revenue" ? raw.revenue_growth_yoy : field === "operating_margin" ? raw.operating_margin : undefined;
    add(name, m?.validated ? m : fallback, "percent");
  }
  for (const key of ["revenue_ttm", "operating_income_ttm", "net_income_ttm", "operating_cash_flow_ttm", "capex_ttm", "free_cash_flow_ttm", "cash", "debt", "equity", "market_cap"])
    add(key, raw[key] ?? snapshot.business_health[key] ?? (key === "equity" ? latestQuarter?.metrics.equity : undefined), "money", key === "market_cap" ? snapshot.price_currency : undefined);
  add("shares_diluted_m", raw.shares_diluted, "shares");
  for (const key of ["gross_margin", "net_margin", "revenue_cagr_3y", "eps_gaap_growth_yoy", "eps_cagr_3y", "roe", "roic", "fcf_margin_ttm"])
    add(key, raw[key], "percent");
  for (const key of ["debt_to_equity", "peg", "ev_to_ebitda_proxy"]) add(key, raw[key], "ratio");
  for (const key of ["gross_profit_ttm", "ebitda_proxy", "enterprise_value_proxy"]) add(key, raw[key], "money");
  const pe = raw.pe_ttm ?? snapshot.valuation.pe;
  if (pe?.value != null && pe.value <= 0) {
    missing.push("pe_ttm"); warnings.add("Trailing P/E is not meaningful with non-positive earnings.");
  } else add("pe_ttm", pe, "ratio");
  add("forward_pe", researchMetric(snapshot, "forward_pe"), "ratio");
  add("price_to_sales", snapshot.screening?.financial_details?.price_to_sales ?? snapshot.valuation.price_to_sales, "ratio");
  add("fcf_yield_pct", snapshot.screening?.financial_details?.fcf_yield ?? snapshot.valuation.fcf_yield, "percent");
  for (const key of ["fcf_margin", "balance_sheet"]) for (const warning of researchMetric(snapshot, key)?.warnings ?? []) warnings.add(warning);

  function recent(series: string, count: number) {
    return [...(snapshot.historical_series[series] ?? [])].sort((a, b) => a.as_of.localeCompare(b.as_of)).slice(-count);
  }
  function history(series: string, count: number, keys: string[]) {
    return recent(series, count).map(row => ({ period: row.period, as_of: row.as_of,
      values: Object.fromEntries(keys.flatMap(key => {
        const value = fact(row.metrics[key], key === "shares_diluted" ? "shares" : key === "eps_diluted" ? "price" : key === "revenue_growth_yoy" ? "percent" : "money", row.as_of);
        return value ? [[key, value]] : [];
      })) }));
  }
  const revenueHistory = history("quarterly_revenue", 10, ["revenue", "revenue_growth_yoy"]);
  const quarterly = history("quarterly_fundamentals", 8, historicalKeys);
  const annual = history("annual_fundamentals", 2, historicalKeys);
  const risk = researchMetric(snapshot, "red_flag_count");
  function scaledEvidence(value: unknown, key = ""): unknown {
    if (typeof value === "number") return round(value, monetary.has(key) ? "money" : "percent");
    if (Array.isArray(value)) return value.map(item => scaledEvidence(item));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, v]) => [key, scaledEvidence(v, key)]));
    return value;
  }
  const redFlags = risk ? { count: risk.value ?? null, observed_count: risk.observed_count, max: risk.max_count,
    as_of: risk.as_of, valid_until: risk.valid_until, coverage: risk.coverage,
    detected: (risk.flags ?? []).map(group => ({ group: group.title, rules: group.checks.filter(check => check.state === "flagged").map(check => ({
      rule: check.title, calculation: check.formula, values: scaledEvidence(check.values),
      ...(check.evidence.some(e => e.currency !== financialCurrency) ? { ccy: check.evidence[0]?.currency ?? null } : {}),
      s: [...new Set(check.evidence.flatMap(input => sourceIds(input.source)))],
    })) })),
    unassessed: (risk.checks ?? []).filter(group => group.state === "unassessed" || group.state === "not_applicable")
      .map(group => ({ group: group.title, reason: group.reason ?? "Insufficient comparable inputs." })),
  } : { count: null, coverage: null };
  const supports = SUPPORT_TIMEFRAMES.flatMap(timeframe => {
    const support = supportMetric(snapshot, timeframe.field);
    if (!support) return [];
    const bounds = /Support zone: \$?([\d,.]+)-\$?([\d,.]+)/.exec(support.metric.notes ?? "");
    return [{ timeframe: timeframe.label, distance_pct: round(support.metric.value!, "percent"),
      zone: bounds?.slice(1).map(v => Number(v.replace(/,/g, ""))), as_of: support.metric.as_of, s: sourceIds(support.metric.source) }];
  });
  const earnings = upcomingEarningsMetric(snapshot);
  const price = snapshot.price_opportunity.current_price;
  const market = { price: fact(price, "price", financialDate, snapshot.price_currency), currency: snapshot.price_currency ?? null, supports,
    return_1y_pct: fact(snapshot.price_opportunity.change_1y, "percent"),
    from_52w_high_pct: fact(snapshot.price_opportunity.distance_from_52w_high, "percent"),
    ...(earnings?.value != null ? { earnings: { date: earnings.period, estimated: earnings.tier === "proxy_estimate", s: sourceIds(earnings.source) } } : {}) };
  // Keep listing-currency denominators only when they add information beyond
  // the financial-statement currency, rather than duplicating every raw input.
  const valuationBasis = snapshot.price_currency && financialCurrency && snapshot.price_currency !== financialCurrency ? Object.fromEntries(
    ["revenue", "net_income", "free_cash_flow"].flatMap(key => {
      const value = fact(snapshot.valuation_inputs?.[key], "money", financialDate, snapshot.price_currency);
      return value ? [[key, value]] : [];
    })) : undefined;
  return { ticker: snapshot.ticker, company: snapshot.name, sector: snapshot.sector, industry: snapshot.industry,
    snapshot_as_of: snapshot.generated_at, financial_as_of: financialDate, currency: financialCurrency,
    metrics: facts, missing_metrics: missing, market, red_flags: redFlags,
    revenue_quarters: revenueHistory, quarters: quarterly, annual,
    ...(valuationBasis && Object.keys(valuationBasis).length ? { valuation_basis: valuationBasis } : {}),
    warnings: [...warnings], data_gaps: snapshot.data_gaps,
    filings: snapshot.company_context?.recent_filings.slice(0, 3).map(filing => ({ form: filing.form, date: filing.filing_date,
      report_date: filing.report_date, items: filing.items, url: filing.source_url })), sources };
}
