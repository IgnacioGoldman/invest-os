import { AlertTriangle, ArrowLeft, BriefcaseBusiness, ChevronDown, DatabaseZap, RefreshCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  fetchCommodityOpportunities,
  fetchCryptoOpportunities,
  fetchEtfOpportunities,
  fetchOpenDataStock,
  fetchOpenDataStockAnalyses,
  fetchOpenDataStockAnalysis,
  fetchOpenDataStocks,
  fetchRefreshJobs,
  fetchRecommendations,
  fetchSnapshot,
  fetchStockCandidateAnalysis,
  generateRecommendations,
  refreshOpenDataStock,
  startRefreshJob,
  type AssetOpportunity,
  type StockEntryAnalysis,
  type StockCandidateAnalysis,
  type OpenDataStockSnapshot,
  type PortfolioSnapshot,
  type Recommendation,
  type RefreshJob,
  type RefreshSource,
} from "./api";
import { AssetInsightsTable } from "./components/AssetInsightsTable";
import { BinanceActivityTable } from "./components/BinanceActivityTable";
import { BreakdownTable } from "./components/BreakdownTable";
import { CashTable } from "./components/CashTable";
import { DataWarnings } from "./components/DataWarnings";
import { HoldingsTable } from "./components/HoldingsTable";
import { OrdersTable } from "./components/OrdersTable";
import { OpenDataStockTable } from "./components/OpenDataStockTable";
import { Recommendations } from "./components/Recommendations";
import { SourceStatus, summarizeSourceStatuses } from "./components/SourceStatus";
import { StockCandidateAnalysisPanel } from "./components/StockCandidateAnalysisPanel";
import { SummaryCards } from "./components/SummaryCards";
import "./styles.css";

const STOCK_ASSET_CLASSES = new Set(["equity", "stock", "etf", "fund"]);
const STOCK_ANALYSIS_TAXONOMY_VERSION = "2026-06-05-v2";
type ConnectorView = "home" | "portfolio" | "binance" | "ibkr";

const isActiveRefreshJob = (job: RefreshJob) => job.status === "queued" || job.status === "running";

const addAmount = (values: Record<string, number>, key: string, amount: number) => {
  if (!Number.isFinite(amount) || Math.abs(amount) <= 0.00000001) {
    return;
  }
  const normalized = key.toUpperCase();
  values[normalized] = (values[normalized] ?? 0) + amount;
};

