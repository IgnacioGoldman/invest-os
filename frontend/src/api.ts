const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 30000;

export type Holding = {
  id: string;
  source: string;
  platform: string;
  symbol: string;
  name?: string | null;
  asset_class: string;
  quantity: number;
  currency: string;
  current_price?: number | null;
  market_value: number;
  cost_basis?: number | null;
  unrealized_pnl?: number | null;
  sector?: string | null;
  vertical?: string | null;
  geography?: string | null;
  confidence: string;
  updated_at: string;
  valuation_source?: string | null;
  valuation_timestamp?: string | null;
  value_in_base?: number | null;
};

export type CashBalance = {
  id: string;
  source: string;
  platform: string;
  currency: string;
  balance: number;
  purpose: string;
  updated_at: string;
  value_in_base?: number | null;
};

export type Order = {
  id: string;
  source: string;
  platform: string;
  symbol: string;
  side: "BUY" | "SELL";
  order_type?: string | null;
  quantity: number;
  limit_price?: number | null;
  status?: string | null;
  created_at?: string | null;
  purpose: string;
  raw: Record<string, unknown>;
  quote_currency?: string | null;
  purchase_amount?: number | null;
  current_value?: number | null;
  roi_percent?: number | null;
  cost_basis_amount?: number | null;
  realized_pnl?: number | null;
  realized_roi_percent?: number | null;
  unrealized_pnl?: number | null;
  unrealized_roi_percent?: number | null;
  remaining_quantity?: number | null;
  remaining_cost_basis?: number | null;
  position_status?: string | null;
  account_value_before?: number | null;
  account_value_after?: number | null;
  account_value_currency?: string | null;
  account_value_source?: string | null;
  account_value_warning?: string | null;
  account_balances_after?: Record<string, number>;
  account_asset_values_after?: Record<string, number>;
  valuation_source?: string | null;
  valuation_timestamp?: string | null;
};

export type BinanceLedgerEvent = {
  id: string;
  source: "binance";
  platform: string;
  event_type: "start" | "deposit" | "withdrawal" | "convert" | "fiat_deposit" | "fiat_withdrawal" | "transfer";
  asset: string;
  amount: number;
  original_amount?: number | null;
  credited_amount?: number | null;
  fee: number;
  status?: string | null;
  created_at: string;
  balance_changes: Record<string, number>;
  raw: Record<string, unknown>;
  account_value_after?: number | null;
  account_value_currency?: string | null;
  account_value_source?: string | null;
  account_value_warning?: string | null;
  account_balances_after?: Record<string, number>;
  account_asset_values_after?: Record<string, number>;
};

export type BreakdownItem = {
  name: string;
  value: number;
  percent: number;
};

export type RefreshSource =
  | "all"
  | "binance"
  | "binance_ledger"
  | "ibkr"
  | "ibkr_history"
  | "manual"
  | "market_data"
  | "fx"
  | "prices_fx";

export type SourceSyncStatus = {
  source: string;
  last_synced_at?: string | null;
  status: string;
  warning?: string | null;
};

export type DisplayRate = {
  currency: string;
  rate_from_base: number;
  source: string;
  fetched_at?: string | null;
};

export type Recommendation = {
  severity: "info" | "warning" | "critical";
  title: string;
  detail: string;
};

export type PortfolioSnapshot = {
  generated_at: string;
  base_currency: string;
  total_net_worth: number;
  total_cash: number;
  total_invested: number;
  holdings: Holding[];
  cash_balances: CashBalance[];
  open_orders: Order[];
  order_history: Order[];
  ledger_events: BinanceLedgerEvent[];
  platform_breakdown: BreakdownItem[];
  asset_class_breakdown: BreakdownItem[];
  top_positions: Holding[];
  data_warnings: string[];
  source_sync_status: SourceSyncStatus[];
  display_rates: DisplayRate[];
};

async function requestSnapshot(path: string, init?: RequestInit): Promise<PortfolioSnapshot> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Snapshot request failed: ${response.status}`);
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Snapshot request timed out.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function fetchSnapshot(): Promise<PortfolioSnapshot> {
  return requestSnapshot("/api/snapshot");
}

export async function refreshSnapshot(source: RefreshSource): Promise<PortfolioSnapshot> {
  return requestSnapshot("/api/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
}

export async function fetchRecommendations(): Promise<Recommendation[]> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}/api/recommendations`, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Recommendations request failed: ${response.status}`);
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Recommendations request timed out.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}
