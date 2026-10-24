export type SimulationPosition = {
  id: string; symbol: string; name: string; currency: string; status: "open" | "closed";
  entry_date: string; exit_date: string | null; entry_price: number; exit_price: number | null;
  quantity: number; cost_basis: number; invested_capital: number; sale_proceeds: number;
  realized_pnl: number; realized_return_pct: number | null; dividends: number; fees: number;
  current_price?: number; price_date?: string; market_value?: number; unrealized_pnl?: number; unrealized_return_pct?: number;
  holding_days: number; thesis_status: string; last_assessment_date: string | null; last_explanation: string | null;
  exit_reason: string | null; replaced_by: string | null; replacement_of_symbol?: string | null;
};
export type SimulationSnapshot = {
  date: string; portfolio_id: "strategy" | "vwce"; equity: number; cash: number; invested_value: number;
  realized_pnl: number; unrealized_pnl: number; cumulative_return_pct: number; fees: number; dividends: number;
  stale_symbols: string[]; valuation_complete: boolean;
};
export type SimulationTransaction = {
  id: string; portfolio_id: "strategy" | "vwce"; symbol: string; name: string; type: "BUY" | "SELL" | "SPLIT" | "DIVIDEND";
  execution_date: string; execution_timestamp: string; execution_price: number; price_currency: string; quantity: number;
  gross_eur: number; fees_eur: number; net_cash_eur: number; fx_to_eur: number; fx_date: string; fx_source: string; price_source: string;
  position_id: string; decision_id: string | null; rationale: string; replacement_symbol?: string | null;
  realized_pnl_eur?: number | null;
};
export type SimulationDecision = {
  id: string; session: string; analysis_date: string; symbol: string | null; action: string; explanation: string;
  execution_status: string; financial_as_of: string | null; model: string; analysis_version: string;
  assessment: { thesis_status: string; principal_risks: string[]; evidence: { reference_id: string; explanation: string }[] } | null;
};
export type PortfolioSimulationData = {
  schema_version: number;
  metadata: { start_date: string; activated_at: string; initial_capital: number; currency: string; strategy_version: string;
    latest_successful_update: string | null; last_successful_analysis: string | null; last_attempt: string | null;
    status: string; transaction_fee_rate: number; return_basis: string; ai_cost_treatment: string };
  benchmark: { symbol: string; isin: string; currency: string; verified: boolean };
  portfolios: Record<"strategy" | "vwce", SimulationSnapshot & { positions: SimulationPosition[]; performance: { max_drawdown_pct: number; annualized_return_pct: number | null } }>;
  snapshots: SimulationSnapshot[]; transactions: SimulationTransaction[]; decisions: SimulationDecision[];
  orders: { id: string; symbol: string; type: string; status: string; market_cutoff: string; portfolio_id: string; rationale: string }[];
  ai_usage: { id: string; session: string; status: string; usage: { input_tokens?: number; output_tokens?: number } | null; estimated_cost_usd: number | null }[];
  ai_costs: { estimated_usd: number; complete: boolean; deducted_from_returns: false; net_economic_return: null };
  reviews: { session: string; status: string | null; screened_count: number; eligible_count: number; message: string | null }[];
};
export function comparisonPoints(data: Pick<PortfolioSimulationData, "snapshots">) {
  const days = new Map<string, Partial<Record<"strategy" | "vwce", SimulationSnapshot>>>();
  for (const snapshot of data.snapshots) {
    if (!Number.isFinite(snapshot.equity) || snapshot.equity < 0) continue;
    const day = days.get(snapshot.date) ?? {};
    day[snapshot.portfolio_id] = snapshot; days.set(snapshot.date, day);
  }
  return [...days.entries()].sort(([a], [b]) => a.localeCompare(b)).flatMap(([date, values]) =>
    values.strategy && values.vwce ? [{ date, strategy: values.strategy, vwce: values.vwce }] : []);
}
export function simulationIsStale(metadata: PortfolioSimulationData["metadata"], now = Date.now()) {
  const timestamp = Date.parse(metadata.latest_successful_update ?? metadata.activated_at);
  return !Number.isFinite(timestamp) || now - timestamp > 4 * 86400000;
}
export const simulationMoney = (value: number, currency = "EUR") => currency === "GBp"
  ? `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)} GBp`
  : new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
export const simulationPercent = (value?: number | null) => value == null ? "—"
  : `${value > 0 ? "+" : ""}${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}%`;
