import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { Fragment, memo, useMemo, useState, type ReactNode } from "react";
import type { BinanceLedgerEvent, Order } from "../api";
import { formatDateTime, formatMoney } from "../format";

type Props = {
  orders: Order[];
  events: BinanceLedgerEvent[];
  emptyLabel?: string;
  title?: string;
  controls?: ReactNode;
  compact?: boolean;
  endTimestamp?: string | null;
  currentBalances?: Record<string, number>;
  currentAssetValues?: Record<string, number>;
};

type ActivityRow = {
  id: string;
  createdAt?: string | null;
  action: string;
  actionKey: string;
  asset: string;
  amount: string;
  status?: string | null;
  balanceChanges: Record<string, number>;
  walletValueBefore?: number | null;
  walletValueAfter?: number | null;
  walletValueCurrency?: string | null;
  walletValueWarning?: string | null;
  balancesAfter?: Record<string, number>;
  assetValuesAfter?: Record<string, number>;
  purchasePrice?: number | null;
  sellPrice?: number | null;
  priceCurrency?: string | null;
  priceAsset?: string | null;
  priceQuantity?: number | null;
  purchasePriceBasis?: number | null;
  sellPriceProceeds?: number | null;
  pnl?: number | null;
  roiPercent?: number | null;
  pnlCurrency?: string | null;
  pnlBasis?: number | null;
  pnlLabel?: "realized" | "unrealized";
  quantityAsset?: string | null;
  openQuantity?: number | null;
  realizedQuantity?: number | null;
  note?: string | null;
  fills?: ActivityRow[];
};

const QUOTES = ["USDT", "USDC", "FDUSD", "EUR", "USD", "BTC", "ETH"];
const FIAT_OR_STABLE_ASSETS = new Set([
  "USD",
  "USDT",
  "USDC",
  "FDUSD",
  "EUR",
  "GBP",
  "CHF",
  "SEK",
  "NOK",
  "DKK",
  "CAD",
  "AUD",
  "NZD",
  "JPY",
]);
const EPSILON = 0.00000001;
const ACTIVITY_PAGE_SIZE = 75;
const assetAmountFormatters = new Map<string, Intl.NumberFormat>();
const percentFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const compactPercentFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const compactDateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

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
  const quote = QUOTES.find((item) => upper.endsWith(item) && upper.length > item.length);
  return quote ? [upper.slice(0, -quote.length), quote] : [upper, null];
};

const quoteAmountFor = (order: Order) => {
  const rawQuote = asNumber(order.raw.quoteQty);
  if (rawQuote > 0) {
    return rawQuote;
  }
  if (order.purchase_amount != null) {
    return order.purchase_amount;
  }
  if (order.limit_price != null) {
    return order.quantity * order.limit_price;
  }
  return 0;
};

const addChange = (changes: Record<string, number>, asset?: string | null, amount = 0) => {
  if (!asset || Math.abs(amount) <= EPSILON) {
    return;
  }
  const key = asset.toUpperCase();
  changes[key] = (changes[key] ?? 0) + amount;
};

const orderChanges = (order: Order) => {
  const changes: Record<string, number> = {};
  const [base, pairQuote] = splitPair(order.symbol);
  const quote = pairQuote ?? order.quote_currency ?? null;
  const quoteAmount = quoteAmountFor(order);

  if (order.side === "BUY") {
    addChange(changes, base, order.quantity);
    addChange(changes, quote, -quoteAmount);
  } else {
    addChange(changes, base, -order.quantity);
    addChange(changes, quote, quoteAmount);
  }

  const commissionAsset = typeof order.raw.commissionAsset === "string" ? order.raw.commissionAsset : null;
  addChange(changes, commissionAsset, -Math.abs(asNumber(order.raw.commission)));
  return changes;
};

const valueAsString = (value: unknown) => {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return null;
};

const minuteKey = (value?: string | null) => value?.slice(0, 16) ?? "unknown-time";

const rawOrderId = (order: Order) =>
  valueAsString(order.raw.orderId) ??
  valueAsString(order.raw.order_id) ??
  valueAsString(order.raw.ibOrderID) ??
  valueAsString(order.raw.orderID);

const orderGroupKey = (order: Order) =>
  [order.source, order.platform, order.symbol, order.side, rawOrderId(order) ?? minuteKey(order.created_at)].join("|");

