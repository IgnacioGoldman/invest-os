import { AlertTriangle, BarChart3, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { AssetMetric, AssetOpportunity } from "../api";
import { formatDateTime } from "../format";

type AssetInsightKind = "etf" | "commodity_proxy" | "crypto";

type Props = {
  title: string;
  assets: AssetOpportunity[];
  loading: boolean;
  kind: AssetInsightKind;
  emptyLabel: string;
};

type MetricColumn = {
  group: "scores" | "price_metrics" | "native_metrics";
  key: string;
  label: string;
  fallbackKind?: AssetMetric["kind"];
};

const SHARED_COLUMNS: MetricColumn[] = [
  { group: "scores", key: "overall_opportunity_score", label: "Overall", fallbackKind: "ratio" },
  { group: "scores", key: "portfolio_fit_score", label: "Fit", fallbackKind: "ratio" },
  { group: "scores", key: "momentum_score", label: "Momentum", fallbackKind: "ratio" },
  { group: "scores", key: "drawdown_score", label: "Drawdown", fallbackKind: "ratio" },
  { group: "scores", key: "volatility_risk_score", label: "Risk", fallbackKind: "ratio" },
  { group: "scores", key: "liquidity_score", label: "Liquidity", fallbackKind: "ratio" },
  { group: "price_metrics", key: "change_3m", label: "3M", fallbackKind: "percent" },
  { group: "price_metrics", key: "change_1y", label: "1Y", fallbackKind: "percent" },
  { group: "price_metrics", key: "distance_from_52w_high", label: "52W High", fallbackKind: "percent" },
  { group: "price_metrics", key: "volatility_90d", label: "Vol 90D", fallbackKind: "percent" },
];

const ETF_COLUMNS: MetricColumn[] = [
  { group: "native_metrics", key: "expense_ratio", label: "Expense", fallbackKind: "percent" },
  { group: "native_metrics", key: "dividend_yield", label: "Yield", fallbackKind: "percent" },
  { group: "native_metrics", key: "total_assets", label: "AUM", fallbackKind: "compact" },
];

const CRYPTO_COLUMNS: MetricColumn[] = [
  { group: "native_metrics", key: "price_change_24h", label: "24H", fallbackKind: "percent" },
  { group: "native_metrics", key: "quote_volume_24h", label: "24H Vol", fallbackKind: "compact" },
];
const PAGE_SIZE = 10;

function formatNumber(value?: number | null, maximumFractionDigits = 1) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

function formatCompact(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatMetric(metric: AssetMetric | undefined, fallbackKind: AssetMetric["kind"] = "ratio") {
  const value = metric?.value;
  const kind = metric?.kind ?? fallbackKind;
  if (value == null || !Number.isFinite(value)) return "-";
  if (kind === "percent") return `${formatNumber(value, 2)}%`;
  if (kind === "compact") return formatCompact(value);
  if (kind === "currency") return formatNumber(value, 2);
  return formatNumber(value, 1);
}

function metricFor(asset: AssetOpportunity, column: MetricColumn) {
  return asset[column.group]?.[column.key];
}

function scoreTone(value?: number | null, inverse = false) {
  if (value == null || !Number.isFinite(value)) return "neutral";
  const normalized = inverse ? 100 - value : value;
  if (normalized >= 75) return "good";
  if (normalized >= 55) return "watch";
  if (normalized >= 35) return "caution";
  return "bad";
}

function columnsFor(kind: AssetInsightKind) {
  if (kind === "crypto") return [...SHARED_COLUMNS, ...CRYPTO_COLUMNS];
  return [...SHARED_COLUMNS, ...ETF_COLUMNS];
}

export function AssetInsightsTable({ title, assets, loading, kind, emptyLabel }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const columns = columnsFor(kind);
  const visibleAssets = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return assets
      .filter((asset) => {
        if (!normalized) return true;
        return [asset.symbol, asset.name, asset.exposure, asset.category, asset.risk_bucket]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(normalized));
      })
      .sort((left, right) => {
        const leftScore = left.scores.overall_opportunity_score?.value ?? -1;
        const rightScore = right.scores.overall_opportunity_score?.value ?? -1;
        return rightScore - leftScore;
      });
  }, [assets, query]);
  const totalPages = Math.max(1, Math.ceil(visibleAssets.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedAssets = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return visibleAssets.slice(start, start + PAGE_SIZE);
  }, [currentPage, visibleAssets]);

  useEffect(() => {
    setPage(1);
  }, [query, kind]);

  return (
    <section className="panel asset-insights">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>{title}</h2>
          <span className="asset-insights-count">{pagedAssets.length} / {visibleAssets.length} / {assets.length}</span>
        </div>
        <div className="asset-insights-search">
          <Search size={15} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search symbol, exposure, category"
            aria-label={`Search ${title}`}
          />
        </div>
      </div>

      {loading && <p className="loading inline">Loading deterministic metrics...</p>}
      {!loading && assets.length === 0 && <p className="empty block">{emptyLabel}</p>}

      {assets.length > 0 && (
        <>
          {visibleAssets.length > PAGE_SIZE && (
            <div className="table-pagination" aria-label={`${title} pagination`}>
              <button
                type="button"
                className="icon-button"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={currentPage === 1}
                title="Previous page"
              >
                <ChevronLeft size={18} aria-hidden="true" />
              </button>
              <strong>{currentPage} / {totalPages}</strong>
              <button
                type="button"
                className="icon-button"
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                disabled={currentPage === totalPages}
                title="Next page"
              >
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            </div>
          )}
          <div className="table-wrap">
            <table className="open-data-table asset-insights-table">
            <thead>
              <tr>
                <th className="sticky-symbol-column">Symbol</th>
                <th>Exposure</th>
                <th>Risk Bucket</th>
                {columns.map((column) => (
                  <th key={`${column.group}:${column.key}`}>{column.label}</th>
                ))}
                <th>Facts</th>
              </tr>
            </thead>
            <tbody>
              {pagedAssets.map((asset) => (
                <tr key={`${asset.asset_class}:${asset.symbol}`}>
                  <td className="sticky-symbol-column">
                    <div className="ticker-cell-main">
                      <strong>{asset.symbol}</strong>
                      <BarChart3 size={15} aria-hidden="true" />
                    </div>
                    <small>{asset.name ?? asset.exposure}</small>
                    <span className="latest-badge">{formatDateTime(asset.generated_at)}</span>
                  </td>
                  <td>
                    <strong>{asset.exposure}</strong>
                    <small>{asset.category?.replace(/_/g, " ") ?? asset.currency}</small>
                  </td>
                  <td>
                    <span className={`tone-pill ${scoreTone(asset.scores.volatility_risk_score?.value, true)}`}>
                      {asset.risk_bucket?.replace(/_/g, " ") ?? "-"}
                    </span>
                  </td>
                  {columns.map((column) => {
                    const metric = metricFor(asset, column);
                    const isRisk = column.key === "volatility_risk_score";
                    const tone = column.group === "scores" ? scoreTone(metric?.value, isRisk) : "neutral";
                    return (
                      <td
                        key={`${asset.symbol}:${column.group}:${column.key}`}
                        className={column.group === "scores" ? "derived-metric-cell" : undefined}
                        title={metric?.notes || metric?.source || column.label}
                      >
                        {column.group === "scores" ? (
                          <>
                            <strong className={`metric-tone ${tone}`}>{formatMetric(metric, column.fallbackKind)}</strong>
                            <small>score</small>
                          </>
                        ) : (
                          formatMetric(metric, column.fallbackKind)
                        )}
                      </td>
                    );
                  })}
                  <td className="asset-facts-cell">
                    {asset.data_gaps.length > 0 && (
                      <span title={asset.data_gaps.join("\n")}>
                        <AlertTriangle size={14} aria-hidden="true" />
                      </span>
                    )}
                    {asset.interesting_facts.length > 0 ? (
                      <ul>
                        {asset.interesting_facts.slice(0, 2).map((fact) => (
                          <li key={`${asset.symbol}:${fact.type}`}>{fact.text}</li>
                        ))}
                      </ul>
                    ) : (
                      <small>No unusual deterministic facts.</small>
                    )}
                  </td>
                </tr>
              ))}
              {visibleAssets.length === 0 && (
                <tr>
                  <td colSpan={columns.length + 4}>
                    <p className="empty block">No assets match the current filters.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </>
      )}
    </section>
  );
}
