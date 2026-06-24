const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 30000;
const ENTRY_BUILD_TIMEOUT_MS = 30 * 60 * 1000;

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
  | "ibkr"
  | "manual"
  | "market_data";

export type RefreshJobSource =
  | RefreshSource
  | "binance_ledger"
  | "ibkr_history"
  | "fx"
  | "prices_fx";

export type RefreshJob = {
  id: string;
  source: RefreshJobSource;
  label: string;
  status: "queued" | "running" | "success" | "error";
  queued_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  stage: string;
  step_source?: string | null;
  current_step: number;
  total_steps: number;
  error?: string | null;
  duplicate_of?: string | null;
  elapsed_seconds: number;
};

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
  category:
    | "allocation"
    | "drawdown_reserve"
    | "trim_or_exit"
    | "capital_move"
    | "entry"
    | "concentration"
    | "theme";
  title: string;
  detail: string;
};

export type RecommendationSnapshot = {
  generated_at?: string | null;
  recommendations: Recommendation[];
};

export type RecommendationFollowUpResponse = {
  generated_at: string;
  mode: "openai" | "codex_required" | "codex";
  status: "complete" | "pending_codex";
  answer: string;
  context_tickers: string[];
  follow_up_id?: string | null;
  codex_command?: string | null;
};

export type BusinessHealth = {
  revenue_growth_yoy?: number | null;
  revenue_cagr_3y?: number | null;
  eps_growth_yoy?: number | null;
  eps_cagr_3y?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  free_cash_flow?: number | null;
  roe?: number | null;
  roic?: number | null;
  cash?: number | null;
  debt?: number | null;
  debt_to_equity?: number | null;
};

export type PriceOpportunity = {
  current_price?: number | null;
  change_1d?: number | null;
  change_1w?: number | null;
  change_1m?: number | null;
  change_3m?: number | null;
  change_6m?: number | null;
  change_1y?: number | null;
  change_2y?: number | null;
  change_5y?: number | null;
  distance_from_ath?: number | null;
  distance_from_52w_high?: number | null;
  distance_from_52w_low?: number | null;
  support_1d_distance?: number | null;
};

export type Valuation = {
  pe?: number | null;
  forward_pe?: number | null;
  peg?: number | null;
  price_to_sales?: number | null;
  ev_to_ebitda?: number | null;
  fcf_yield?: number | null;
};

export type EntryStockSnapshot = {
  date: string;
  ticker: string;
  name?: string | null;
  exchange?: string | null;
  country?: string | null;
  sector?: string | null;
  industry?: string | null;
  market_cap?: number | null;
  avg_volume?: number | null;
  business_health: BusinessHealth;
  price_opportunity: PriceOpportunity;
  valuation: Valuation;
};

export type EntrySnapshotFile = {
  date: string;
  source: string;
  generated_at: string;
  count: number;
  failed_tickers: string[];
  stocks: EntryStockSnapshot[];
};

export type OpenDataMetricTier =
  | "exact_public_fact"
  | "computed_from_public_facts"
  | "proxy_estimate"
  | "unavailable_open_free";

export type OpenDataMetric = {
  value?: number | null;
  source: string;
  tier: OpenDataMetricTier;
  as_of: string;
  notes: string;
};

export type OpenDataFilingExhibit = {
  document: string;
  description?: string | null;
  type?: string | null;
  url?: string | null;
};

export type OpenDataCompanyFiling = {
  accession_number: string;
  form: string;
  filing_date: string;
  report_date?: string | null;
  acceptance_datetime?: string | null;
  primary_document?: string | null;
  primary_document_description?: string | null;
  items: string[];
  exhibits: OpenDataFilingExhibit[];
  source_url?: string | null;
  notes: string;
};

export type OpenDataCompanyContext = {
  source: string;
  as_of: string;
  recent_filings: OpenDataCompanyFiling[];
  known_context_gaps: string[];
  notes: string;
};

export type OpenDataStockSnapshot = {
  ticker: string;
  name?: string | null;
  cik?: number | null;
  exchange?: string | null;
  country?: string | null;
  sector?: string | null;
  industry?: string | null;
  source: string;
  generated_at: string;
  business_health: Record<string, OpenDataMetric>;
  price_opportunity: Record<string, OpenDataMetric>;
  valuation: Record<string, OpenDataMetric>;
  historical_series: Record<string, Array<{
    period: string;
    as_of: string;
    metrics: Record<string, OpenDataMetric>;
  }>>;
  company_context?: OpenDataCompanyContext | null;
  data_gaps: string[];
  metrics: Record<string, OpenDataMetric>;
};

