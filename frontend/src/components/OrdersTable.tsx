import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import type { CashBalance, Order } from "../api";
import { formatDateTime, formatMoney, formatNumber } from "../format";

type Props = {
  title: string;
  orders: Order[];
  cashBalances?: CashBalance[];
};

type OrderGroup = {
  key: string;
  date?: string | null;
  symbol: string;
  side: "BUY" | "SELL";
  orderType?: string | null;
  quantity: number;
  averagePrice?: number | null;
  quoteCurrency?: string | null;
  purchaseAmount?: number | null;
  costBasisAmount?: number | null;
  currentValue?: number | null;
  roiPercent?: number | null;
  realizedPnl?: number | null;
  realizedRoiPercent?: number | null;
  unrealizedPnl?: number | null;
  unrealizedRoiPercent?: number | null;
  remainingQuantity?: number | null;
  remainingCostBasis?: number | null;
  accountValueBefore?: number | null;
  accountValueAfter?: number | null;
  accountValueCurrency?: string | null;
  accountValueSource?: string | null;
  accountValueWarning?: string | null;
  status?: string | null;
  positionStatus?: string | null;
  platform: string;
  valuationSource?: string | null;
  fills: Order[];
};

const valueAsString = (value: unknown) => {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return null;
};

const minuteKey = (value?: string | null) => {
  if (!value) {
    return "unknown-time";
  }
  return value.slice(0, 16);
};

const rawOrderId = (order: Order) => valueAsString(order.raw.orderId) ?? valueAsString(order.raw.order_id);

const asNumber = (value: unknown) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const splitPair = (symbol: string) => {
  const upper = symbol.toUpperCase();
  const quote = ["USDT", "USDC", "FDUSD", "EUR", "USD", "BTC", "ETH"].find(
    (item) => upper.endsWith(item) && upper.length > item.length,
  );
  return quote ? [upper.slice(0, -quote.length), quote] : [upper, null];
};

const remainingQuantityFor = (order: Order) => {
  const executed = asNumber(order.raw.executedQty);
  const rawRemaining = asNumber(order.raw.origQty) - executed;
  return rawRemaining > 0 ? rawRemaining : order.quantity;
};

const remainingNotionalFor = (order: Order) => {
  const [_base, pairQuote] = splitPair(order.symbol);
  const quote = order.quote_currency ?? pairQuote;
  if (!quote || order.limit_price == null) {
    return null;
  }
  return { currency: quote, amount: remainingQuantityFor(order) * order.limit_price };
};

const historyGroupKey = (order: Order) =>
  [order.source, order.platform, order.symbol, order.side, rawOrderId(order) ?? minuteKey(order.created_at)].join("|");

const addNullable = (left?: number | null, right?: number | null) =>
  left == null && right == null ? null : (left ?? 0) + (right ?? 0);

const normalizeStatus = (status?: string | null) => status?.replace(/_/g, " ") ?? null;

const isOrderGroup = (row: Order | OrderGroup): row is OrderGroup => "fills" in row;

const mergePositionStatus = (side: "BUY" | "SELL", statuses: Array<string | null | undefined>) => {
  const unique = Array.from(new Set(statuses.filter(Boolean))) as string[];
  if (unique.length === 0) {
    return null;
  }
  if (unique.length === 1) {
    return unique[0];
  }
  if (side === "BUY") {
    return unique.every((status) => status === "closed") ? "closed" : "partial";
  }
  return unique.some((status) => status.includes("unmatched")) ? "partial_unmatched" : "realized";
};

const realizedPnlFor = (row: Order | OrderGroup) => (isOrderGroup(row) ? row.realizedPnl : row.realized_pnl) ?? null;

const unrealizedPnlFor = (row: Order | OrderGroup) =>
  (isOrderGroup(row) ? row.unrealizedPnl : row.unrealized_pnl) ?? null;

const realizedRoiFor = (row: Order | OrderGroup) =>
  (isOrderGroup(row) ? row.realizedRoiPercent : row.realized_roi_percent) ?? null;

const unrealizedRoiFor = (row: Order | OrderGroup) =>
  (isOrderGroup(row) ? row.unrealizedRoiPercent : row.unrealized_roi_percent) ?? null;

const remainingCostBasisFor = (row: Order | OrderGroup) =>
  (isOrderGroup(row) ? row.remainingCostBasis : row.remaining_cost_basis) ?? null;

const pnlFor = (row: Order | OrderGroup) => (row.side === "SELL" ? realizedPnlFor(row) : unrealizedPnlFor(row));