const formatAssetAmount = (asset: string, value: number) => {
  const upper = asset.toUpperCase();
  const formatterKey = FIAT_OR_STABLE_ASSETS.has(upper) ? "fiat" : "asset";
  const cached = assetAmountFormatters.get(formatterKey);
  if (cached) {
    return cached.format(value);
  }
  const formatter = new Intl.NumberFormat(
    undefined,
    FIAT_OR_STABLE_ASSETS.has(upper)
      ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { maximumFractionDigits: 10 },
  );
  assetAmountFormatters.set(formatterKey, formatter);
  return formatter.format(value);
};

const signedAssetAmount = (asset: string, amount: number) =>
  `${amount >= 0 ? "+" : ""}${formatAssetAmount(asset, amount)}`;

const formatAssetValue = (asset: string, value: number) => `${formatAssetAmount(asset, value)} ${asset}`;

const orderLotQuantities = (order: Order) => {
  const [base] = splitPair(order.symbol);
  if (order.side !== "BUY") {
    return { quantityAsset: base, openQuantity: null, realizedQuantity: null };
  }
  const commissionAsset = typeof order.raw.commissionAsset === "string" ? order.raw.commissionAsset.toUpperCase() : null;
  const commissionAmount = Math.abs(asNumber(order.raw.commission));
  const netQuantity = commissionAsset === base ? Math.max(order.quantity - commissionAmount, 0) : order.quantity;
  const openQuantity = order.remaining_quantity ?? null;
  const realizedQuantity = openQuantity == null ? null : Math.max(netQuantity - openQuantity, 0);
  return { quantityAsset: base, openQuantity, realizedQuantity };
};

const orderNetAmounts = (order: Order) => {
  const [base, pairQuote] = splitPair(order.symbol);
  const quote = pairQuote ?? order.quote_currency ?? null;
  const commissionAsset = typeof order.raw.commissionAsset === "string" ? order.raw.commissionAsset.toUpperCase() : null;
  const commissionAmount = Math.abs(asNumber(order.raw.commission));
  let baseQuantity = order.quantity;
  let quoteAmount = quoteAmountFor(order);

  if (order.side === "BUY") {
    if (commissionAsset === base) {
      baseQuantity -= commissionAmount;
    }
    if (commissionAsset === quote) {
      quoteAmount += commissionAmount;
    }
  } else {
    if (commissionAsset === base) {
      baseQuantity += commissionAmount;
    }
    if (commissionAsset === quote) {
      quoteAmount -= commissionAmount;
    }
  }

  return {
    base,
    quote,
    baseQuantity: Math.max(baseQuantity, 0),
    quoteAmount,
  };
};

const orderPriceDetails = (order: Order) => {
  const { base, quote, baseQuantity, quoteAmount } = orderNetAmounts(order);
  const apiPrice = asNumber(order.raw.price) || order.limit_price || null;
  const grossQuantity = order.quantity;
  const grossQuoteAmount = quoteAmountFor(order);
  const purchasePriceBasis = order.side === "SELL" ? order.cost_basis_amount ?? null : grossQuoteAmount;
  const sellPriceProceeds =
    order.side === "SELL"
      ? apiPrice != null && baseQuantity > EPSILON
        ? apiPrice * baseQuantity
        : quoteAmount
      : null;
  const priceQuantity = order.side === "SELL" ? baseQuantity : grossQuantity;
  return {
    priceCurrency: quote,
    priceAsset: base,
    priceQuantity,
    purchasePriceBasis,
    sellPriceProceeds,
    purchasePrice:
      order.side === "BUY" && apiPrice != null
        ? apiPrice
        : purchasePriceBasis != null && priceQuantity > EPSILON
          ? purchasePriceBasis / priceQuantity
          : null,
    sellPrice: sellPriceProceeds != null && priceQuantity > EPSILON ? sellPriceProceeds / priceQuantity : null,
  };
};

const orderDisplayPnl = (order: Order) =>
  order.side === "SELL" ? order.realized_pnl : order.unrealized_pnl ?? order.realized_pnl;

const orderDisplayRoi = (order: Order) =>
  order.side === "SELL" ? order.realized_roi_percent : order.unrealized_roi_percent ?? order.realized_roi_percent;

const orderDisplayPnlBasis = (order: Order) =>
  order.side === "SELL"
    ? order.cost_basis_amount
    : order.unrealized_pnl != null
      ? order.remaining_cost_basis
      : order.cost_basis_amount;

