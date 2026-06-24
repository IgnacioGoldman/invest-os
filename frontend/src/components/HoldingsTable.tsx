import type { Holding } from "../api";
import { formatDateTime, formatMoney, formatNumber } from "../format";

type Props = {
  title: string;
  holdings: Holding[];
  displayCurrency: string;
  displayRate: number;
};

const formatPercent = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);

function pnlPercent(holding: Holding) {
  if (holding.unrealized_pnl == null || holding.cost_basis == null || holding.cost_basis <= 0) {
    return null;
  }
  return (holding.unrealized_pnl / holding.cost_basis) * 100;
}

export function HoldingsTable({ title, holdings, displayCurrency, displayRate }: Props) {
  const aggregate = holdings.reduce(
    (totals, holding) => {
      if (holding.value_in_base == null || holding.cost_basis == null || holding.market_value === 0) {
        return totals;
      }
      const valueToBaseRate = holding.value_in_base / holding.market_value;
      const costBasisInBase = holding.cost_basis * valueToBaseRate;
      totals.value += holding.value_in_base;
      totals.costBasis += costBasisInBase;
      return totals;
    },
    { value: 0, costBasis: 0 },
  );
  const aggregatePnl = aggregate.costBasis > 0 ? aggregate.value - aggregate.costBasis : null;
  const aggregateRoi = aggregatePnl == null ? null : (aggregatePnl / aggregate.costBasis) * 100;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <div className="panel-heading-meta">
          {aggregatePnl != null && (
            <strong className={aggregatePnl >= 0 ? "positive" : "negative"}>
              {formatMoney(aggregatePnl * displayRate, displayCurrency)}
              <small>{aggregateRoi == null ? "" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(aggregateRoi)}%`}</small>
            </strong>
          )}
          <span>{holdings.length}</span>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Platform</th>
              <th>Class</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Value</th>
              <th>Display Value</th>
              <th>Valuation</th>
              <th>P/L</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => {
              const roiPercent = pnlPercent(holding);
              return (
                <tr key={holding.id}>
                  <td>
                    <strong>{holding.symbol}</strong>
                    <small>{holding.name}</small>
                  </td>
                  <td>{holding.platform}</td>
                  <td>{holding.asset_class}</td>
                  <td>{formatNumber(holding.quantity)}</td>
                  <td>{holding.current_price == null ? "-" : formatMoney(holding.current_price, holding.currency)}</td>
                  <td>{formatMoney(holding.market_value, holding.currency)}</td>
                  <td>{holding.value_in_base == null ? "-" : formatMoney(holding.value_in_base * displayRate, displayCurrency)}</td>
                  <td>
                    <span>{holding.valuation_source ?? "-"}</span>
                    <small>{formatDateTime(holding.valuation_timestamp)}</small>
                  </td>
                  <td className={(holding.unrealized_pnl ?? 0) >= 0 ? "positive" : "negative"}>
                    {holding.unrealized_pnl == null ? (
                      "-"
                    ) : (
                      <>
                        {formatMoney(holding.unrealized_pnl, holding.currency)}
                        {roiPercent != null && <small>{formatPercent(roiPercent)}%</small>}
                      </>
                    )}
                  </td>
                  <td>{holding.confidence}</td>
                </tr>
              );
            })}
            {holdings.length === 0 && (
              <tr>
                <td colSpan={10} className="empty">No holdings loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
