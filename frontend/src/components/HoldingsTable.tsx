import type { Holding } from "../api";
import { formatMoney, formatNumber } from "../format";

type Props = {
  title: string;
  holdings: Holding[];
};

export function HoldingsTable({ title, holdings }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span>{holdings.length}</span>
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
              <th>P/L</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => (
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
                <td className={(holding.unrealized_pnl ?? 0) >= 0 ? "positive" : "negative"}>
                  {holding.unrealized_pnl == null ? "-" : formatMoney(holding.unrealized_pnl, holding.currency)}
                </td>
                <td>{holding.confidence}</td>
              </tr>
            ))}
            {holdings.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">No holdings loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