const orderDisplayPnlLabel = (order: Order): "realized" | "unrealized" =>
  order.side === "SELL" || (order.unrealized_pnl == null && order.realized_pnl != null) ? "realized" : "unrealized";

const eventChanges = (event: BinanceLedgerEvent) => {
  if (event.balance_changes && Object.keys(event.balance_changes).length > 0) {
    return event.balance_changes;
  }
  if (event.event_type === "transfer") {
    return {};
  }
  const amount = event.event_type.includes("withdrawal") ? -(event.amount + event.fee) : event.amount;
  return { [event.asset]: amount };
};

const eventLabel = (event: BinanceLedgerEvent) => {
  if (event.event_type === "start") {
    return "Start";
  }
  if (event.event_type === "transfer" && typeof event.raw.type === "string") {
    return event.raw.type.replace(/_/g, " -> ");
  }
  return event.event_type.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
};

const actionKeyFor = (action: string) => action.toLowerCase().replace(/\s+/g, "_");

const actionLabelFor = (actionKey: string) =>
  actionKey.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

const signedAmount = (asset: string, amount: number) => `${signedAssetAmount(asset, amount)} ${asset}`;

const changesLabel = (changes: Record<string, number>) => {
  const entries = Object.entries(changes).filter(([, amount]) => Math.abs(amount) > EPSILON);
  return entries.length ? entries.map(([asset, amount]) => signedAmount(asset, amount)).join(", ") : "-";
};

const mergeChanges = (rows: ActivityRow[]) => {
  const merged: Record<string, number> = {};
  rows.forEach((row) => {
    Object.entries(row.balanceChanges).forEach(([asset, amount]) => {
      addChange(merged, asset, amount);
    });
  });
  return merged;
};

const sumNullable = (values: Array<number | null | undefined>) => {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) : null;
};

const formatPercent = (value: number) => percentFormatter.format(value);

const walletValueLabel = (row: ActivityRow) => {
  if (
    row.walletValueAfter == null ||
    row.walletValueAfter < 0 ||
    !row.walletValueCurrency
  ) {
    return row.walletValueWarning ? <span title={row.walletValueWarning}>Unavailable</span> : "-";
  }
  return (
    <span title={row.walletValueWarning ?? undefined}>
      {formatAssetValue(row.walletValueCurrency, row.walletValueAfter)}
      <small>{walletValueNote(row.walletValueWarning)}</small>
    </span>
  );
};

const walletValueNote = (warning?: string | null) => {
  if (!warning) {
    return "estimated";
  }
  if (warning.includes("Inferred")) {
    return "inferred";
  }
  if (warning.includes("negative")) {
    return "estimated, partial history";
  }
  if (warning.includes("nearest")) {
    return "estimated, nearest price";
  }
  if (warning.includes("missing historical")) {
    return "estimated, missing price";
  }
  return "estimated, review";
};

const balancesLabel = (balances?: Record<string, number>) => {
  const entries = Object.entries(balances ?? {})
    .filter(([, amount]) => amount > EPSILON)
    .sort(([left], [right]) => left.localeCompare(right));
  if (entries.length === 0) {
    return "-";
  }

  const label = entries.map(([asset, amount]) => `${formatAssetAmount(asset, amount)} ${asset}`).join(", ");
  return (
    <div className="asset-list" title={label}>
      {entries.map(([asset, amount]) => (
        <span key={asset}>
          <strong>{asset}</strong>
          <em>{formatAssetAmount(asset, amount)}</em>
        </span>
      ))}
    </div>
  );
};

const assetValuesLabel = (values?: Record<string, number>) => {
  const entries = Object.entries(values ?? {})
    .filter(([, value]) => Math.abs(value) > EPSILON)
    .sort(([left], [right]) => left.localeCompare(right));
  if (entries.length === 0) {
    return "-";
  }

  const label = entries.map(([asset, value]) => `${asset}: ${formatAssetAmount("USDT", value)} USDT`).join(", ");
  return (
    <div className="asset-list value-list" title={label}>
      {entries.map(([asset, value]) => (
        <span key={asset}>
          <strong>{asset}</strong>
          <em>{formatAssetAmount("USDT", value)} USDT</em>
        </span>
      ))}
    </div>
  );
};

