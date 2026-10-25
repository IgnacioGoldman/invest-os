import type { OpenDataStockSnapshot } from "./api";
import { compactAnalysisStock } from "./aiBriefData";
import stockAnalysisTemplate from "./prompts/stock-analysis.md?raw";

// Keep pasted research briefs small enough to leave room for the AI's comparison.
export const MAX_ANALYSIS_STOCKS = 3;

export type StockAnalysisBrief = {
  tickers: string[];
  preview: string;
  prompt: string;
};

export function prepareStockAnalysis(snapshots: OpenDataStockSnapshot[], filterName: string): StockAnalysisBrief {
  snapshots = snapshots.slice(0, MAX_ANALYSIS_STOCKS);
  const tickers = snapshots.map((snapshot) => snapshot.ticker);
  const subject = tickers.length > 1 ? `Compare ${tickers.join(", ")} as potential investments.` : `Evaluate ${tickers[0]} as a potential investment.`;
  const preview = `${subject} Assess each stock independently using descriptive tags only: Strong, Solid, Average, Weak or Poor for business quality; Cheap, Fair or Expensive for valuation; Unknown when evidence is insufficient. Then compare and rank all selected stocks, giving equal importance to business quality and valuation, and create one table with Rank, Stock, Business quality, Valuation and Rationale. Use the supplied data as a starting point, supplement it with research when available, and explain the investment case and key risks.`;
  const variables: Record<string, string> = { subject, preparedAt: new Date().toISOString(), filterName };
  const instructions = stockAnalysisTemplate.trimEnd().replace(
    /\{\{(subject|preparedAt|filterName)\}\}/g,
    (_placeholder, key: string) => variables[key],
  );
  const lines = [instructions, "",
    "Compact data key: v=value (rounded to 7 significant digits); t=r reported, c computed, p proxy/estimate; s=1-based references to that stock's sources list; d=as-of date, otherwise financial_as_of (or the history row's as_of); ccy overrides the stock's financial currency. Monetary amounts and share counts are in millions; prices (including support zones) and EPS are per share. Market prices/support use market.currency. Percentages, percentage points and valuation ratios are unscaled. Missing/omitted values are unknown, never zero. Quarterly and annual histories remain separate. Red-flag values use the same units; an incomplete count is null and observed_count is only a lower bound. Filing links are metadata, not proof their contents were reviewed.", ""];
  for (const snapshot of snapshots) {
    lines.push(
      `### ${snapshot.ticker} — ${snapshot.name ?? snapshot.ticker}`,
      "",
      "```json",
      JSON.stringify(compactAnalysisStock(snapshot)),
      "```",
      "",
    );
  }
  return { tickers, preview, prompt: lines.join("\n") };
}
