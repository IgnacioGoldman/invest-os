import type { BreakdownItem } from "../api";
import { formatMoney } from "../format";

type Props = {
  title: string;
  items: BreakdownItem[];
  currency: string;
  displayRate: number;
};

export function BreakdownTable({ title, items, currency, displayRate }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      <div className="breakdown-list">
        {items.map((item) => (
          <div className="breakdown-row" key={item.name}>
            <div>
              <strong>{item.name}</strong>
              <span>{formatMoney(item.value * displayRate, currency)}</span>
            </div>
            <div className="bar" aria-hidden="true">
              <span style={{ width: `${Math.max(2, item.percent)}%` }} />
            </div>
            <em>{item.percent.toFixed(1)}%</em>
          </div>
        ))}
        {items.length === 0 && <p className="empty block">No breakdown data loaded.</p>}
      </div>
    </section>
  );
}