const changesList = (changes: Record<string, number>, fallback = "-") => {
  const entries = Object.entries(changes).filter(([, amount]) => Math.abs(amount) > EPSILON);
  if (entries.length === 0) {
    return fallback;
  }
  const label = entries.map(([asset, amount]) => signedAmount(asset, amount)).join(", ");
  return (
    <div className="asset-list change-list" title={label}>
      {entries.map(([asset, amount]) => (
        <span key={asset}>
          <strong>{asset}</strong>
          <em>{signedAssetAmount(asset, amount)}</em>
        </span>
      ))}
    </div>
  );
};

const purchasePriceLabel = (row: ActivityRow) => {
  if (row.purchasePrice == null || !row.priceCurrency || !row.priceAsset) {
    return "-";
  }
  return (
    <span>
      {formatAssetValue(row.priceCurrency, row.purchasePrice)} / {row.priceAsset}
      {row.sellPrice != null && (
        <small>sold at {formatAssetValue(row.priceCurrency, row.sellPrice)} / {row.priceAsset}</small>
      )}
    </span>
  );
};

const pnlLabel = (row: ActivityRow) => {
  if (row.pnl == null || !row.pnlCurrency) {
    return "-";
  }
  return (
    <span className={row.pnl >= 0 ? "positive" : "negative"}>
      {formatAssetValue(row.pnlCurrency, row.pnl)}
      {row.pnlLabel && <small>{row.pnlLabel}</small>}
      {row.realizedQuantity != null && row.realizedQuantity > EPSILON && row.quantityAsset && (
        <small>{formatAssetAmount(row.quantityAsset, row.realizedQuantity)} {row.quantityAsset} realized</small>
      )}
    </span>
  );
};

const roiLabel = (row: ActivityRow) => {
  if (row.roiPercent == null) {
    return "-";
  }
  return (
    <span className={row.roiPercent >= 0 ? "positive" : "negative"}>
      {formatPercent(row.roiPercent)}%
      {row.pnlLabel && <small>{row.pnlLabel === "unrealized" ? "unrealized ROI" : "realized ROI"}</small>}
    </span>
  );
};

const compactDateLabel = (value?: string | null) => {
  if (!value) {
    return "-";
  }
  return compactDateFormatter.format(new Date(value));
};

const compactMoneyLabel = (value?: number | null, currency?: string | null) => {
  if (value == null || !Number.isFinite(value) || !currency) {
    return "-";
  }
  return formatMoney(value, currency);
};

const compactOperationCost = (row: ActivityRow) =>
  row.pnlBasis ?? row.purchasePriceBasis ?? null;

const compactOperationNow = (row: ActivityRow) => {
  const cost = compactOperationCost(row);
  if (cost != null && row.pnl != null) {
    return cost + row.pnl;
  }
  if (row.sellPriceProceeds != null) {
    return row.sellPriceProceeds;
  }
  return row.walletValueAfter ?? null;
};

const compactOperationCurrency = (row: ActivityRow) =>
  row.pnlCurrency ?? row.priceCurrency ?? row.walletValueCurrency ?? null;

const compactOperationAsset = (row: ActivityRow) => {
  if (row.priceAsset && row.priceQuantity != null && row.priceQuantity > EPSILON) {
    return (
      <>
        <strong>{row.asset}</strong>
        <small>
          {formatAssetAmount(row.priceAsset, row.priceQuantity)} {row.priceAsset}
        </small>
      </>
    );
  }
  return <strong>{row.asset}</strong>;
};

const compactOperationPnl = (row: ActivityRow) => {
  if (row.roiPercent == null && (row.pnl == null || !row.pnlCurrency)) {
    return "-";
  }
  const toneValue = row.roiPercent ?? row.pnl ?? 0;
  return (
    <span className={toneValue >= 0 ? "positive" : "negative"}>
      {row.roiPercent == null
        ? compactMoneyLabel(row.pnl, row.pnlCurrency)
        : `${row.roiPercent >= 0 ? "+" : ""}${compactPercentFormatter.format(row.roiPercent)}%`}
      {row.pnl != null && row.pnlCurrency && <small>{formatMoney(row.pnl, row.pnlCurrency)}</small>}
    </span>
  );
};

const sumValues = (values?: Record<string, number>) => {
  const entries = Object.values(values ?? {}).filter((value) => Number.isFinite(value));
  return entries.length ? entries.reduce((sum, value) => sum + value, 0) : null;
};

