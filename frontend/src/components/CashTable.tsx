import { memo } from "react";
import type { CashBalance } from "../api";
import { HIDDEN_ABSOLUTE_VALUE, formatMoneyPrivacy, formatNumber } from "../format";

type Props = {
  cash: CashBalance[];
  displayCurrency: string;
  displayRate: number;
  hideAbsoluteValues?: boolean;
};

export const CashTable = memo(function CashTable({
  cash,
  displayCurrency,
  displayRate,
  hideAbsoluteValues = false,
}: Props) {
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
                <td>{item.value_in_base == null ? "-" : formatMoneyPrivacy(item.value_in_base * displayRate, displayCurrency, hideAbsoluteValues)}</td>
                <td>
                  <strong>{hideAbsoluteValues ? HIDDEN_ABSOLUTE_VALUE : formatNumber(item.balance)}</strong>
                  <small>{formatMoneyPrivacy(item.balance, item.currency, hideAbsoluteValues)}</small>
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
});
