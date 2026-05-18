import type { CashBalance } from "../api";
import { formatMoney, formatNumber } from "../format";

type Props = {
  cash: CashBalance[];
  displayCurrency: string;
  displayRate: number;
};

export function CashTable({ cash, displayCurrency, displayRate }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Cash</h2>
        <span>{cash.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Platform</th>
              <th>Display Value</th>
              <th>Native Balance</th>
              <th>Currency</th>
              <th>Purpose</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {cash.map((item) => (
              <tr key={item.id}>
                <td>{item.platform}</td>
                <td>{item.value_in_base == null ? "-" : formatMoney(item.value_in_base * displayRate, displayCurrency)}</td>
                <td>
                  <strong>{formatNumber(item.balance)}</strong>
                  <small>{formatMoney(item.balance, item.currency)}</small>
                </td>
                <td>{item.currency}</td>
                <td>{item.purpose}</td>
                <td>{item.source}</td>
              </tr>
            ))}
            {cash.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">No cash balances loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
