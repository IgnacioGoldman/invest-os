import type { BreakdownItem, CashBalance, DisplayRate, Holding, Order } from "../api";
import { formatMoney } from "../format";

type Props = {
  title: string;
  items: BreakdownItem[];
  currency: string;
  displayRate: number;
  holdings?: Holding[];
  cashBalances?: CashBalance[];
  openOrders?: Order[];
  displayRates?: DisplayRate[];
};

type PlatformSegments = {
  invested: number;
  openOrders: number;
  cash: number;
};

function addValue(values: Map<string, number>, key: string, value?: number | null) {
  if (value == null || !Number.isFinite(value) || value <= 0) return;
  values.set(key, (values.get(key) ?? 0) + value);
}

function inferQuoteCurrency(symbol: string) {
  const normalized = symbol.toUpperCase();
  return ["USDT", "USDC", "FDUSD", "BUSD", "EUR", "USD", "BTC", "ETH"].find(
    (quote) => normalized.endsWith(quote) && normalized.length > quote.length,
  );
}

function rateFromBase(currency: string, displayRates: DisplayRate[]) {
  const normalized = currency.toUpperCase();
  const directRate = displayRates.find((displayRate) => displayRate.currency === normalized)?.rate_from_base;
  if (directRate) return directRate;
  if (["USDT", "USDC", "FDUSD", "BUSD"].includes(normalized)) {
    return displayRates.find((displayRate) => displayRate.currency === "USD")?.rate_from_base;
  }
  return undefined;
}

function orderNotionalInBase(order: Order, displayRates: DisplayRate[]) {
  if (order.side !== "BUY") return 0;

  const amount = order.purchase_amount ?? (
    order.limit_price != null && Number.isFinite(order.limit_price) ? order.limit_price * order.quantity : null
  );
  if (amount == null || !Number.isFinite(amount) || amount <= 0) return 0;

  const quoteCurrency = order.quote_currency ?? order.account_value_currency ?? inferQuoteCurrency(order.symbol);
  if (!quoteCurrency) return 0;

  const rate = rateFromBase(quoteCurrency, displayRates);
  if (!rate || rate <= 0) return 0;

  return amount / rate;
}

function platformSegments(
  platform: string,
  holdings: Holding[],
  cashBalances: CashBalance[],
  openOrders: Order[],
  displayRates: DisplayRate[],
): PlatformSegments {
  const investedByPlatform = new Map<string, number>();
  const cashByPlatform = new Map<string, number>();
  const ordersByPlatform = new Map<string, number>();

  holdings.forEach((holding) => addValue(investedByPlatform, holding.platform, holding.value_in_base));
  cashBalances.forEach((cash) => addValue(cashByPlatform, cash.platform, cash.value_in_base));
  openOrders.forEach((order) => addValue(ordersByPlatform, order.platform, orderNotionalInBase(order, displayRates)));

  const invested = investedByPlatform.get(platform) ?? 0;
  const cash = cashByPlatform.get(platform) ?? 0;
  const openOrderReserve = Math.min(cash, ordersByPlatform.get(platform) ?? 0);

  return {
    invested,
    openOrders: openOrderReserve,
    cash: Math.max(0, cash - openOrderReserve),
  };
}

function segmentWidth(value: number, total: number) {
  if (!total || value <= 0) return "0%";
  return `${Math.max(2, (value / total) * 100)}%`;
}

export function BreakdownTable({
  title,
  items,
  currency,
  displayRate,
  holdings = [],
  cashBalances = [],
  openOrders = [],
  displayRates = [],
}: Props) {
  const showPlatformSegments = holdings.length > 0 || cashBalances.length > 0 || openOrders.length > 0;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      <div className="breakdown-list">
        {items.map((item) => (
          <BreakdownRow
            key={item.name}
            item={item}
            currency={currency}
            displayRate={displayRate}
            segments={
              showPlatformSegments
                ? platformSegments(item.name, holdings, cashBalances, openOrders, displayRates)
                : undefined
            }
          />
        ))}
        {items.length === 0 && <p className="empty block">No breakdown data loaded.</p>}
      </div>
    </section>
  );
}

type BreakdownRowProps = {
  item: BreakdownItem;
  currency: string;
  displayRate: number;
  segments?: PlatformSegments;
};

function BreakdownRow({ item, currency, displayRate, segments }: BreakdownRowProps) {
  const total = item.value;

  return (
    <div className="breakdown-row">
      <div>
        <strong>{item.name}</strong>
        <span>{formatMoney(item.value * displayRate, currency)}</span>
      </div>
      <div>
        <div className="bar" aria-hidden="true" style={{ width: `${Math.max(2, item.percent)}%` }}>
          {segments ? (
            <>
              <span className="bar-segment invested" style={{ width: segmentWidth(segments.invested, total) }} />
              <span className="bar-segment open-orders" style={{ width: segmentWidth(segments.openOrders, total) }} />
              <span className="bar-segment cash" style={{ width: segmentWidth(segments.cash, total) }} />
            </>
          ) : (
            <span className="bar-segment invested" style={{ width: "100%" }} />
          )}
        </div>
        {segments && (
          <div className="breakdown-segments">
            <span className="segment-label invested">Invested {formatMoney(segments.invested * displayRate, currency)}</span>
            <span className="segment-label open-orders">
              Open orders {formatMoney(segments.openOrders * displayRate, currency)}
            </span>
            <span className="segment-label cash">Cash {formatMoney(segments.cash * displayRate, currency)}</span>
          </div>
        )}
      </div>
      <em>{item.percent.toFixed(1)}%</em>
    </div>
  );
}
