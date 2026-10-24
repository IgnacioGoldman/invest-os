import type { OpenDataStockSnapshot } from "./api";
import { researchMetric } from "./stockMetrics";
import stockAnalysisTemplate from "./prompts/stock-analysis.md?raw";

export type StockAnalysisBrief = {
  tickers: string[];
  preview: string;
  prompt: string;
};

function latestRows(snapshot: OpenDataStockSnapshot, series: string, count: number) {
  return [...(snapshot.historical_series[series] ?? [])]
    .sort((a, b) => a.as_of.localeCompare(b.as_of) || a.period.localeCompare(b.period, undefined, { numeric: true }))
    .slice(-count);
}

export function prepareStockAnalysis(snapshots: OpenDataStockSnapshot[], filterName: string): StockAnalysisBrief {
  const tickers = snapshots.map((snapshot) => snapshot.ticker);
  const subject = tickers.length > 1 ? `Compare ${tickers.join(", ")} as potential investments.` : `Evaluate ${tickers[0]} as a potential investment.`;
  const preview = `${subject} Use the financial data from Invest OS: revenue growth, valuation, profitability and support levels. Compare business quality, opportunities and risks. Explain which deserves further research and why.`;
  const variables: Record<string, string> = { subject, preparedAt: new Date().toISOString(), filterName };
  const instructions = stockAnalysisTemplate.trimEnd().replace(
    /\{\{(subject|preparedAt|filterName)\}\}/g,
    (_placeholder, key: string) => variables[key],
  );
  const lines = [instructions, ""];
  for (const snapshot of snapshots) {
    const context = snapshot.company_context;

    lines.push(
      `### ${snapshot.ticker} — ${snapshot.name ?? snapshot.ticker}`,
      "",
      "```json",
      JSON.stringify({
        ticker: snapshot.ticker,
        company: snapshot.name,
        exchange: snapshot.exchange,
        country: snapshot.country,
        sector: snapshot.sector,
        industry: snapshot.industry,
        dataset_source: snapshot.source,
        dataset_generated_at: snapshot.generated_at,
        business_health: snapshot.business_health,
        valuation: snapshot.valuation,
        price_and_support: snapshot.price_opportunity,
        revenue_growth_momentum: researchMetric(snapshot, "momentum"),
        screening_metrics: { ...snapshot.screening, metrics: { ...snapshot.screening?.metrics, forward_pe: researchMetric(snapshot, "forward_pe") } },
        raw_financial_metrics: snapshot.metrics,
        raw_valuation_inputs: snapshot.valuation_inputs,
        recent_quarterly_revenue: latestRows(snapshot, "quarterly_revenue", 10),
        latest_quarterly_fundamentals: latestRows(snapshot, "quarterly_fundamentals", 8),
        recent_annual_fundamentals: latestRows(snapshot, "annual_fundamentals", 2),
        data_gaps: snapshot.data_gaps,
        company_context: context ? { ...context, recent_filings: context.recent_filings.slice(0, 3) } : null,
      }, null, 2),
      "```",
      "",
    );
  }
  return { tickers, preview, prompt: lines.join("\n") };
}
