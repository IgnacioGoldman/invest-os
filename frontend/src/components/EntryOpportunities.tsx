import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";
import type { EntrySnapshotFile, StockEntryAnalysis, StockEntryAnalysisSection } from "../api";
import { formatDateTime } from "../format";

type Props = {
  snapshot: EntrySnapshotFile | null;
  analyses: StockEntryAnalysis[];
  loading: boolean;
  analysisLoading: boolean;
  building: boolean;
  onBuild: () => void;
};

const PAGE_SIZES = [25, 50, 100, 200];
const CONVICTION_HELP =
  "0-3: weak / avoid / insufficient facts\n" +
  "4-5: interesting but too uncertain\n" +
  "6-7: interesting setup, but with meaningful caveats\n" +
  "8-10: very strong setup with cleaner valuation, price action, and evidence";

type Tone = "good" | "watch" | "caution" | "bad" | "neutral";

const OPPORTUNITY_COPY: Record<StockEntryAnalysis["opportunity_type"], { label: string; detail: string; tone: Tone }> = {
  "Temporary selloff": {
    label: "Short-term wobble",
    detail: "The stock has pulled back, but the supplied facts do not prove a deeper bargain.",
    tone: "watch",
  },
  "Quality compounder pullback": {
    label: "Good business, less stretched",
    detail: "Good business, still expensive-ish, but temporarily less stretched than it was.",
    tone: "good",
  },
  "Valuation reset": {
    label: "Price reset",
    detail: "The price or valuation has reset enough to make a fresh look worthwhile.",
    tone: "good",
  },
  "Momentum continuation": {
    label: "Still running",
    detail: "The longer trend is strong, so this is more trend-following than bargain hunting.",
    tone: "watch",
  },
  "Falling knife risk": {
    label: "Still falling",
    detail: "The price move looks risky enough that waiting for better evidence may be wiser.",
    tone: "bad",
  },
  "Insufficient data": {
    label: "Need more facts",
    detail: "The supplied facts are not enough to judge the setup confidently.",
    tone: "neutral",
  },
};

const ASSESSMENT_COPY: Record<string, { label: string; tone: Tone }> = {
  strong: { label: "Strong", tone: "good" },
  solid: { label: "Solid", tone: "good" },
  mixed: { label: "Mixed", tone: "watch" },
  weak: { label: "Weak", tone: "caution" },
  unclear: { label: "Unclear", tone: "neutral" },
  no_dip: { label: "No dip", tone: "caution" },
  strong_trend: { label: "Strong trend", tone: "watch" },
  better_spot: { label: "Better spot", tone: "watch" },
  pullback: { label: "Pullback", tone: "good" },
  deep_pullback: { label: "Deep pullback", tone: "watch" },
  falling: { label: "Falling", tone: "bad" },
  cheap: { label: "Cheap", tone: "good" },
  fair: { label: "Fair", tone: "good" },
  slightly_expensive: { label: "Slightly expensive", tone: "watch" },
  pricey: { label: "Pricey", tone: "caution" },
  very_pricey: { label: "Very pricey", tone: "bad" },
  fair_or_unclear: { label: "Fair / unclear", tone: "watch" },
  expensive_but_quality_supported: { label: "Pricey", tone: "caution" },
  moderate_short_term_pullback_with_strong_longer_trend: { label: "Pullback", tone: "good" },
  meaningful_pullback_weak_trend: { label: "Better spot", tone: "watch" },
  extended_no_pullback: { label: "No dip", tone: "caution" },
  strong_momentum_no_pullback: { label: "Strong trend", tone: "watch" },
  recent_sec_context_available_but_not_interpretable_for_sentiment: { label: "SEC context", tone: "neutral" },
  no_recent_sec_context: { label: "No SEC context", tone: "neutral" },
};

