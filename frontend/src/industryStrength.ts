import type { OpenDataStockSnapshot } from "./api";
import type { MetricSignal } from "./metricStatus";

export type IndustryStrength = {
  period: "1Y";
  value: number | null;
  label: string;
  reason: string | null;
  sector: string | null;
  industry: string | null;
  original_sector: string | null;
  original_industry: string | null;
  classification_source: string;
  classification_reviewed_at: string;
  classification_sources: string[];
  benchmark: { symbol: string; name: string; source_url: string; currency: string; market: string };
  start_date: string | null;
  end_date: string | null;
  generated_at: string;
  industry_return: number | null;
  market_return: number | null;
  stock_return: number | null;
  stock_vs_industry: number | null;
  peer_count: number;
  tracked_peer_count: number;
  peers: Array<{ ticker: string; name: string | null; return_pct: number }>;
  excluded_peers: Array<{ ticker: string; reason: string }>;
  chart: Array<{ date: string; stock: number; industry: number; market: number }>;
  source: string;
  tier: string;
};

export const INDUSTRY_STRENGTH_COPY = {
  title: "Industry Relative Strength",
  question: "How has the stock's industry performed compared with the wider market?",
  description: "Compares the equal-weight 1-year price return of tracked industry peers with the S&P 500. The selected stock is excluded from the peer average. A positive difference means the industry is ahead of the market; a negative difference means it is behind. This describes price context, not whether the stock or industry is cheap, expensive, or a good investment.",
};

export function industryStrengthContext(snapshot: OpenDataStockSnapshot): IndustryStrength | null {
  const result = snapshot.industry_relative_strength;
  if (!result) return null;
  if (result.value == null) return result;
  const currentDate = snapshot.price_opportunity.current_price?.as_of?.slice(0, 10);
  const age = result.end_date ? (Date.now() - Date.parse(`${result.end_date}T00:00:00Z`)) / 86400000 : Infinity;
  if (!Number.isFinite(result.value) || currentDate !== result.end_date || age >= 8 || age < 0) {
    return { ...result, value: null, label: "Unclear", chart: [],
      reason: "This industry comparison needs to be rebuilt from fresh, matching price dates." };
  }
  return result;
}

export function industryStrengthSignal(context: IndustryStrength | null): MetricSignal {
  const value = context?.value;
  return {
    label: value == null ? "Unclear" : value >= 5 ? "Ahead of market" : value <= -5 ? "Behind market" : "In line with market",
    tone: "neutral",
    detail: context?.reason ?? undefined,
  };
}
