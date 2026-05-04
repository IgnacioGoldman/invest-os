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
};

export type CashBalance = {
  id: string;
  source: string;
  platform: string;
  currency: string;
  balance: number;
  purpose: string;
  updated_at: string;
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
};

export type BreakdownItem = {
  name: string;
  value: number;
  percent: number;
};

export type RefreshSource = "all" | "binance" | "ibkr" | "ibkr_history" | "manual";

export type SourceSyncStatus = {
  source: string;
  last_synced_at?: string | null;
  status: string;
  warning?: string | null;
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
  platform_breakdown: BreakdownItem[];
  asset_class_breakdown: BreakdownItem[];
  top_positions: Holding[];
  data_warnings: string[];
  source_sync_status: SourceSyncStatus[];
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