export type StockEntryAnalysisSection = {
  assessment: string;
  evidence: string[];
  concerns: string[];
};

export type StockEntryDcaPlan = {
  buy_now: number;
  buy_dip_1: number;
  buy_dip_2: number;
};

export type StockEntryAnalysis = {
  ticker: string;
  name?: string | null;
  generated_at: string;
  source_snapshot_generated_at?: string | null;
  needs_more_data: boolean;
  conviction: number;
  summary: string;
  opportunity_type:
    | "Temporary selloff"
    | "Quality compounder pullback"
    | "Valuation reset"
    | "Momentum continuation"
    | "Falling knife risk"
    | "Insufficient data";
  business_health: StockEntryAnalysisSection;
  price_opportunity: StockEntryAnalysisSection;
  valuation: StockEntryAnalysisSection;
  company_context: StockEntryAnalysisSection;
  missing_data: string[];
  dca_entry: StockEntryDcaPlan;
};

export type StockCandidateDecision =
  | "starter_entry_candidate"
  | "watchlist"
  | "wait"
  | "tactical_candidate"
  | "no_clean_candidate";

export type StockCandidate = {
  ticker: string;
  name?: string | null;
  horizon?: "long_term_accumulation" | "tactical_entry" | "long_term" | "short_term" | "both" | null;
  conviction: number;
  decision: StockCandidateDecision;
  entry_quality: string;
  why_now: string;
  thesis: string;
  business_evidence?: string[];
  valuation_evidence?: string[];
  price_evidence?: string[];
  support_1d_evidence?: string[];
  derived_signal_evidence?: string[];
  key_risks?: string[];
  evidence: string[];
  main_risks: string[];
  missing_data: string[];
};

export type StockRunnerUp = {
  ticker: string;
  name?: string | null;
  horizon: "long_term_accumulation" | "tactical_entry" | "long_term" | "short_term" | "both";
  reason: string;
};

export type StockRejectedCandidate = {
  ticker: string;
  name?: string | null;
  reason: string;
};

export type StockCandidateAnalysis = {
  generated_at: string;
  as_of: string;
  source: string;
  skill: string;
  deterministic_inputs: string[];
  live_context_used: boolean;
  best_long_term_candidate?: StockCandidate | null;
  best_short_term_candidate?: StockCandidate | null;
  runner_ups: StockRunnerUp[];
  rejected_interesting_names: StockRejectedCandidate[];
  data_quality_notes: string[];
};

export type AssetMetric = {
  value?: number | null;
  kind: "percent" | "ratio" | "compact" | "currency";
  source: string;
  as_of: string;
  notes: string;
};

export type AssetInterestingFact = {
  type: string;
  severity: number;
  text: string;
  evidence: string[];
};

export type AssetClass = "etf" | "commodity_proxy" | "crypto";

export type AssetOpportunity = {
  symbol: string;
  name?: string | null;
  asset_class: AssetClass;
  exposure: string;
  category?: string | null;
  currency: string;
  generated_at: string;
  price_metrics: Record<string, AssetMetric>;
  native_metrics: Record<string, AssetMetric>;
  scores: Record<string, AssetMetric>;
  interesting_facts: AssetInterestingFact[];
  risk_bucket?: string | null;
  data_gaps: string[];
};

