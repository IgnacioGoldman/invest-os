const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const DATA_BASE = trimTrailingSlash(import.meta.env.VITE_STATIC_DATA_BASE_URL ?? `${import.meta.env.BASE_URL}data`);
export const STATIC_DATA_MODE = import.meta.env.VITE_DATA_MODE === "static";
const REQUEST_TIMEOUT_MS = 30000;

export type RefreshSource = "exploration_beta";

export type RefreshJob = {
  id: string;
  source: RefreshSource;
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

export type StockUniverseItem = {
  symbol: string;
  name?: string | null;
  quote_type?: string | null;
  region?: string | null;
  country?: string | null;
  sector?: string | null;
  industry?: string | null;
  active: boolean;
  loaded: boolean;
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

export type OpenDataPricePoint = {
  date: string;
  close: number;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  source: string;
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

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const payload = await response.json();
        detail = payload.detail ?? detail;
      } catch {
        // Keep the HTTP status text when the response has no JSON body.
      }
      throw new Error(detail || `Request failed with ${response.status}`);
    }
    return response.json() as Promise<T>;
  } finally {
    window.clearTimeout(timeout);
  }
}

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function staticPath(path: string): string {
  return `${DATA_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function requestStaticJson<T>(path: string): Promise<T> {
  const response = await fetch(staticPath(path), {
    headers: {
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Static data request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchOpenDataStocks(): Promise<OpenDataStockSnapshot[]> {
  if (STATIC_DATA_MODE) {
    return requestStaticJson<OpenDataStockSnapshot[]>("/open-data/stocks.json");
  }
  return requestJson<OpenDataStockSnapshot[]>("/api/open-data/stocks");
}

export async function fetchStockUniverse(): Promise<StockUniverseItem[]> {
  if (STATIC_DATA_MODE) {
    return requestStaticJson<StockUniverseItem[]>("/stocks/universe.json");
  }
  return requestJson<StockUniverseItem[]>("/api/stocks/universe");
}

export async function addActiveStock(ticker: string): Promise<OpenDataStockSnapshot> {
  if (STATIC_DATA_MODE) {
    throw new Error(`Static build cannot add ${ticker}. Update data/stocks/stocks.json and wait for the next refresh.`);
  }
  return requestJson<OpenDataStockSnapshot>(`/api/stocks/active/${encodeURIComponent(ticker)}`, {
    method: "POST",
  });
}

export async function removeActiveStock(ticker: string): Promise<{ status: string; ticker: string }> {
  if (STATIC_DATA_MODE) {
    throw new Error(`Static build cannot remove ${ticker}. Update data/stocks/stocks.json and wait for the next refresh.`);
  }
  return requestJson<{ status: string; ticker: string }>(`/api/stocks/active/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
}

export async function fetchOpenDataStockPriceHistory(ticker: string): Promise<OpenDataPricePoint[]> {
  if (STATIC_DATA_MODE) {
    return requestStaticJson<OpenDataPricePoint[]>(`/open-data/price-history/${encodeURIComponent(ticker.toUpperCase())}.json`);
  }
  return requestJson<OpenDataPricePoint[]>(`/api/open-data/stocks/${encodeURIComponent(ticker)}/price-history`);
}

export async function startRefreshJob(source: RefreshSource): Promise<RefreshJob> {
  if (STATIC_DATA_MODE) {
    throw new Error(`Static build cannot start ${source} refresh jobs. GitHub Actions refreshes the data daily.`);
  }
  return requestJson<RefreshJob>("/api/refresh", {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export async function fetchRefreshJobs(): Promise<RefreshJob[]> {
  if (STATIC_DATA_MODE) {
    return [];
  }
  return requestJson<RefreshJob[]>("/api/refresh/jobs");
}