const inferredAssetValues = (
  balances?: Record<string, number>,
  referenceBalances?: Record<string, number>,
  referenceValues?: Record<string, number>,
) => {
  const values: Record<string, number> = {};
  Object.entries(balances ?? {}).forEach(([asset, amount]) => {
    if (!Number.isFinite(amount) || amount <= EPSILON) {
      return;
    }
    const key = asset.toUpperCase();
    const referenceBalance = referenceBalances?.[key];
    const referenceValue = referenceValues?.[key];
    if (
      referenceBalance != null &&
      referenceValue != null &&
      Number.isFinite(referenceBalance) &&
      Number.isFinite(referenceValue) &&
      Math.abs(referenceBalance) > EPSILON
    ) {
      values[key] = (referenceValue / referenceBalance) * amount;
      return;
    }
    if (["USD", "USDT", "USDC", "FDUSD"].includes(key)) {
      values[key] = amount;
    }
  });
  return values;
};

const subtractChanges = (
  balances?: Record<string, number>,
  changes?: Record<string, number>,
) => {
  const result: Record<string, number> = {};
  Object.entries(balances ?? {}).forEach(([asset, amount]) => {
    if (Number.isFinite(amount)) {
      result[asset.toUpperCase()] = amount;
    }
  });
  Object.entries(changes ?? {}).forEach(([asset, amount]) => {
    if (!Number.isFinite(amount)) {
      return;
    }
    const key = asset.toUpperCase();
    result[key] = (result[key] ?? 0) - amount;
    if (Math.abs(result[key]) <= EPSILON) {
      delete result[key];
    }
  });
  return result;
};

