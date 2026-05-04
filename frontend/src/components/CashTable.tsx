import type { CashBalance } from "../api";
import { formatMoney } from "../format";

type Props = {
  cash: CashBalance[];
};

export function CashTable({ cash }: Props) {
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
              <th>Currency</th>
              <th>Balance</th>
              <th>Purpose</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {cash.map((item) => (
              <tr key={item.id}>
                <td>{item.platform}</td>
                <td>{item.currency}</td>
                <td>{formatMoney(item.balance, item.currency)}</td>
                <td>{item.purpose}</td>
                <td>{item.source}</td>
              </tr>
            ))}
            {cash.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">No cash balances loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
