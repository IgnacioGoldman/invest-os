import { AlertTriangle, DatabaseZap, RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchRecommendations, fetchSnapshot, refreshSnapshot, type PortfolioSnapshot, type Recommendation, type RefreshSource } from "./api";
import { BinanceActivityTable } from "./components/BinanceActivityTable";
import { BreakdownTable } from "./components/BreakdownTable";
import { CashTable } from "./components/CashTable";
import { DataWarnings } from "./components/DataWarnings";
import { HoldingsTable } from "./components/HoldingsTable";
import { OrdersTable } from "./components/OrdersTable";
import { Recommendations } from "./components/Recommendations";
import { SourceStatus } from "./components/SourceStatus";
import { SummaryCards } from "./components/SummaryCards";
import "./styles.css";

type SourceFilter = "all" | "binance" | "ibkr";
type DashboardView = "portfolio" | "crypto" | "stocks";

const STOCK_ASSET_CLASSES = new Set(["equity", "stock", "etf", "fund"]);

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
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [dashboardView, setDashboardView] = useState<DashboardView>("portfolio");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  useEffect(() => {
    Promise.all([fetchSnapshot(), fetchRecommendations()])
      .then(([snap, recs]) => {
        setSnapshot(snap);
        setRecommendations(recs);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load snapshot."))
      .finally(() => setLoading(false));
  }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      await refreshSnapshot(refreshSource);
      const [snap, recs] = await Promise.all([fetchSnapshot(), fetchRecommendations()]);
      setSnapshot(snap);
      setRecommendations(recs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh snapshot.");
    } finally {
      setLoading(false);
    }
  };

  const displayRate = snapshot?.display_rates.find((rate) => rate.currency === displayCurrency)?.rate_from_base ?? 1;
  const canShowUsd = Boolean(snapshot?.display_rates.some((rate) => rate.currency === "USD"));

  const filterBySource = <T extends { source: string }>(items: T[]) =>
    sourceFilter === "all" ? items : items.filter((item) => item.source === sourceFilter);
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
  const warningCount = snapshot?.data_warnings.length ?? 0;
  const syncIssueCount =
    snapshot?.source_sync_status.filter((status) => status.status !== "success").length ?? 0;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p>Local Portfolio Snapshot</p>
          <h1>Invest OS</h1>
        </div>
        <div className="refresh-controls">
          <div className="segmented" aria-label="Dashboard view">
            <button
              type="button"
              className={dashboardView === "portfolio" ? "active" : ""}
              onClick={() => setDashboardView("portfolio")}
            >
              Portfolio
            </button>
            <button
              type="button"
              className={dashboardView === "crypto" ? "active" : ""}
              onClick={() => setDashboardView("crypto")}
            >
              Crypto
            </button>
            <button
              type="button"
              className={dashboardView === "stocks" ? "active" : ""}
              onClick={() => setDashboardView("stocks")}
            >
              Stocks
            </button>
          </div>
          {snapshot && (
            <>
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
                <summary className={`header-menu-button ${syncIssueCount ? "warning" : ""}`}>
                  <DatabaseZap size={16} aria-hidden="true" />
                  Source Sync
                  <span>{syncIssueCount}</span>
                </summary>
                <div className="header-menu-content source-menu">
                  <SourceStatus statuses={snapshot.source_sync_status} />
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
              title={canShowUsd ? "Show values in USD" : "Refresh FX rates to enable USD display"}
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
            <option value="binance_ledger">Refresh Binance ledger</option>
            <option value="ibkr">Refresh IBKR</option>
            <option value="ibkr_history">Refresh IBKR history</option>
            <option value="manual">Refresh manual cash & assets</option>
            <option value="market_data">Refresh market prices</option>
            <option value="fx">Refresh FX rates</option>
            <option value="prices_fx">Refresh prices & FX</option>
          </select>
          <button onClick={refresh} disabled={loading} title="Refresh selected source">
            <RefreshCcw size={18} aria-hidden="true" />
            {loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <section className="error">{error}</section>}
      {!snapshot && !error && <section className="loading">Loading portfolio snapshot...</section>}

      {snapshot && (
        <>
          {dashboardView === "portfolio" && (
            <>
              <SummaryCards snapshot={snapshot} displayCurrency={displayCurrency} displayRate={displayRate} />

              <div className="grid two">
                <BreakdownTable
                  title="Platform Breakdown"
                  items={snapshot.platform_breakdown}
                  currency={displayCurrency}
                  displayRate={displayRate}
                />
                <BreakdownTable
                  title="Asset Class Breakdown"
                  items={snapshot.asset_class_breakdown}
                  currency={displayCurrency}
                  displayRate={displayRate}
                />
              </div>

              <CashTable cash={snapshot.cash_balances} displayCurrency={displayCurrency} displayRate={displayRate} />

              <Recommendations recommendations={recommendations} />

              <section className="positions-section">
                <div className="section-heading">
                  <h2>Open Positions</h2>
                  <div className="segmented" aria-label="Source filter">
                    <button
                      type="button"
                      className={sourceFilter === "all" ? "active" : ""}
                      onClick={() => setSourceFilter("all")}
                    >
                      All
                    </button>
                    <button
                      type="button"
                      className={sourceFilter === "binance" ? "active" : ""}
                      onClick={() => setSourceFilter("binance")}
                    >
                      Binance
                    </button>
                    <button
                      type="button"
                      className={sourceFilter === "ibkr" ? "active" : ""}
                      onClick={() => setSourceFilter("ibkr")}
                    >
                      IBKR
                    </button>
                  </div>
                </div>
                <HoldingsTable
                  title="Open Positions"
                  holdings={filterBySource(snapshot.holdings)}
                  displayCurrency={displayCurrency}
                  displayRate={displayRate}
                />
              </section>
            </>
          )}

          {dashboardView === "crypto" && (
            <section className="positions-section">
              <div className="section-heading">
                <h2>Crypto</h2>
              </div>
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
            </section>
          )}

          {dashboardView === "stocks" && (
            <section className="positions-section">
              <div className="section-heading">
                <h2>Stocks</h2>
              </div>
              <HoldingsTable
                title="Stock Positions"
                holdings={stockHoldings}
                displayCurrency={displayCurrency}
                displayRate={displayRate}
              />
              <OrdersTable title="Open Orders" orders={stockOpenOrders} cashBalances={stockCashBalances} />
              <CashTable cash={stockCashBalances} displayCurrency={displayCurrency} displayRate={displayRate} />
              <OrdersTable title="Activity History" orders={stockOrderHistory} />
            </section>
          )}
        </>
      )}
    </main>
  );
}

export default App;