function formatCompact(value?: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatMetric(value?: number | null, digits = 2) {
  if (value == null) return "-";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

function formatPercent(value?: number | null) {
  if (value == null) return "-";
  return `${formatMetric(value)}%`;
}

function movementClass(value?: number | null) {
  if (value == null || value === 0) return undefined;
  return value > 0 ? "positive" : "negative";
}

function assessmentLabel(value: string) {
  return value.replace(/_/g, " ");
}

function assessmentCopy(value: string) {
  return ASSESSMENT_COPY[value] ?? { label: assessmentLabel(value), tone: "neutral" as const };
}

function analysisHeading(analysis: StockEntryAnalysis) {
  if (!analysis.name || analysis.name === analysis.ticker) return analysis.ticker;
  return `${analysis.ticker} (${analysis.name})`;
}

function verdictText(analysis: StockEntryAnalysis) {
  const summary = analysis.summary.trim();
  const names = [analysis.name, analysis.ticker].filter(Boolean) as string[];
  for (const name of names) {
    if (summary.startsWith(`${name} has `)) return summary.slice(`${name} has `.length);
    if (summary.startsWith(`${name} looks like `)) return `looks like ${summary.slice(`${name} looks like `.length)}`;
    if (summary.startsWith(`${name} `)) return summary.slice(name.length + 1);
  }
  return summary;
}

function convictionTone(value: number, needsMoreData: boolean): Tone {
  if (needsMoreData || value < 4) return "bad";
  if (value < 6) return "watch";
  if (value < 8) return "watch";
  return "good";
}

function opportunityToneFor(analysis: StockEntryAnalysis, baseTone: Tone): Tone {
  const valuationTone = assessmentCopy(analysis.valuation.assessment).tone;
  const confidenceTone = convictionTone(analysis.conviction, analysis.needs_more_data);
  if (analysis.needs_more_data || confidenceTone === "bad") return "bad";
  if (baseTone === "good" && (confidenceTone !== "good" || valuationTone === "bad")) return "watch";
  return baseTone;
}

function AnalysisSection({
  title,
  section,
}: {
  title: string;
  section: StockEntryAnalysisSection;
}) {
  const tag = assessmentCopy(section.assessment);
  const detail = assessmentLabel(section.assessment);

  return (
    <details className="entry-analysis-section">
      <summary>
        <h4>{title}</h4>
        <span className={`analysis-tag ${tag.tone}`} title={detail}>
          {tag.label}
        </span>
      </summary>
      {section.evidence.length > 0 && (
        <ul>
          {section.evidence.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {section.concerns.length > 0 && (
        <div className="entry-analysis-concerns">
          {section.concerns.slice(0, 3).map((item) => (
            <p key={item}>{item}</p>
          ))}
        </div>
      )}
    </details>
  );
}

function StockEntryAnalysisCard({ analysis }: { analysis: StockEntryAnalysis }) {
  const dcaTotal = analysis.dca_entry.buy_now + analysis.dca_entry.buy_dip_1 + analysis.dca_entry.buy_dip_2;
  const opportunity = OPPORTUNITY_COPY[analysis.opportunity_type];
  const opportunityTone = opportunityToneFor(analysis, opportunity.tone);
  const confidenceTone = convictionTone(analysis.conviction, analysis.needs_more_data);

  return (
    <article className="entry-analysis-card">
      <div className="entry-analysis-hero">
        <div>
          <div className="entry-analysis-title">
            <strong>{analysisHeading(analysis)}</strong>
            <span className={`tone-chip ${opportunityTone}`} title={opportunity.detail}>
              {opportunity.label}
            </span>
            {analysis.needs_more_data && <span className="warning-chip">Needs data</span>}
          </div>
          <p className="entry-analysis-verdict">
            <strong>Verdict:</strong> {verdictText(analysis)}
          </p>
        </div>
        <div
          className={`conviction-meter ${confidenceTone}`}
          aria-label={`Conviction ${analysis.conviction} out of 10`}
          title={CONVICTION_HELP}
        >
          <strong>{analysis.conviction.toFixed(1)}</strong>
          <span>Conviction</span>
        </div>
      </div>

      <div className="entry-analysis-grid">
        <AnalysisSection title="Business" section={analysis.business_health} />
        <AnalysisSection title="Price" section={analysis.price_opportunity} />
        <AnalysisSection title="Valuation" section={analysis.valuation} />
      </div>

      <div className="dca-plan">
        <div className="dca-bars" aria-label={`DCA total ${dcaTotal}%`}>
          <span style={{ flexGrow: analysis.dca_entry.buy_now || 1 }}>
            Now {analysis.dca_entry.buy_now}%
          </span>
          <span style={{ flexGrow: analysis.dca_entry.buy_dip_1 || 1 }}>
            Dip 1 {analysis.dca_entry.buy_dip_1}%
          </span>
          <span style={{ flexGrow: analysis.dca_entry.buy_dip_2 || 1 }}>
            Dip 2 {analysis.dca_entry.buy_dip_2}%
          </span>
        </div>
      </div>

      {analysis.missing_data.length > 0 && (
        <div className="entry-analysis-missing">
          <strong>Missing data for stronger confidence</strong>
          <ul>
            {analysis.missing_data.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="entry-analysis-footer">
        <span>Generated {formatDateTime(analysis.generated_at)}</span>
        {analysis.source_snapshot_generated_at && (
          <span>Facts {formatDateTime(analysis.source_snapshot_generated_at)}</span>
        )}
      </div>
    </article>
  );
}

export function EntryOpportunities({
  snapshot,
  analyses,
  loading,
  analysisLoading,
  building,
  onBuild,
}: Props) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const stocks = snapshot?.stocks ?? [];
  const totalCount = (snapshot?.count ?? 0) + analyses.length;
  const totalPages = Math.max(1, Math.ceil(stocks.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleStocks = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return stocks.slice(start, start + pageSize);
  }, [currentPage, pageSize, stocks]);

  const onPageSizeChange = (value: number) => {
    setPageSize(value);
    setPage(1);
  };

  return (
    <section className="panel entry-opportunities">
      <div className="panel-heading">
        <h2>Entry Opportunities</h2>
        <div className="panel-heading-actions">
          <span>{totalCount}</span>
          <button type="button" onClick={onBuild} disabled={building} title="Find entry opportunities">
            <Search size={16} aria-hidden="true" />
            {building ? "Finding" : "Find Entry Opportunities"}
          </button>
        </div>
      </div>

      {snapshot && (
        <div className="entry-meta">
          <strong>{snapshot.date}</strong>
          <span>{formatDateTime(snapshot.generated_at)}</span>
          <span>{snapshot.source.toUpperCase()}</span>
          <span>{snapshot.failed_tickers.length} failed</span>
        </div>
      )}

      {loading && <p className="loading inline">Loading entry snapshot...</p>}
      {analysisLoading && <p className="loading inline">Loading stock analysis...</p>}
      {!loading && !analysisLoading && !snapshot && analyses.length === 0 && (
        <p className="empty block">No entry snapshot generated yet.</p>
      )}

      {analyses.map((analysis) => (
        <StockEntryAnalysisCard key={analysis.ticker} analysis={analysis} />
      ))}

      {snapshot && (
        <>
          <div className="activity-controls entry-controls">
            <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size} rows
                </option>
              ))}
            </select>
            <button
              type="button"
              className="icon-button"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={currentPage === 1}
              title="Previous page"
            >
              <ChevronLeft size={18} aria-hidden="true" />
            </button>
            <strong>
              {currentPage} / {totalPages}
            </strong>
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
          <div className="table-wrap">
            <table className="entry-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Exchange</th>
                  <th>Sector</th>
                  <th>Market Cap</th>
                  <th>Avg Volume</th>
                  <th>Rev YoY</th>
                  <th>Rev CAGR 3Y</th>
                  <th>EPS YoY</th>
                  <th>EPS CAGR 3Y</th>
                  <th>Gross</th>
                  <th>Operating</th>
                  <th>Net</th>
                  <th>FCF</th>
                  <th>ROE</th>
                  <th>ROIC</th>
                  <th>Cash</th>
                  <th>Debt</th>
                  <th>D/E</th>
                  <th>Price</th>
                  <th>1D</th>
                  <th>1W</th>
                  <th>1M</th>
                  <th>3M</th>
                  <th>6M</th>
                  <th>1Y</th>
                  <th>2Y</th>
                  <th>5Y</th>
                  <th>ATH</th>
                  <th>52W High</th>
                  <th>52W Low</th>
                  <th>PE</th>
                  <th>Fwd PE</th>
                  <th>PEG</th>
                  <th>P/S</th>
                  <th>EV/EBITDA</th>
                  <th>FCF Yield</th>
                </tr>
              </thead>
              <tbody>
                {visibleStocks.map((stock) => (
                  <tr key={stock.ticker}>
                    <td>
                      <strong>{stock.ticker}</strong>
                      <small>{stock.name}</small>
                    </td>
                    <td>
                      {stock.exchange ?? "-"}
                      <small>{stock.country}</small>
                    </td>
                    <td>
                      {stock.sector ?? "-"}
                      <small>{stock.industry}</small>
                    </td>
                    <td>{formatCompact(stock.market_cap)}</td>
                    <td>{formatCompact(stock.avg_volume)}</td>
                    <td className={movementClass(stock.business_health.revenue_growth_yoy)}>
                      {formatPercent(stock.business_health.revenue_growth_yoy)}
                    </td>
                    <td className={movementClass(stock.business_health.revenue_cagr_3y)}>
                      {formatPercent(stock.business_health.revenue_cagr_3y)}
                    </td>
                    <td className={movementClass(stock.business_health.eps_growth_yoy)}>
                      {formatPercent(stock.business_health.eps_growth_yoy)}
                    </td>
                    <td className={movementClass(stock.business_health.eps_cagr_3y)}>
                      {formatPercent(stock.business_health.eps_cagr_3y)}
                    </td>
                    <td>{formatPercent(stock.business_health.gross_margin)}</td>
                    <td>{formatPercent(stock.business_health.operating_margin)}</td>
                    <td>{formatPercent(stock.business_health.net_margin)}</td>
                    <td>{formatCompact(stock.business_health.free_cash_flow)}</td>
                    <td>{formatPercent(stock.business_health.roe)}</td>
                    <td>{formatPercent(stock.business_health.roic)}</td>
                    <td>{formatCompact(stock.business_health.cash)}</td>
                    <td>{formatCompact(stock.business_health.debt)}</td>
                    <td>{formatMetric(stock.business_health.debt_to_equity)}</td>
                    <td>{formatMetric(stock.price_opportunity.current_price)}</td>
                    <td className={movementClass(stock.price_opportunity.change_1d)}>
                      {formatPercent(stock.price_opportunity.change_1d)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_1w)}>
                      {formatPercent(stock.price_opportunity.change_1w)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_1m)}>
                      {formatPercent(stock.price_opportunity.change_1m)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_3m)}>
                      {formatPercent(stock.price_opportunity.change_3m)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_6m)}>
                      {formatPercent(stock.price_opportunity.change_6m)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_1y)}>
                      {formatPercent(stock.price_opportunity.change_1y)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_2y)}>
                      {formatPercent(stock.price_opportunity.change_2y)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.change_5y)}>
                      {formatPercent(stock.price_opportunity.change_5y)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.distance_from_ath)}>
                      {formatPercent(stock.price_opportunity.distance_from_ath)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.distance_from_52w_high)}>
                      {formatPercent(stock.price_opportunity.distance_from_52w_high)}
                    </td>
                    <td className={movementClass(stock.price_opportunity.distance_from_52w_low)}>
                      {formatPercent(stock.price_opportunity.distance_from_52w_low)}
                    </td>
                    <td>{formatMetric(stock.valuation.pe)}</td>
                    <td>{formatMetric(stock.valuation.forward_pe)}</td>
                    <td>{formatMetric(stock.valuation.peg)}</td>
                    <td>{formatMetric(stock.valuation.price_to_sales)}</td>
                    <td>{formatMetric(stock.valuation.ev_to_ebitda)}</td>
                    <td>{formatPercent(stock.valuation.fcf_yield)}</td>
                  </tr>
                ))}
                {visibleStocks.length === 0 && (
                  <tr>
                    <td colSpan={36} className="empty">
                      No stocks loaded.
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