function App() {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshSource, setRefreshSource] = useState<RefreshSource>("all");
  const [displayCurrency, setDisplayCurrency] = useState("EUR");
  const [connectorView, setConnectorView] = useState<ConnectorView>("home");
  const [aiInput, setAiInput] = useState("Analyze my portfolio and find stock entry candidates.");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [analyzingBrain, setAnalyzingBrain] = useState(false);
  const [openDataStocks, setOpenDataStocks] = useState<OpenDataStockSnapshot[]>([]);
  const [selectedOpenDataTicker, setSelectedOpenDataTicker] = useState("GOOGL");
  const [openDataStockLoading, setOpenDataStockLoading] = useState(false);
  const [openDataStockLoaded, setOpenDataStockLoaded] = useState(false);
  const [stockEntryAnalyses, setStockEntryAnalyses] = useState<Record<string, StockEntryAnalysis>>({});
  const [stockEntryAnalysesLoading, setStockEntryAnalysesLoading] = useState(false);
  const [stockEntryAnalysesLoadedKey, setStockEntryAnalysesLoadedKey] = useState("");
  const [stockCandidateAnalysis, setStockCandidateAnalysis] = useState<StockCandidateAnalysis | null>(null);
  const [stockCandidateAnalysisLoading, setStockCandidateAnalysisLoading] = useState(false);
  const [stockCandidateAnalysisLoaded, setStockCandidateAnalysisLoaded] = useState(false);
  const [etfInsights, setEtfInsights] = useState<AssetOpportunity[]>([]);
  const [cryptoInsights, setCryptoInsights] = useState<AssetOpportunity[]>([]);
  const [commodityInsights, setCommodityInsights] = useState<AssetOpportunity[]>([]);
  const [assetInsightsLoading, setAssetInsightsLoading] = useState(false);
  const [assetInsightsLoaded, setAssetInsightsLoaded] = useState(false);
  const [refreshJobs, setRefreshJobs] = useState<RefreshJob[]>([]);
  const [refreshStartPending, setRefreshStartPending] = useState(false);
  const refreshJobsRef = useRef<RefreshJob[]>([]);

  const loadPortfolioData = async () => {
    const [snap, recs] = await Promise.all([fetchSnapshot(), fetchRecommendations()]);
    setSnapshot(snap);
    setRecommendations(recs);
  };

  const pollRefreshJobs = async (isCancelled?: () => boolean) => {
    try {
      const jobs = await fetchRefreshJobs();
      if (isCancelled?.()) {
        return;
      }
      const previousById = new Map(refreshJobsRef.current.map((job) => [job.id, job]));
      const finishedSinceLastPoll = jobs.some((job) => {
        const previous = previousById.get(job.id);
        return previous && isActiveRefreshJob(previous) && !isActiveRefreshJob(job);
      });
      const successfulCompletion = jobs.some((job) => {
        const previous = previousById.get(job.id);
        return previous && isActiveRefreshJob(previous) && job.status === "success";
      });
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      if (successfulCompletion) {
        await loadPortfolioData();
      }
      if (finishedSinceLastPoll) {
        setLoading(false);
      }
    } catch {
      // Keep the dashboard usable if the transient polling endpoint misses once.
    }
  };

  const hasActiveRefreshJob = refreshJobs.some(isActiveRefreshJob);

  useEffect(() => {
    let cancelled = false;
    loadPortfolioData()
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load snapshot."))
      .finally(() => setLoading(false));
    pollRefreshJobs(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hasActiveRefreshJob) {
      return;
    }
    let cancelled = false;
    const interval = window.setInterval(() => pollRefreshJobs(() => cancelled), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [hasActiveRefreshJob]);

  useEffect(() => {
    if (stockCandidateAnalysisLoading || stockCandidateAnalysisLoaded) {
      return;
    }
    setStockCandidateAnalysisLoading(true);
    fetchStockCandidateAnalysis()
      .then((analysis) => setStockCandidateAnalysis(analysis))
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load stock candidate analysis."))
      .finally(() => {
        setStockCandidateAnalysisLoaded(true);
        setStockCandidateAnalysisLoading(false);
      });
  }, [stockCandidateAnalysisLoaded, stockCandidateAnalysisLoading]);

  useEffect(() => {
    if (openDataStocks.length > 0 || openDataStockLoading || openDataStockLoaded) {
      return;
    }
    setOpenDataStockLoading(true);
    fetchOpenDataStocks()
      .then(async (snapshots) => {
        if (snapshots.length > 0) {
          setOpenDataStocks(snapshots);
          setSelectedOpenDataTicker((ticker) =>
            snapshots.some((snapshot) => snapshot.ticker === ticker) ? ticker : snapshots[0].ticker,
          );
          return;
        }
        const snapshot = await fetchOpenDataStock("GOOGL");
        setOpenDataStocks([snapshot]);
        setSelectedOpenDataTicker(snapshot.ticker);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load open-data stocks."))
      .finally(() => {
        setOpenDataStockLoaded(true);
        setOpenDataStockLoading(false);
      });
  }, [openDataStocks.length, openDataStockLoaded, openDataStockLoading]);

  useEffect(() => {
    if (assetInsightsLoading || assetInsightsLoaded) {
      return;
    }
    setAssetInsightsLoading(true);
    Promise.all([fetchEtfOpportunities(), fetchCryptoOpportunities(), fetchCommodityOpportunities()])
      .then(([etfs, crypto, commodities]) => {
        setEtfInsights(etfs);
        setCryptoInsights(crypto);
        setCommodityInsights(commodities);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load asset insights."))
      .finally(() => {
        setAssetInsightsLoaded(true);
        setAssetInsightsLoading(false);
      });
  }, [assetInsightsLoaded, assetInsightsLoading]);

  useEffect(() => {
    if (openDataStocks.length === 0 || stockEntryAnalysesLoading) {
      return;
    }
    const analysisKey = `${STOCK_ANALYSIS_TAXONOMY_VERSION}:${openDataStocks
      .map((snapshot) => `${snapshot.ticker}:${snapshot.generated_at}`)
      .join("|")}`;
    if (stockEntryAnalysesLoadedKey === analysisKey) {
      return;
    }
    setStockEntryAnalysesLoading(true);
    fetchOpenDataStockAnalyses()
      .then((analyses) => {
        setStockEntryAnalyses(analyses);
        setStockEntryAnalysesLoadedKey(analysisKey);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load stock analyses."))
      .finally(() => {
        setStockEntryAnalysesLoading(false);
      });
  }, [
    openDataStocks,
    stockEntryAnalysesLoadedKey,
    stockEntryAnalysesLoading,
  ]);

  const refresh = async () => {
    setRefreshStartPending(true);
    setError(null);
    try {
      const job = await startRefreshJob(refreshSource);
      const jobs = await fetchRefreshJobs().catch(() => [job]);
      refreshJobsRef.current = jobs;
      setRefreshJobs(jobs);
      if (jobs.some((item) => item.id === job.id && item.status === "success")) {
        await loadPortfolioData();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh snapshot.");
    } finally {
      setRefreshStartPending(false);
    }
  };

  const analyzeBrain = async () => {
    setAnalyzingBrain(true);
    setError(null);
    try {
      const [recs, candidateAnalysis] = await Promise.all([
        generateRecommendations(),
        fetchStockCandidateAnalysis(),
      ]);
      setRecommendations(recs);
      setStockCandidateAnalysis(candidateAnalysis);
      setStockCandidateAnalysisLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run AI analysis.");
    } finally {
      setAnalyzingBrain(false);
    }
  };

  const collectOpenDataStockFacts = async (ticker: string) => {
    setOpenDataStockLoading(true);
    setStockEntryAnalysesLoading(true);
    setError(null);
    try {
      const snapshot = await refreshOpenDataStock(ticker);
      const analysis = await fetchOpenDataStockAnalysis(ticker);
      setOpenDataStocks((snapshots) => {
        const next = snapshots.filter((item) => item.ticker !== snapshot.ticker);
        next.push(snapshot);
        next.sort((left, right) => left.ticker.localeCompare(right.ticker));
        return next;
      });
      setSelectedOpenDataTicker(snapshot.ticker);
      setStockEntryAnalyses((analyses) => (analysis ? { ...analyses, [snapshot.ticker]: analysis } : analyses));
      setStockEntryAnalysesLoadedKey("");
      setOpenDataStockLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not collect ${ticker} facts.`);
    } finally {
      setOpenDataStockLoading(false);
      setStockEntryAnalysesLoading(false);
    }
  };

  const displayRate = snapshot?.display_rates.find((rate) => rate.currency === displayCurrency)?.rate_from_base ?? 1;
  const canShowUsd = Boolean(snapshot?.display_rates.some((rate) => rate.currency === "USD"));

  const cryptoHoldings = (snapshot?.holdings ?? []).filter(
    (holding) => holding.source === "binance" || holding.asset_class.toLowerCase() === "crypto",
  );
  const cryptoOpenOrders = (snapshot?.open_orders ?? []).filter((order) => order.source === "binance");
  const cryptoCashBalances = (snapshot?.cash_balances ?? []).filter(
    (cash) => cash.source === "binance" && cash.currency.toUpperCase() === "USDC",
  );
  const cryptoOrderHistory = (snapshot?.order_history ?? []).filter((order) => order.source === "binance");
  const cryptoLedgerEvents = (snapshot?.ledger_events ?? []).filter((event) => event.source === "binance");
  const stockHoldings = (snapshot?.holdings ?? []).filter(
    (holding) => holding.asset_class.toLowerCase() !== "rsu" && (
      holding.source === "ibkr" || STOCK_ASSET_CLASSES.has(holding.asset_class.toLowerCase())
    ),
  );
  const stockOpenOrders = (snapshot?.open_orders ?? []).filter((order) => order.source === "ibkr");
  const stockCashBalances = (snapshot?.cash_balances ?? []).filter((cash) => cash.source === "ibkr");
  const stockOrderHistory = (snapshot?.order_history ?? []).filter((order) => order.source === "ibkr");
  const usdDisplayRate = snapshot?.display_rates.find((rate) => rate.currency === "USD")?.rate_from_base ?? 1;
  const currentCryptoBalances: Record<string, number> = {};
  const currentCryptoAssetValues: Record<string, number> = {};
  cryptoHoldings
    .filter((holding) => holding.source === "binance")
    .forEach((holding) => {
      addAmount(currentCryptoBalances, holding.symbol, holding.quantity);
      if (holding.value_in_base != null) {
        addAmount(currentCryptoAssetValues, holding.symbol, holding.value_in_base * usdDisplayRate);
      }
    });
  (snapshot?.cash_balances ?? [])
    .filter((cash) => cash.source === "binance")
    .forEach((cash) => {
      addAmount(currentCryptoBalances, cash.currency, cash.balance);
      if (cash.value_in_base != null) {
        addAmount(currentCryptoAssetValues, cash.currency, cash.value_in_base * usdDisplayRate);
      }
    });
  const activeRefreshJobs = refreshJobs.filter(isActiveRefreshJob);
  const sourceSyncStatuses = summarizeSourceStatuses(snapshot?.source_sync_status ?? []);
  const warningCount = snapshot?.data_warnings.length ?? 0;
  const syncIssueCount =
    sourceSyncStatuses.filter((status) => status.status !== "success").length ?? 0;
  const isLanding = connectorView === "home";
  const connectorTitle =
    connectorView === "portfolio" ? "Portfolio View" : connectorView === "binance" ? "Binance" : "IBKR";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p>Investment Operating System</p>
          <h1>Invest OS</h1>
        </div>
        <div className="refresh-controls">
          {snapshot && (
            <>
              <details className="header-menu portfolio-dropdown">
                <summary className="header-menu-button portfolio-menu-button">
                  <BriefcaseBusiness size={16} aria-hidden="true" />
                  Portfolio
                  <ChevronDown size={15} aria-hidden="true" />
                </summary>
                <div className="header-menu-content portfolio-menu-content">
                  <button type="button" onClick={() => setConnectorView("home")}>
                    Main
                    <small>Brain, recommendations, and asset insights</small>
                  </button>
                  <button type="button" onClick={() => setConnectorView("portfolio")}>
                    Portfolio View
                    <small>Totals, allocation, and platform breakdown</small>
                  </button>
                  <button type="button" onClick={() => setConnectorView("ibkr")}>
                    IBKR
                    <small>Stock positions, orders, cash, activity</small>
                  </button>
                  <button type="button" onClick={() => setConnectorView("binance")}>
                    Binance
                    <small>Crypto positions, orders, activity</small>
                  </button>
                </div>
              </details>
              <details className="header-menu">
                <summary className={`header-menu-button ${warningCount ? "warning" : ""}`}>
                  <AlertTriangle size={16} aria-hidden="true" />
                  Warnings
                  <span>{warningCount}</span>
                </summary>
                <div className="header-menu-content">
                  {warningCount ? (
                    <DataWarnings warnings={snapshot.data_warnings} />
                  ) : (
                    <p className="empty block">No data warnings.</p>
                  )}
                </div>
              </details>
              <details className="header-menu">
                <summary className={`header-menu-button ${syncIssueCount ? "warning" : activeRefreshJobs.length ? "active" : ""}`}>
                  <DatabaseZap size={16} aria-hidden="true" />
                  Source Sync
                  <span>{activeRefreshJobs.length || syncIssueCount}</span>
                </summary>
                <div className="header-menu-content source-menu">
                  <SourceStatus statuses={snapshot.source_sync_status} activeJobs={activeRefreshJobs} />
                </div>
              </details>
            </>
          )}
          <div className="segmented" aria-label="Display currency">
            <button
              type="button"
              className={displayCurrency === "EUR" ? "active" : ""}
              onClick={() => setDisplayCurrency("EUR")}
            >
              EUR
            </button>
            <button
              type="button"
              className={displayCurrency === "USD" ? "active" : ""}
              onClick={() => setDisplayCurrency("USD")}
              disabled={!canShowUsd}
              title={canShowUsd ? "Show values in USD" : "Refresh market prices to enable USD display"}
            >
              USD
            </button>
          </div>
          <select
            value={refreshSource}
            onChange={(event) => setRefreshSource(event.target.value as RefreshSource)}
            disabled={loading}
            title="Choose source to refresh"
          >
            <option value="all">Refresh all</option>
            <option value="binance">Refresh Binance</option>
            <option value="ibkr">Refresh IBKR</option>
            <option value="manual">Refresh manual cash & assets</option>
            <option value="market_data">Refresh market prices</option>
          </select>
          <button onClick={refresh} disabled={loading || refreshStartPending} title="Refresh selected source">
            <RefreshCcw size={18} aria-hidden="true" />
            {refreshStartPending ? "Starting" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <section className="error">{error}</section>}
      {!snapshot && !error && <section className="loading">Loading portfolio snapshot...</section>}

      {snapshot && (
        <>
          {isLanding ? (
            <>
              <section className="brain-landing">
                <div className="brain-copy">
                  <p>Brain</p>
                  <h2>Ask Invest OS what to do next.</h2>
                </div>
                <div className="brain-input-row">
                  <input
                    value={aiInput}
                    onChange={(event) => setAiInput(event.target.value)}
                    placeholder="Analyze my portfolio and find entry candidates"
                    aria-label="AI analysis input"
                  />
                  <button type="button" onClick={analyzeBrain} disabled={analyzingBrain}>
                    {analyzingBrain ? "Analyzing" : "✨ Analyze"}
                  </button>
                </div>
              </section>

              <Recommendations
                recommendations={recommendations}
                alwaysShow
              />
              <StockCandidateAnalysisPanel
                analysis={stockCandidateAnalysis}
                loading={stockCandidateAnalysisLoading}
              />

              <section className="positions-section">
                <OpenDataStockTable
                  snapshots={openDataStocks}
                  selectedTicker={selectedOpenDataTicker}
                  loading={openDataStockLoading}
                  analyses={stockEntryAnalyses}
                  analysisLoading={stockEntryAnalysesLoading}
                  onSelectTicker={setSelectedOpenDataTicker}
                  onRefresh={collectOpenDataStockFacts}
                />
                <AssetInsightsTable
                  title="ETF Insights"
                  assets={etfInsights}
                  loading={assetInsightsLoading}
                  kind="etf"
                  emptyLabel="No ETF deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
                />
                <AssetInsightsTable
                  title="Crypto Insights"
                  assets={cryptoInsights}
                  loading={assetInsightsLoading}
                  kind="crypto"
                  emptyLabel="No crypto deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
                />
                <AssetInsightsTable
                  title="Commodities Insights"
                  assets={commodityInsights}
                  loading={assetInsightsLoading}
                  kind="commodity_proxy"
                  emptyLabel="No commodity-proxy deterministic metrics loaded. Run python scripts/build_asset_derived_signals.py."
                />
              </section>
            </>
          ) : (
            <section className="connector-section">
              <div className="connector-detail-heading">
                <button
                  type="button"
                  className="connector-back-button"
                  onClick={() => setConnectorView("home")}
                  title="Return to main insights"
                >
                  <ArrowLeft size={17} aria-hidden="true" />
                  Main
                </button>
                <div>
                  <span>Connector</span>
                  <h2>{connectorTitle}</h2>
                </div>
              </div>

              {connectorView === "portfolio" && (
                <div className="connector-body">
                  <SummaryCards snapshot={snapshot} displayCurrency={displayCurrency} displayRate={displayRate} />

                  <BreakdownTable
                    title="Platform Breakdown"
                    items={snapshot.platform_breakdown}
                    currency={displayCurrency}
                    displayRate={displayRate}
                    holdings={snapshot.holdings}
                    cashBalances={snapshot.cash_balances}
                    openOrders={snapshot.open_orders}
                    displayRates={snapshot.display_rates}
                  />
                </div>
              )}

              {connectorView === "binance" && (
                <div className="connector-body">
                  <HoldingsTable
                    title="Crypto Positions"
                    holdings={cryptoHoldings}
                    displayCurrency={displayCurrency}
                    displayRate={displayRate}
                  />
                  <OrdersTable title="Open Orders" orders={cryptoOpenOrders} cashBalances={cryptoCashBalances} />
                  <BinanceActivityTable
                    orders={cryptoOrderHistory}
                    events={cryptoLedgerEvents}
                    emptyLabel="No crypto activity loaded."
                    endTimestamp={snapshot.generated_at}
                    currentBalances={currentCryptoBalances}
                    currentAssetValues={currentCryptoAssetValues}
                  />
                </div>
              )}

              {connectorView === "ibkr" && (
                <div className="connector-body">
                  <HoldingsTable
                    title="Stock Positions"
                    holdings={stockHoldings}
                    displayCurrency={displayCurrency}
                    displayRate={displayRate}
                  />
                  <OrdersTable title="Open Orders" orders={stockOpenOrders} cashBalances={stockCashBalances} />
                  <CashTable cash={stockCashBalances} displayCurrency={displayCurrency} displayRate={displayRate} />
                  <OrdersTable title="Activity History" orders={stockOrderHistory} />
                </div>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}

export default App;
