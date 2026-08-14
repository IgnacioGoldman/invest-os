import { AlertTriangle, BarChart3, ChevronDown, ChevronLeft, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { Fragment, memo, useEffect, useMemo, useState } from "react";
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
const DEFAULT_VISIBLE_ASSET_COLUMN_IDS = [
  "scores:overall_opportunity_score",
  "scores:portfolio_fit_score",
  "scores:momentum_score",
  "scores:drawdown_score",
];
const PAGE_SIZE = 10;

const assetColumnId = (column: MetricColumn) => `${column.group}:${column.key}`;

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

export const AssetInsightsTable = memo(function AssetInsightsTable({ title, assets, loading, kind, emptyLabel }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [columnMenuOpen, setColumnMenuOpen] = useState(false);
  const [visibleColumnIds, setVisibleColumnIds] = useState(() => DEFAULT_VISIBLE_ASSET_COLUMN_IDS);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const columns = useMemo(() => columnsFor(kind), [kind]);
  const visibleColumns = useMemo(
    () => columns.filter((column) => visibleColumnIds.includes(assetColumnId(column))),
    [columns, visibleColumnIds],
  );
  const hiddenColumns = useMemo(
    () => columns.filter((column) => !visibleColumnIds.includes(assetColumnId(column))),
    [columns, visibleColumnIds],
  );
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

  const toggleColumnVisibility = (column: MetricColumn) => {
    const id = assetColumnId(column);
    setVisibleColumnIds((ids) => {
      if (ids.includes(id)) {
        return ids.length === 1 ? ids : ids.filter((item) => item !== id);
      }
      return [...ids, id];
    });
  };

  const resetVisibleColumns = () => setVisibleColumnIds(DEFAULT_VISIBLE_ASSET_COLUMN_IDS);

  const toggleExpandedRow = (asset: AssetOpportunity) => {
    const id = `${asset.asset_class}:${asset.symbol}`;
    setExpandedRows((rows) => ({
      ...rows,
      [id]: !rows[id],
    }));
  };

  const renderMetricDetail = (asset: AssetOpportunity, column: MetricColumn) => {
    const metric = metricFor(asset, column);
    const isRisk = column.key === "volatility_risk_score";
    const tone = column.group === "scores" ? scoreTone(metric?.value, isRisk) : "neutral";
    return (
      <article
        className={`exploration-metric-card ${column.group === "scores" ? "derived" : ""}`}
        key={assetColumnId(column)}
        title={metric?.notes || metric?.source || column.label}
      >
        <span>{column.label}</span>
        <strong className={column.group === "scores" ? `metric-tone ${tone}` : undefined}>
          {formatMetric(metric, column.fallbackKind)}
        </strong>
        {metric && <small>{metric.source ?? column.group.replace(/_/g, " ")}</small>}
      </article>
    );
  };

  const renderFactsDetail = (asset: AssetOpportunity) => (
    <article className="exploration-metric-card exploration-facts-card" key="facts">
      <span>Facts</span>
      {asset.data_gaps.length > 0 && (
        <small className="exploration-warning-line">
          <AlertTriangle size={13} aria-hidden="true" />
          {asset.data_gaps.join(", ")}
        </small>
      )}
      {asset.interesting_facts.length > 0 ? (
        <ul>
          {asset.interesting_facts.map((fact) => (
            <li key={`${asset.symbol}:${fact.type}`}>{fact.text}</li>
          ))}
        </ul>
      ) : (
        <small>No unusual deterministic facts.</small>
      )}
    </article>
  );

  return (
    <section className="panel asset-insights">
      <div className="panel-heading">
        <div className="panel-title-with-info">
          <h2>{title}</h2>
          <span className="asset-insights-count">{pagedAssets.length} / {visibleAssets.length} / {assets.length}</span>
        </div>
        <div className="asset-insights-controls">
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
          <div className="column-menu">
            <button
              type="button"
              className={`filter-menu-trigger ${columnMenuOpen ? "active" : ""}`}
              onClick={() => setColumnMenuOpen((open) => !open)}
              aria-expanded={columnMenuOpen}
            >
              <SlidersHorizontal size={16} aria-hidden="true" />
              Columns
              <span>{visibleColumns.length}</span>
            </button>
            {columnMenuOpen && (
              <div className="column-popover">
                <div className="column-option-list">
                  {columns.map((column) => {
                    const id = assetColumnId(column);
                    const checked = visibleColumnIds.includes(id);
                    return (
                      <label className="column-option" key={id}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={checked && visibleColumns.length === 1}
                          onChange={() => toggleColumnVisibility(column)}
                        />
                        <span>{column.label}</span>
                      </label>
                    );
                  })}
                </div>
                <button type="button" className="filter-clear" onClick={resetVisibleColumns}>
                  Default columns
                </button>
              </div>
            )}
          </div>
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
            <table
              className="open-data-table asset-insights-table exploration-asset-table"
              style={{ minWidth: Math.max(820, 430 + visibleColumns.length * 122) }}
            >
            <thead>
              <tr>
                <th className="sticky-symbol-column">Symbol</th>
                <th>Exposure</th>
                <th>Risk Bucket</th>
                {visibleColumns.map((column) => (
                  <th key={`${column.group}:${column.key}`}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pagedAssets.map((asset) => {
                const rowId = `${asset.asset_class}:${asset.symbol}`;
                const rowExpanded = Boolean(expandedRows[rowId]);
                return (
                  <Fragment key={rowId}>
                    <tr className={rowExpanded ? "exploration-row-expanded" : ""}>
                      <td className="sticky-symbol-column">
                        <div className="ticker-cell-main">
                          <button
                            type="button"
                            className="icon-button row-toggle exploration-row-toggle"
                            onClick={() => toggleExpandedRow(asset)}
                            title={rowExpanded ? "Hide hidden values" : "Show hidden values"}
                            aria-expanded={rowExpanded}
                          >
                            {rowExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                          </button>
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
                      {visibleColumns.map((column) => {
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
                    </tr>
                    {rowExpanded && (
                      <tr className="exploration-detail-row">
                        <td colSpan={visibleColumns.length + 3}>
                          <div className="exploration-detail-panel">
                            <div className="lot-lifecycle-heading">
                              <strong>All hidden values for {asset.symbol}</strong>
                              <span>{hiddenColumns.length + 1} sections</span>
                            </div>
                            <div className="exploration-metric-grid">
                              {hiddenColumns.map((column) => renderMetricDetail(asset, column))}
                              {renderFactsDetail(asset)}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {visibleAssets.length === 0 && (
                <tr>
                  <td colSpan={visibleColumns.length + 3}>
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
});