const roiFor = (row: Order | OrderGroup) => (row.side === "SELL" ? realizedRoiFor(row) : unrealizedRoiFor(row));

const costBasisFor = (row: Order | OrderGroup) =>
  row.side === "SELL"
    ? (isOrderGroup(row) ? row.costBasisAmount : row.cost_basis_amount) ?? null
    : remainingCostBasisFor(row);

const statusFor = (row: Order | OrderGroup) =>
  isOrderGroup(row) ? row.positionStatus ?? row.status : row.position_status ?? row.status;

const roiLabelFor = (row: Order | OrderGroup) => {
  if (roiFor(row) == null) {
    return null;
  }
  return row.side === "SELL" ? "realized" : "unrealized";
};

const accountValueLabel = (value?: number | null, currency?: string | null, warning?: string | null) => {
  if (value == null || !currency) {
    return (
      <>
        <span>Unavailable</span>
        {warning && <small title={warning}>hover for reason</small>}
      </>
    );
  }
  return (
    <>
      {formatMoney(value, currency)}
      <small>{warning ? "estimated, warning" : "estimated"}</small>
    </>
  );
};

const groupHistoryOrders = (orders: Order[]): OrderGroup[] => {
  const groups = new Map<string, OrderGroup>();

  orders.forEach((order) => {
    const key = historyGroupKey(order);
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        key,
        date: order.created_at,
        symbol: order.symbol,
        side: order.side,
        orderType: order.order_type,
        quantity: order.quantity,
        averagePrice: order.limit_price,
        quoteCurrency: order.quote_currency,
        purchaseAmount: order.purchase_amount,
        costBasisAmount: order.cost_basis_amount,
        currentValue: order.current_value,
        roiPercent: order.roi_percent,
        realizedPnl: order.realized_pnl,
        realizedRoiPercent: order.realized_roi_percent,
        unrealizedPnl: order.unrealized_pnl,
        unrealizedRoiPercent: order.unrealized_roi_percent,
        remainingQuantity: order.remaining_quantity,
        remainingCostBasis: order.remaining_cost_basis,
        accountValueBefore: order.account_value_before,
        accountValueAfter: order.account_value_after,
        accountValueCurrency: order.account_value_currency,
        accountValueSource: order.account_value_source,
        accountValueWarning: order.account_value_warning,
        status: order.status,
        positionStatus: order.position_status,
        platform: order.platform,
        valuationSource: order.valuation_source,
        fills: [order],
      });
      return;
    }

    existing.fills.push(order);
    existing.quantity += order.quantity;
    existing.purchaseAmount = addNullable(existing.purchaseAmount, order.purchase_amount);
    existing.costBasisAmount = addNullable(existing.costBasisAmount, order.cost_basis_amount);
    existing.currentValue = addNullable(existing.currentValue, order.current_value);
    existing.realizedPnl = addNullable(existing.realizedPnl, order.realized_pnl);
    existing.unrealizedPnl = addNullable(existing.unrealizedPnl, order.unrealized_pnl);
    existing.remainingQuantity = addNullable(existing.remainingQuantity, order.remaining_quantity);
    existing.remainingCostBasis = addNullable(existing.remainingCostBasis, order.remaining_cost_basis);
    existing.date = existing.date && order.created_at && order.created_at < existing.date ? order.created_at : existing.date;
    existing.status = existing.status === order.status ? existing.status : "FILLED";
    existing.positionStatus = mergePositionStatus(existing.side, [...existing.fills.map((fill) => fill.position_status)]);
    if (!existing.valuationSource && order.valuation_source) {
      existing.valuationSource = order.valuation_source;
    }
  });

  return Array.from(groups.values())
    .map((group) => {
      const fills = [...group.fills].sort((a, b) => String(a.created_at ?? "").localeCompare(String(b.created_at ?? "")));
      const firstFill = fills[0];
      const lastFill = fills[fills.length - 1];
      const averagePrice =
        group.purchaseAmount != null && group.purchaseAmount > 0 && group.quantity > 0
          ? group.purchaseAmount / group.quantity
          : group.averagePrice;
      const realizedRoiPercent =
        group.realizedPnl != null && group.costBasisAmount != null && group.costBasisAmount > 0
          ? (group.realizedPnl / group.costBasisAmount) * 100
          : null;
      const unrealizedRoiPercent =
        group.unrealizedPnl != null && group.remainingCostBasis != null && group.remainingCostBasis > 0
          ? (group.unrealizedPnl / group.remainingCostBasis) * 100
          : null;
      const roiPercent = group.side === "SELL" ? realizedRoiPercent : unrealizedRoiPercent;
      return {
        ...group,
        fills,
        averagePrice,
        realizedRoiPercent,
        unrealizedRoiPercent,
        roiPercent,
        accountValueBefore: firstFill?.account_value_before ?? group.accountValueBefore,
        accountValueAfter: lastFill?.account_value_after ?? group.accountValueAfter,
        accountValueCurrency: firstFill?.account_value_currency ?? group.accountValueCurrency,
        accountValueSource: firstFill?.account_value_source ?? group.accountValueSource,
        accountValueWarning: firstFill?.account_value_warning ?? group.accountValueWarning,
      };
    })
    .sort((a, b) => String(b.date ?? "").localeCompare(String(a.date ?? "")));
};