const buildRows = (
  orders: Order[],
  events: BinanceLedgerEvent[],
  endTimestamp?: string | null,
  currentBalances?: Record<string, number>,
  currentAssetValues?: Record<string, number>,
) => {
  const orderGroups = new Map<string, ActivityRow[]>();
  orders.forEach((order) => {
    const changes = orderChanges(order);
    const row: ActivityRow = {
      id: order.id,
      createdAt: order.created_at,
      action: order.side,
      actionKey: actionKeyFor(order.side),
      asset: order.symbol,
      amount: changesLabel(changes),
      status: order.status,
      balanceChanges: changes,
      walletValueBefore: order.account_value_before,
      walletValueAfter: order.account_value_after,
      walletValueCurrency: order.account_value_currency,
      walletValueWarning: order.account_value_warning,
      balancesAfter: order.account_balances_after,
      assetValuesAfter: order.account_asset_values_after,
      ...orderPriceDetails(order),
      pnl: orderDisplayPnl(order),
      roiPercent: orderDisplayRoi(order),
      pnlCurrency: order.quote_currency,
      pnlBasis: orderDisplayPnlBasis(order),
      pnlLabel: orderDisplayPnlLabel(order),
      ...orderLotQuantities(order),
      note: order.order_type,
    };
    const key = orderGroupKey(order);
    orderGroups.set(key, [...(orderGroups.get(key) ?? []), row]);
  });

  const groupedOrders = Array.from(orderGroups.entries()).map(([key, fills]) => {
    const sortedFills = [...fills].sort((left, right) => String(left.createdAt ?? "").localeCompare(String(right.createdAt ?? "")));
    const firstFill = sortedFills[0];
    const lastFill = sortedFills[sortedFills.length - 1];
    const changes = mergeChanges(sortedFills);
    const statuses = Array.from(new Set(sortedFills.map((fill) => fill.status).filter(Boolean)));
    const pnl = sumNullable(sortedFills.map((fill) => fill.pnl));
    const pnlBasis = sumNullable(sortedFills.map((fill) => fill.pnlBasis));
    const roiPercent = pnl != null && pnlBasis ? (pnl / pnlBasis) * 100 : null;
    const realizedQuantity = sumNullable(sortedFills.map((fill) => fill.realizedQuantity));
    const openQuantity = sumNullable(sortedFills.map((fill) => fill.openQuantity));
    const priceQuantity = sumNullable(sortedFills.map((fill) => fill.priceQuantity));
    const purchasePriceBasis = sumNullable(sortedFills.map((fill) => fill.purchasePriceBasis));
    const sellPriceProceeds = sumNullable(sortedFills.map((fill) => fill.sellPriceProceeds));
    return {
      id: key,
      createdAt: firstFill?.createdAt,
      action: firstFill?.action ?? "TRADE",
      actionKey: firstFill?.actionKey ?? actionKeyFor("TRADE"),
      asset: firstFill?.asset ?? "-",
      amount: changesLabel(changes),
      status: statuses.length === 1 ? statuses[0] : "FILLED",
      balanceChanges: changes,
      walletValueBefore: firstFill?.walletValueBefore,
      walletValueAfter: lastFill?.walletValueAfter,
      walletValueCurrency: lastFill?.walletValueCurrency,
      walletValueWarning: lastFill?.walletValueWarning,
      balancesAfter: lastFill?.balancesAfter,
      assetValuesAfter: lastFill?.assetValuesAfter,
      purchasePrice: purchasePriceBasis != null && priceQuantity ? purchasePriceBasis / priceQuantity : null,
      sellPrice: sellPriceProceeds != null && priceQuantity ? sellPriceProceeds / priceQuantity : null,
      priceCurrency: firstFill?.priceCurrency,
      priceAsset: firstFill?.priceAsset,
      priceQuantity,
      purchasePriceBasis,
      sellPriceProceeds,
      pnl,
      roiPercent,
      pnlCurrency: firstFill?.pnlCurrency,
      pnlBasis,
      pnlLabel: firstFill?.pnlLabel ?? (firstFill?.action === "SELL" ? "realized" : "unrealized"),
      quantityAsset: firstFill?.quantityAsset,
      openQuantity,
      realizedQuantity,
      note: `${firstFill?.note ?? "trade"}${sortedFills.length > 1 ? `, ${sortedFills.length} fills` : ""}`,
      fills: sortedFills,
    } satisfies ActivityRow;
  });

  const chronologicalRows: ActivityRow[] = [
    ...groupedOrders,
    ...events.map((event): ActivityRow => {
      const changes = eventChanges(event);
      const action = eventLabel(event);
      return {
        id: event.id,
        createdAt: event.created_at,
        action,
        actionKey: actionKeyFor(action),
        asset: event.asset,
        amount: changesLabel(changes),
        status: event.status,
        balanceChanges: changes,
        walletValueAfter: event.account_value_after,
        walletValueCurrency: event.account_value_currency,
        walletValueWarning: event.account_value_warning,
        balancesAfter: event.account_balances_after,
        assetValuesAfter: event.account_asset_values_after,
        note: event.fee ? `fee ${formatAssetAmount(event.asset, event.fee)} ${event.asset}` : null,
      };
    }),
  ].sort((left, right) => String(left.createdAt ?? "").localeCompare(String(right.createdAt ?? "")));

  const latestRow = chronologicalRows[chronologicalRows.length - 1];
  const earliestRow = chronologicalRows[0];
  const hasBalanceTimeline =
    events.length > 0 ||
    orders.some((order) => order.source === "binance") ||
    Boolean(currentBalances && Object.keys(currentBalances).length > 0) ||
    Boolean(currentAssetValues && Object.keys(currentAssetValues).length > 0);
  const startBalances = subtractChanges(earliestRow?.balancesAfter, earliestRow?.balanceChanges);
  const startAssetValues = inferredAssetValues(
    startBalances,
    earliestRow?.balancesAfter,
    earliestRow?.assetValuesAfter,
  );
  const inferredStartValue = earliestRow?.walletValueBefore ?? sumValues(startAssetValues);
  const unvaluedStartAssets = Object.entries(startBalances)
    .filter(([, amount]) => amount > EPSILON)
    .map(([asset]) => asset.toUpperCase())
    .filter((asset) => startAssetValues[asset] == null);
  const startValueWarning =
    unvaluedStartAssets.length > 0
      ? `Inferred opening value before the earliest traceable activity. Missing valuation for ${unvaluedStartAssets.join(", ")}.`
      : "Inferred opening value before the earliest traceable activity.";
  const startRow: ActivityRow | null =
    hasBalanceTimeline && earliestRow
      ? {
          id: "synthetic-start",
          createdAt: earliestRow.createdAt,
          action: "Start",
          actionKey: "start",
          asset: "Spot",
          amount: "-",
          status: "inferred",
          balanceChanges: {},
          walletValueAfter: inferredStartValue,
          walletValueCurrency: inferredStartValue == null ? null : earliestRow.walletValueCurrency ?? "USDT",
          walletValueWarning: startValueWarning,
          balancesAfter: startBalances,
          assetValuesAfter: startAssetValues,
          note: "inferred opening balance",
        } satisfies ActivityRow
      : null;
  const endBalances = currentBalances && Object.keys(currentBalances).length ? currentBalances : latestRow?.balancesAfter;
  const endAssetValues = currentAssetValues && Object.keys(currentAssetValues).length ? currentAssetValues : latestRow?.assetValuesAfter;
  const endValue = sumValues(endAssetValues);
  const endRow: ActivityRow | null =
    hasBalanceTimeline && endTimestamp && latestRow
      ? {
          id: "synthetic-end",
          createdAt: endTimestamp,
          action: "End",
          actionKey: "end",
          asset: "Spot",
          amount: "-",
          status: "current",
          balanceChanges: {},
          walletValueAfter: endValue,
          walletValueCurrency: endValue == null ? null : "USDT",
          walletValueWarning: null,
          balancesAfter: endBalances,
          assetValuesAfter: endAssetValues,
          note: "latest snapshot",
        } satisfies ActivityRow
      : null;

  return [...chronologicalRows, ...(startRow ? [startRow] : []), ...(endRow ? [endRow] : [])].sort((left, right) =>
    String(right.createdAt ?? "").localeCompare(String(left.createdAt ?? "")),
  );
};

