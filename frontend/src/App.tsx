import { RefreshCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchSnapshot, refreshSnapshot, type PortfolioSnapshot, type RefreshSource } from "./api";
import { BreakdownTable } from "./components/BreakdownTable";
import { CashTable } from "./components/CashTable";
import { DataWarnings } from "./components/DataWarnings";
import { HoldingsTable } from "./components/HoldingsTable";
import { OrdersTable } from "./components/OrdersTable";
import { SourceStatus } from "./components/SourceStatus";
import { SummaryCards } from "./components/SummaryCards";
import "./styles.css";

function App() {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshSource, setRefreshSource] = useState<RefreshSource>("all");

  useEffect(() => {
    fetchSnapshot()
      .then(setSnapshot)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load snapshot."))
      .finally(() => setLoading(false));
  }, []);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      await refreshSnapshot(refreshSource);
      setSnapshot(await fetchSnapshot());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh snapshot.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p>Local Portfolio Snapshot</p>
          <h1>Invest OS</h1>
        </div>
        <div className="refresh-controls">
          <select
            value={refreshSource}
            onChange={(event) => setRefreshSource(event.target.value as RefreshSource)}
            disabled={loading}
            title="Choose source to refresh"
          >
            <option value="all">Refresh all</option>
            <option value="binance">Refresh Binance</option>
            <option value="ibkr">Refresh IBKR</option>
            <option value="ibkr_history">Refresh IBKR history</option>
            <option value="manual">Refresh manual cash & assets</option>
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
          <SummaryCards snapshot={snapshot} />
          <DataWarnings warnings={snapshot.data_warnings} />
          <SourceStatus statuses={snapshot.source_sync_status} />

          <div className="grid two">
            <BreakdownTable title="Platform Breakdown" items={snapshot.platform_breakdown} currency={snapshot.base_currency} />
            <BreakdownTable title="Asset Class Breakdown" items={snapshot.asset_class_breakdown} currency={snapshot.base_currency} />
          </div>

          <HoldingsTable title="Top Positions" holdings={snapshot.top_positions} />
          <HoldingsTable title="Holdings" holdings={snapshot.holdings} />
          <CashTable cash={snapshot.cash_balances} />

          <div className="grid two">
            <OrdersTable title="Open Orders" orders={snapshot.open_orders} />
            <OrdersTable title="Order History" orders={snapshot.order_history.slice(0, 25)} />
          </div>
        </>
      )}
    </main>
  );
}

export default App;