export function OrdersTable({ title, orders, cashBalances = [] }: Props) {
  const isHistory = title.toLowerCase().includes("history");
  const accountValueHeading =
    orders.length > 0 && orders.every((order) => order.source === "binance") ? "Binance Value" : "Account Value";
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const groupedOrders = useMemo(() => (isHistory ? groupHistoryOrders(orders) : []), [isHistory, orders]);
  const openOrderReserves = useMemo(() => {
    const reserves: Record<string, number> = {};
    if (isHistory) {
      return reserves;
    }
    orders.forEach((order) => {
      if (order.side !== "BUY") {
        return;
      }
      const remaining = remainingNotionalFor(order);
      if (!remaining) {
        return;
      }
      reserves[remaining.currency] = (reserves[remaining.currency] ?? 0) + remaining.amount;
    });
    return reserves;
  }, [isHistory, orders]);
  const relevantCash = cashBalances.filter(
    (cash) => cash.balance > 0 || openOrderReserves[cash.currency.toUpperCase()] != null,
  );

  const toggle = (key: string) => {
    setExpanded((current) => ({ ...current, [key]: !current[key] }));
  };

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
              {isHistory && <th>Date</th>}
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              {!isHistory && <th>Remaining</th>}
              {!isHistory && <th>Remaining Notional</th>}
              <th>Limit/Price</th>
              {isHistory && <th>Amount</th>}
              {isHistory && <th>Cost Basis</th>}
              {isHistory && <th>Current</th>}
              {isHistory && <th>P/L</th>}
              {isHistory && <th>ROI</th>}
              {isHistory && <th>{accountValueHeading} Before</th>}
              {isHistory && <th>{accountValueHeading} After</th>}
              <th>Status</th>
              <th>Platform</th>
            </tr>
          </thead>
          <tbody>
            {!isHistory &&
              orders.map((order) => (
                <tr key={order.id}>
                  <td><strong>{order.symbol}</strong></td>
                  <td><span className={order.side === "BUY" ? "buy" : "sell"}>{order.side}</span></td>
                  <td>{order.order_type ?? "-"}</td>
                  <td>{formatNumber(order.quantity)}</td>
                  <td>{formatNumber(remainingQuantityFor(order))}</td>
                  <td>
                    {(() => {
                      const remaining = remainingNotionalFor(order);
                      return remaining ? formatMoney(remaining.amount, remaining.currency) : "-";
                    })()}
                  </td>
                  <td>{order.limit_price == null ? "-" : formatNumber(order.limit_price)}</td>
                  <td>{order.status ?? "-"}</td>
                  <td>{order.platform}</td>
                </tr>
              ))}

            {isHistory &&
              groupedOrders.map((group) => (
                <Fragment key={group.key}>
                  <tr>
                    <td>{formatDateTime(group.date)}</td>
                    <td>
                      <button type="button" className="icon-button row-toggle" onClick={() => toggle(group.key)} title="Show fills">
                        {expanded[group.key] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </button>
                      <strong>{group.symbol}</strong>
                      <small>{group.fills.length} fill{group.fills.length === 1 ? "" : "s"}</small>
                    </td>
                    <td><span className={group.side === "BUY" ? "buy" : "sell"}>{group.side}</span></td>
                    <td>{group.orderType ?? "-"}</td>
                    <td>{formatNumber(group.quantity)}</td>
                    <td>{group.averagePrice == null ? "-" : formatNumber(group.averagePrice)}</td>
                    <td>
                      {group.purchaseAmount == null || !group.quoteCurrency
                        ? "-"
                        : formatMoney(group.purchaseAmount, group.quoteCurrency)}
                    </td>
                    <td>
                      {costBasisFor(group) == null || !group.quoteCurrency
                        ? "-"
                        : formatMoney(costBasisFor(group) ?? 0, group.quoteCurrency)}
                    </td>
                    <td>
                      {group.currentValue == null || !group.quoteCurrency
                        ? "-"
                        : formatMoney(group.currentValue, group.quoteCurrency)}
                      {group.valuationSource && <small>{group.valuationSource}</small>}
                    </td>
                    <td className={(pnlFor(group) ?? 0) >= 0 ? "positive" : "negative"}>
                      {pnlFor(group) == null || !group.quoteCurrency ? "-" : formatMoney(pnlFor(group) ?? 0, group.quoteCurrency)}
                    </td>
                    <td className={(roiFor(group) ?? 0) >= 0 ? "positive" : "negative"}>
                      {roiFor(group) == null ? "-" : `${roiFor(group)?.toFixed(2)}%`}
                      {roiLabelFor(group) && <small>{roiLabelFor(group)}</small>}
                    </td>
                    <td title={group.accountValueWarning ?? undefined}>
                      {accountValueLabel(group.accountValueBefore, group.accountValueCurrency, group.accountValueWarning)}
                    </td>
                    <td title={group.accountValueWarning ?? undefined}>
                      {accountValueLabel(group.accountValueAfter, group.accountValueCurrency, group.accountValueWarning)}
                    </td>
                    <td>{normalizeStatus(statusFor(group)) ?? "-"}</td>
                    <td>{group.platform}</td>
                  </tr>
                  {expanded[group.key] &&
                    group.fills.map((order, index) => (
                      <tr className="child-row" key={`${group.key}-${order.id}-${index}`}>
                        <td>{formatDateTime(order.created_at)}</td>
                        <td><span>{order.symbol}</span></td>
                        <td><span className={order.side === "BUY" ? "buy" : "sell"}>{order.side}</span></td>
                        <td>{order.order_type ?? "-"}</td>
                        <td>{formatNumber(order.quantity)}</td>
                        <td>{order.limit_price == null ? "-" : formatNumber(order.limit_price)}</td>
                        <td>
                          {order.purchase_amount == null || !order.quote_currency
                            ? "-"
                            : formatMoney(order.purchase_amount, order.quote_currency)}
                        </td>
                        <td>
                          {costBasisFor(order) == null || !order.quote_currency
                            ? "-"
                            : formatMoney(costBasisFor(order) ?? 0, order.quote_currency)}
                        </td>
                        <td>
                          {order.current_value == null || !order.quote_currency
                            ? "-"
                            : formatMoney(order.current_value, order.quote_currency)}
                        </td>
                        <td className={(pnlFor(order) ?? 0) >= 0 ? "positive" : "negative"}>
                          {pnlFor(order) == null || !order.quote_currency ? "-" : formatMoney(pnlFor(order) ?? 0, order.quote_currency)}
                        </td>
                        <td className={(roiFor(order) ?? 0) >= 0 ? "positive" : "negative"}>
                          {roiFor(order) == null ? "-" : `${roiFor(order)?.toFixed(2)}%`}
                          {roiLabelFor(order) && <small>{roiLabelFor(order)}</small>}
                        </td>
                        <td title={order.account_value_warning ?? undefined}>
                          {accountValueLabel(order.account_value_before, order.account_value_currency, order.account_value_warning)}
                        </td>
                        <td title={order.account_value_warning ?? undefined}>
                          {accountValueLabel(order.account_value_after, order.account_value_currency, order.account_value_warning)}
                        </td>
                        <td>{normalizeStatus(statusFor(order)) ?? "-"}</td>
                        <td>{order.platform}</td>
                      </tr>
                    ))}
                </Fragment>
              ))}
            {(isHistory ? groupedOrders.length : orders.length) === 0 && (
              <tr>
                <td colSpan={isHistory ? 15 : 9} className="empty">No orders loaded.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!isHistory && relevantCash.length > 0 && (
        <div className="open-order-summary">
          {relevantCash.map((cash) => {
            const currency = cash.currency.toUpperCase();
            const reserved = openOrderReserves[currency] ?? 0;
            const availableAfterOrders = cash.balance - reserved;
            return (
              <div className="open-order-summary-row" key={cash.id}>
                <strong>{currency} Cash</strong>
                <span>{formatMoney(cash.balance, currency)}</span>
                <small>open orders {formatMoney(reserved, currency)}</small>
                <small>remaining {formatMoney(availableAfterOrders, currency)}</small>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
