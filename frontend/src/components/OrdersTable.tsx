import type { Order } from "../api";

type Props = {
  title: string;
  orders: Order[];
};

export function OrdersTable({ title, orders }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span>{orders.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Limit/Price</th>
              <th>Status</th>
              <th>Platform</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id}>
                <td><strong>{order.symbol}</strong></td>
                <td><span className={order.side === "BUY" ? "buy" : "sell"}>{order.side}</span></td>
                <td>{order.order_type ?? "-"}</td>
                <td>{order.quantity}</td>
                <td>{order.limit_price ?? "-"}</td>
                <td>{order.status ?? "-"}</td>
                <td>{order.platform}</td>
              </tr>
            ))}
            {orders.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">No orders loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