export type AssetOpportunityFile = {
  generated_at: string;
  source: string;
  deterministic_inputs: string[];
  count: number;
  assets: AssetOpportunity[];
  collection_errors: string[];
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

async function requestSnapshot(
  path: string,
  init?: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<PortfolioSnapshot> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
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

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail ?? `Request failed: ${response.status}`);
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request timed out.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function fetchSnapshot(): Promise<PortfolioSnapshot> {
  return requestSnapshot("/api/snapshot");
}

export async function startRefreshJob(source: RefreshSource): Promise<RefreshJob> {
  return requestJson<RefreshJob>("/api/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
}

export async function fetchRefreshJobs(): Promise<RefreshJob[]> {
  return requestJson<RefreshJob[]>("/api/refresh/jobs");
}

export async function fetchRecommendations(): Promise<RecommendationSnapshot> {
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

export async function generateRecommendations(): Promise<RecommendationSnapshot> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS * 3);
  try {
    const response = await fetch(`${API_BASE}/api/recommendations`, {
      method: "POST",
      signal: controller.signal,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail ?? `Recommendations generation failed: ${response.status}`);
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Recommendations generation timed out.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function askRecommendationFollowUp(
  recommendation: Recommendation,
  question: string,
): Promise<RecommendationFollowUpResponse> {
  return requestJson<RecommendationFollowUpResponse>(
    "/api/recommendations/follow-up",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recommendation, question }),
    },
    REQUEST_TIMEOUT_MS * 2,
  );
}

export async function fetchRecommendationFollowUpResult(requestId: string): Promise<RecommendationFollowUpResponse> {
  return requestJson<RecommendationFollowUpResponse>(`/api/recommendations/follow-up/${requestId}`);
}

export async function fetchLatestEntrySnapshot(): Promise<EntrySnapshotFile | null> {
  try {
    return await requestJson<EntrySnapshotFile>("/api/entry/snapshot");
  } catch (error) {
    if (error instanceof Error && error.message.includes("No entry snapshot")) {
      return null;
    }
    throw error;
  }
}

export async function buildEntrySnapshot(limit = 2000): Promise<EntrySnapshotFile> {
  return requestJson<EntrySnapshotFile>(
    "/api/entry/snapshot",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit }),
    },
    ENTRY_BUILD_TIMEOUT_MS,
  );
}

export async function fetchOpenDataStocks(): Promise<OpenDataStockSnapshot[]> {
  return requestJson<OpenDataStockSnapshot[]>("/api/open-data/stocks");
}

export async function fetchOpenDataStock(ticker = "GOOGL"): Promise<OpenDataStockSnapshot> {
  return requestJson<OpenDataStockSnapshot>(`/api/open-data/stocks/${encodeURIComponent(ticker)}`);
}

export async function fetchOpenDataStockAnalyses(): Promise<Record<string, StockEntryAnalysis>> {
  try {
    return await requestJson<Record<string, StockEntryAnalysis>>("/api/open-data/stocks/analysis");
  } catch (error) {
    if (error instanceof Error && error.message.includes("No collected open-data stock facts")) {
      return {};
    }
    throw error;
  }
}

export async function fetchOpenDataStockAnalysis(ticker = "GOOGL"): Promise<StockEntryAnalysis | null> {
  try {
    return await requestJson<StockEntryAnalysis>(`/api/open-data/stocks/${encodeURIComponent(ticker)}/analysis`);
  } catch (error) {
    if (error instanceof Error && error.message.includes("No collected open-data facts")) {
      return null;
    }
    throw error;
  }
}

export async function fetchStockCandidateAnalysis(): Promise<StockCandidateAnalysis | null> {
  try {
    return await requestJson<StockCandidateAnalysis>("/api/open-data/stocks/candidate-analysis");
  } catch (error) {
    if (error instanceof Error && error.message.includes("No AI stock candidate analysis")) {
      return null;
    }
    throw error;
  }
}

export async function fetchAssetOpportunities(): Promise<AssetOpportunityFile | null> {
  try {
    return await requestJson<AssetOpportunityFile>("/api/open-data/assets");
  } catch (error) {
    if (error instanceof Error && error.message.includes("No multi-asset derived signals")) {
      return null;
    }
    throw error;
  }
}

export async function fetchEtfOpportunities(): Promise<AssetOpportunity[]> {
  return requestJson<AssetOpportunity[]>("/api/open-data/assets/etfs");
}

export async function fetchCommodityOpportunities(): Promise<AssetOpportunity[]> {
  return requestJson<AssetOpportunity[]>("/api/open-data/assets/commodities");
}

export async function fetchCryptoOpportunities(): Promise<AssetOpportunity[]> {
  return requestJson<AssetOpportunity[]>("/api/open-data/assets/crypto");
}

export async function refreshOpenDataStock(ticker = "GOOGL"): Promise<OpenDataStockSnapshot> {
  return requestJson<OpenDataStockSnapshot>(
    `/api/open-data/stocks/${encodeURIComponent(ticker)}/refresh`,
    { method: "POST" },
    ENTRY_BUILD_TIMEOUT_MS,
  );
}
