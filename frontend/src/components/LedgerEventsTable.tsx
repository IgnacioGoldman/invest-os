import type { BinanceLedgerEvent } from "../api";
import { formatDateTime, formatMoney, formatNumber } from "../format";

type Props = {
  events: BinanceLedgerEvent[];
};

const labelFor = (type: BinanceLedgerEvent["event_type"]) =>
  type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const signedAmount = (event: BinanceLedgerEvent) => {
  if (event.balance_changes && Object.keys(event.balance_changes).length > 0) {
    return Object.entries(event.balance_changes)
      .map(([asset, amount]) => `${amount >= 0 ? "+" : ""}${formatNumber(amount)} ${asset}`)
      .join(", ");
  }
  const sign = event.event_type.includes("withdrawal") ? "-" : "+";
  return `${sign}${formatNumber(event.amount)} ${event.asset}`;
};

export function LedgerEventsTable({ events }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Binance Ledger</h2>
        <span>{events.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Asset</th>
              <th>Amount</th>
              <th>Fee</th>
              <th>Status</th>
              <th>Platform</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td>{formatDateTime(event.created_at)}</td>
                <td>{labelFor(event.event_type)}</td>
                <td><strong>{event.asset}</strong></td>
                <td>{signedAmount(event)}</td>
                <td>{event.fee ? formatMoney(event.fee, event.asset) : "-"}</td>
                <td>{event.status ?? "-"}</td>
                <td>{event.platform}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">No Binance ledger events loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