export const BinanceActivityTable = memo(function BinanceActivityTable({
  orders,
  events,
  emptyLabel = "No activity loaded.",
  title = "Operations",
  controls,
  compact = false,
  endTimestamp,
  currentBalances,
  currentAssetValues,
}: Props) {
  const rows = useMemo(
    () => buildRows(orders, events, endTimestamp, currentBalances, currentAssetValues),
    [currentAssetValues, currentBalances, endTimestamp, events, orders],
  );
  const actionOptions = useMemo(
    () => Array.from(new Map(rows.map((row) => [row.actionKey, actionLabelFor(row.actionKey)])).entries()),
    [rows],
  );
  const showBalanceColumns = useMemo(
    () =>
      rows.some(
        (row) =>
          row.walletValueAfter != null ||
          Object.keys(row.balancesAfter ?? {}).length > 0 ||
          Object.keys(row.assetValuesAfter ?? {}).length > 0,
      ),
    [rows],
  );
  const [visibleActions, setVisibleActions] = useState<Record<string, boolean>>({ buy: true, sell: true });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState(1);
  const visibleRows = useMemo(
    () => rows.filter((row) => visibleActions[row.actionKey] ?? true),
    [rows, visibleActions],
  );
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / ACTIVITY_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * ACTIVITY_PAGE_SIZE;
  const pagedRows = useMemo(
    () => visibleRows.slice(pageStart, pageStart + ACTIVITY_PAGE_SIZE),
    [pageStart, visibleRows],
  );
  const paginationLabel =
    visibleRows.length === 0
      ? "0"
      : `${pageStart + 1}-${Math.min(pageStart + ACTIVITY_PAGE_SIZE, visibleRows.length)} of ${visibleRows.length}`;

  const toggle = (id: string) => {
    setExpanded((current) => ({ ...current, [id]: !current[id] }));
  };

  const toggleAction = (actionKey: string) => {
    setPage(1);
    setVisibleActions((current) => ({ ...current, [actionKey]: !current[actionKey] }));
  };

  const showAllActions = () => {
    setPage(1);
    setVisibleActions(Object.fromEntries(actionOptions.map(([actionKey]) => [actionKey, true])));
  };

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <div className="panel-heading-actions">
          {controls}
          <span>{visibleRows.length}</span>
        </div>
      </div>
      <div className="activity-controls">
        <button type="button" className="filter-chip" onClick={showAllActions}>
          All
        </button>
        {actionOptions.map(([actionKey, label]) => (
          <button
            type="button"
            className={`filter-chip ${visibleActions[actionKey] ? "active" : ""}`}
            key={actionKey}
            onClick={() => toggleAction(actionKey)}
          >
            {label}
          </button>
        ))}
      </div>
      {compact ? (
        <div className="table-wrap compact-table-wrap">
          <table className="compact-operations-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Action</th>
                <th>Asset / Pair</th>
                <th>Cost</th>
                <th>Cost Now</th>
                <th>P/L</th>
              </tr>
            </thead>
            <tbody>
              {pagedRows.map((row) => {
                const currency = compactOperationCurrency(row);
                return (
                  <tr key={row.id}>
                    <td>{compactDateLabel(row.createdAt)}</td>
                    <td>
                      <strong>{row.action}</strong>
                      {row.note && <small>{row.note}</small>}
                    </td>
                    <td className="compact-operation-asset">{compactOperationAsset(row)}</td>
                    <td>{compactMoneyLabel(compactOperationCost(row), currency)}</td>
                    <td>{compactMoneyLabel(compactOperationNow(row), currency)}</td>
                    <td>{compactOperationPnl(row)}</td>
                  </tr>
                );
              })}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">{emptyLabel}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-wrap">
          <table className={`activity-table ${showBalanceColumns ? "" : "compact"}`}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Action</th>
                <th>Asset / Pair</th>
                <th>Purchase Price</th>
                <th>Spot Change</th>
                <th>P/L</th>
                <th>ROI</th>
                {showBalanceColumns && <th>Estimated Wallet Value</th>}
                <th>Status</th>
                {showBalanceColumns && <th>Wallet Assets After</th>}
                {showBalanceColumns && <th>Asset Values</th>}
              </tr>
            </thead>
            <tbody>
              {pagedRows.map((row) => (
                <Fragment key={row.id}>
                  <tr>
                    <td>{formatDateTime(row.createdAt)}</td>
                    <td>
                      {row.fills && row.fills.length > 1 && (
                        <button type="button" className="icon-button row-toggle" onClick={() => toggle(row.id)} title="Show fills">
                          {expanded[row.id] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </button>
                      )}
                      <strong>{row.action}</strong>
                      {row.note && <small>{row.note}</small>}
                    </td>
                    <td>{row.asset}</td>
                    <td>{purchasePriceLabel(row)}</td>
                    <td className="activity-list-cell">{changesList(row.balanceChanges, row.amount)}</td>
                    <td>{pnlLabel(row)}</td>
                    <td>{roiLabel(row)}</td>
                    {showBalanceColumns && <td>{walletValueLabel(row)}</td>}
                    <td>{row.status ?? "-"}</td>
                    {showBalanceColumns && <td className="activity-list-cell wide">{balancesLabel(row.balancesAfter)}</td>}
                    {showBalanceColumns && <td className="activity-list-cell wide">{assetValuesLabel(row.assetValuesAfter)}</td>}
                  </tr>
                  {expanded[row.id] &&
                    row.fills?.map((fill) => (
                      <tr className="child-row" key={fill.id}>
                        <td>{formatDateTime(fill.createdAt)}</td>
                        <td>
                          <strong>{fill.action}</strong>
                          {fill.note && <small>{fill.note}</small>}
                        </td>
                        <td>{fill.asset}</td>
                        <td>{purchasePriceLabel(fill)}</td>
                        <td className="activity-list-cell">{changesList(fill.balanceChanges, fill.amount)}</td>
                        <td>{pnlLabel(fill)}</td>
                        <td>{roiLabel(fill)}</td>
                        {showBalanceColumns && <td>{walletValueLabel(fill)}</td>}
                        <td>{fill.status ?? "-"}</td>
                        {showBalanceColumns && <td className="activity-list-cell wide">{balancesLabel(fill.balancesAfter)}</td>}
                        {showBalanceColumns && <td className="activity-list-cell wide">{assetValuesLabel(fill.assetValuesAfter)}</td>}
                      </tr>
                    ))}
                </Fragment>
              ))}
              {visibleRows.length === 0 && (
                <tr>
                  <td colSpan={showBalanceColumns ? 11 : 8} className="empty">{emptyLabel}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {visibleRows.length > ACTIVITY_PAGE_SIZE && (
        <div className="table-pagination" aria-label={`${title} pagination`}>
          <span>{paginationLabel}</span>
          <button
            type="button"
            className="icon-button"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={currentPage <= 1}
            title="Previous page"
          >
            <ChevronLeft size={16} aria-hidden="true" />
          </button>
          <strong>
            {currentPage} / {totalPages}
          </strong>
          <button
            type="button"
            className="icon-button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            disabled={currentPage >= totalPages}
            title="Next page"
          >
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      )}
    </section>
  );
});
