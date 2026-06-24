from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.config import Settings
from app.models import (
    BinanceLedgerEvent,
    BreakdownItem,
    CashBalance,
    DisplayRate,
    FxRate,
    HistoricalPrice,
    Holding,
    MarketPrice,
    Order,
    PortfolioSnapshot,
    RefreshSource,
    SourceResult,
    SourceSyncStatus,
)
from app.services.normalization import stable_id
from app.services.storage import (
    connect,
    load_cash_balances,
    load_fx_rates,
    load_historical_prices,
    load_holdings,
    load_ledger_events,
    load_market_prices,
    load_open_orders,
    load_order_history,
    load_sync_status,
    replace_fx_rates,
    replace_historical_prices,
    replace_ledger_events,
    replace_market_prices,
    replace_order_history,
    replace_source_result,
    update_sync_status,
)
from app.sources.binance import fetch_binance, fetch_binance_historical_prices, fetch_binance_ledger
from app.sources.fx import canonical_fx_currency, fetch_fx_rates
from app.sources.ibkr import fetch_ibkr, fetch_ibkr_history
from app.sources.market_data import fetch_market_prices
from app.sources.manual import load_manual_data


USD_LIKE_QUOTES = {"USD", "USDT", "USDC", "FDUSD"}
EPSILON = 0.00000001
RefreshProgressCallback = Callable[[str, str, int, int], None]


REFRESH_STEP_LABELS: dict[str, str] = {
    "manual": "Manual cash and assets",
    "binance": "Binance balances, orders, and trades",
    "binance_ledger": "Binance ledger and historical prices",
    "ibkr": "IBKR positions, cash, and orders",
    "ibkr_history": "IBKR activity history",
    "market_data": "Market prices",
    "fx": "FX rates",
    "snapshot": "Rebuilding snapshot",
}


@dataclass
class _CostLot:
    order_id: str
    original_quantity: float
    remaining_quantity: float
    remaining_cost: float


@dataclass
class _TimelineEvent:
    created_at: datetime
    kind: str
    order: Order | None = None
    ledger_event: BinanceLedgerEvent | None = None


def _convert(value: float, currency: str, settings: Settings, fx_rates: dict[str, FxRate], warnings: list[str]) -> float:
    if abs(value) < 0.0000001:
        return 0
    currency = canonical_fx_currency(currency, settings.base_currency)
    if currency == settings.base_currency:
        return value
    rate = fx_rates.get(currency)
    if rate is None:
        warnings.append(
            f"Missing FX rate for {currency}->{settings.base_currency}; excluded {value:.2f} {currency} from totals."
        )
        return 0
    return value * rate.rate


def _convert_between(
    value: float,
    from_currency: str | None,
    to_currency: str | None,
    settings: Settings,
    fx_rates: dict[str, FxRate],
) -> float | None:
    if from_currency is None or to_currency is None:
        return None
    from_currency = canonical_fx_currency(from_currency, settings.base_currency)
    to_currency = canonical_fx_currency(to_currency, settings.base_currency)
    if from_currency == to_currency:
        return value

    if from_currency == settings.base_currency:
        base_value = value
    else:
        from_rate = fx_rates.get(from_currency)
        if from_rate is None:
            return None
        base_value = value * from_rate.rate

    if to_currency == settings.base_currency:
        return base_value
    to_rate = fx_rates.get(to_currency)
    if to_rate is None or abs(to_rate.rate) <= EPSILON:
        return None
    return base_value / to_rate.rate


def _display_rates(settings: Settings, fx_rates: dict[str, FxRate]) -> list[DisplayRate]:
    rates = [DisplayRate(currency=settings.base_currency, rate_from_base=1.0, source="system")]
    usd = fx_rates.get("USD")
    if usd and usd.rate:
        rates.append(
            DisplayRate(
                currency="USD",
                rate_from_base=1 / usd.rate,
                source=usd.source,
                fetched_at=usd.fetched_at,
            )
        )
    return rates


def _breakdown(rows: dict[str, float], total: float) -> list[BreakdownItem]:
    items = []
    for name, value in sorted(rows.items(), key=lambda item: item[1], reverse=True):
        percent = (value / total * 100) if total else 0
        items.append(BreakdownItem(name=name, value=round(value, 2), percent=round(percent, 2)))
    return items


def _demo_result() -> SourceResult:
    now = datetime.now(timezone.utc)
    holdings = [
        Holding(
            id=stable_id("demo", "VWCE"),
            source="demo",
            platform="Demo Broker",
            symbol="VWCE",
            name="Vanguard FTSE All-World UCITS ETF",
            asset_class="etf",
            quantity=12,
            currency="EUR",
            current_price=120.5,
            market_value=1446,
            cost_basis=1320,
            unrealized_pnl=126,
            sector="Broad Market",
            vertical="Global equities",
            geography="Global",
            confidence="manual_verified",
            updated_at=now,
        ),
        Holding(
            id=stable_id("demo", "BTC"),
            source="demo",
            platform="Demo Exchange",
            symbol="BTC",
            name="Bitcoin",
            asset_class="crypto",
            quantity=0.15,
            currency="EUR",
            current_price=58000,
            market_value=8700,
            cost_basis=7500,
            unrealized_pnl=1200,
            sector="Digital Assets",
            vertical="Store of value",
            geography="Global",
            confidence="manual_verified",
            updated_at=now,
        ),
    ]
    cash = [
        CashBalance(
            id=stable_id("demo-cash", "bank"),
            source="demo",
            platform="Demo Bank",
            currency="EUR",
            balance=6500,
            purpose="emergency_fund",
            updated_at=now,
        )
    ]
    orders = [
        Order(
            id=stable_id("demo-order", "AAPL"),
            source="demo",
            platform="Demo Broker",
            symbol="AAPL",
            side="BUY",
            order_type="LMT",
            quantity=5,
            limit_price=165,
            status="Submitted",
            created_at=now,
            raw={"demo": True},
        )
    ]
    return SourceResult(
        holdings=holdings,
        cash_balances=cash,
        open_orders=orders,
        warnings=["Using demo fallback data because no real/manual portfolio data was loaded."],
    )


def _source_status_warnings(statuses: list[SourceSyncStatus]) -> list[str]:
    warnings: list[str] = []
    for status in statuses:
        if status.warning:
            warnings.extend(f"{status.source}: {line}" for line in status.warning.splitlines() if line)
    return warnings


def _price_for_holding(
    holding: Holding,
    market_prices: dict[tuple[str, str], MarketPrice],
    settings: Settings,
    warnings: list[str],
) -> tuple[Holding, bool]:
    symbol = holding.symbol.upper()
    candidates = [
        (symbol, holding.currency.upper()),
        (symbol, "USD"),
        (symbol, "USDT"),
        (symbol, "USDC"),
        (symbol, "FDUSD"),
        (symbol, settings.base_currency),
    ]
    price = next((market_prices[key] for key in candidates if key in market_prices), None)

    if price:
        fetched_at = price.fetched_at if price.fetched_at.tzinfo else price.fetched_at.replace(tzinfo=timezone.utc)
        stale_after = datetime.now(timezone.utc) - timedelta(hours=settings.market_price_stale_hours)
        if fetched_at < stale_after:
            warnings.append(
                f"Stale market price for {symbol}: {price.fetched_at.isoformat()} from {price.source}. "
                "Suggested action: Refresh market prices."
            )
        market_value = holding.quantity * price.price
        return (
            holding.model_copy(
                update={
                    "currency": price.currency,
                    "current_price": price.price,
                    "market_value": market_value,
                    "unrealized_pnl": (market_value - holding.cost_basis) if holding.cost_basis is not None else holding.unrealized_pnl,
                    "updated_at": price.fetched_at,
                    "valuation_source": price.source,
                    "valuation_timestamp": price.fetched_at,
                }
            ),
            True,
        )

    if holding.source == "manual" and holding.current_price is not None:
        market_value = holding.quantity * holding.current_price
        return (
            holding.model_copy(
                update={
                    "market_value": market_value,
                    "valuation_source": "manual_estimated_price",
                    "valuation_timestamp": holding.updated_at,
                }
            ),
            True,
        )

    warnings.append(
        f"Missing market price for {symbol}; quantity included but market value excluded from totals. "
        "Suggested action: Refresh market prices."
    )
    return (holding.model_copy(update={"market_value": 0, "current_price": None}), False)


def _split_pair(symbol: str) -> tuple[str, str | None]:
    for quote in ("USDT", "USDC", "FDUSD", "EUR", "USD", "BTC", "ETH"):
        if symbol.upper().endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)].upper(), quote
    return symbol.upper(), None


def _value_bucket(currency: str | None) -> str | None:
    if currency is None:
        return None
    currency = currency.upper()
    return "USD" if currency in USD_LIKE_QUOTES else currency


def _same_value_bucket(left: str | None, right: str | None) -> bool:
    return _value_bucket(left) is not None and _value_bucket(left) == _value_bucket(right)


def _price_for_order(order: Order, market_prices: dict[tuple[str, str], MarketPrice]) -> MarketPrice | None:
    base, quote = _split_pair(order.symbol)
    candidates = []
    if quote:
        candidates.append((base, quote))
        if quote in {"USDT", "USDC", "FDUSD"}:
            candidates.append((base, "USD"))
    candidates.extend([(base, "EUR"), (base, "USDT"), (base, "USDC"), (base, "USD")])
    return next((market_prices[key] for key in candidates if key in market_prices), None)


def _order_quote_amount(order: Order) -> float | None:
    quote_qty = order.raw.get("quoteQty") or order.raw.get("cummulativeQuoteQty")
    if quote_qty not in (None, ""):
        try:
            return float(quote_qty)
        except (TypeError, ValueError):
            return None
    if order.limit_price is not None:
        return order.limit_price * order.quantity
    return None


def _pnl_base_quantity_and_quote_amount(order: Order) -> tuple[float, float | None]:
    base, quote = _split_pair(order.symbol)
    quote_amount = _order_quote_amount(order)
    commission_asset, commission_amount = _commission(order)
    base_quantity = order.quantity

    if order.side == "BUY":
        if commission_asset == base:
            base_quantity -= commission_amount
        if commission_asset == quote and quote_amount is not None:
            quote_amount += commission_amount
    else:
        if commission_asset == base:
            base_quantity += commission_amount
        if commission_asset == quote and quote_amount is not None:
            quote_amount -= commission_amount

    return max(base_quantity, 0.0), quote_amount


def _base_order_update(order: Order, quote_amount: float | None, quote: str | None) -> dict[str, object]:
    return {
        "quote_currency": quote,
        "purchase_amount": quote_amount,
        "cost_basis_amount": None,
        "current_value": None,
        "roi_percent": None,
        "realized_pnl": None,
        "realized_roi_percent": None,
        "unrealized_pnl": None,
        "unrealized_roi_percent": None,
        "remaining_quantity": None,
        "remaining_cost_basis": None,
        "position_status": None,
        "valuation_source": None,
        "valuation_timestamp": None,
    }


def _apply_open_lot_valuation(
    order: Order,
    update: dict[str, object],
    remaining_quantity: float,
    remaining_cost: float,
    market_prices: dict[tuple[str, str], MarketPrice],
    settings: Settings,
    fx_rates: dict[str, FxRate],
) -> None:
    price = _price_for_order(order, market_prices)
    quote = update.get("quote_currency")
    price_in_quote = _convert_between(
        price.price,
        price.currency,
        str(quote) if quote else None,
        settings,
        fx_rates,
    ) if price else None
    current_value = None
    unrealized_pnl = None
    unrealized_roi = None

    if price and price_in_quote is not None:
        current_value = remaining_quantity * price_in_quote
        unrealized_pnl = current_value - remaining_cost
        unrealized_roi = (unrealized_pnl / remaining_cost) * 100 if remaining_cost else None

    update.update(
        {
            "current_value": current_value,
            "roi_percent": unrealized_roi,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_roi_percent": unrealized_roi,
            "remaining_quantity": remaining_quantity,
            "remaining_cost_basis": remaining_cost,
            "valuation_source": price.source if current_value is not None and price else None,
            "valuation_timestamp": price.fetched_at if current_value is not None and price else None,
        }
    )


def _order_sort_time(order: Order) -> datetime:
    if order.created_at is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if order.created_at.tzinfo is None:
        return order.created_at.replace(tzinfo=timezone.utc)
    return order.created_at.astimezone(timezone.utc)


def _event_sort_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _minute_key(value: datetime) -> str:
    return _event_sort_time(value).replace(second=0, microsecond=0).isoformat()


def _minute(value: datetime) -> datetime:
    return _event_sort_time(value).replace(second=0, microsecond=0)


def _enrich_binance_order_history(
    orders: list[Order],
    market_prices: dict[tuple[str, str], MarketPrice],
    settings: Settings,
    fx_rates: dict[str, FxRate],
) -> list[Order]:
    lots: dict[tuple[str, str], list[_CostLot]] = defaultdict(list)
    updates: dict[str, dict[str, object]] = {}
    ordered = sorted(orders, key=_order_sort_time)
    orders_by_id = {order.id: order for order in orders}

    for order in ordered:
        quote_amount = _order_quote_amount(order)
        pnl_quantity, pnl_quote_amount = _pnl_base_quantity_and_quote_amount(order)
        base, quote = _split_pair(order.symbol)
        quote_bucket = _value_bucket(quote)
        lot_key = (base, quote_bucket or quote or "")
        update = _base_order_update(order, quote_amount, quote)
        updates[order.id] = update

        if not quote_bucket or pnl_quote_amount is None or pnl_quantity <= 0:
            update["position_status"] = "unpriced"
            continue

        if order.side == "BUY":
            lots[lot_key].append(
                _CostLot(
                    order_id=order.id,
                    original_quantity=pnl_quantity,
                    remaining_quantity=pnl_quantity,
                    remaining_cost=pnl_quote_amount,
                )
            )
            update.update(
                {
                    "cost_basis_amount": pnl_quote_amount,
                    "remaining_quantity": pnl_quantity,
                    "remaining_cost_basis": pnl_quote_amount,
                    "position_status": "open",
                }
            )
            continue

        remaining_to_match = pnl_quantity
        matched_quantity = 0.0
        matched_cost = 0.0
        for lot in lots[lot_key]:
            if remaining_to_match <= EPSILON:
                break
            if lot.remaining_quantity <= EPSILON:
                continue

            consumed_quantity = min(remaining_to_match, lot.remaining_quantity)
            consumed_cost = lot.remaining_cost * (consumed_quantity / lot.remaining_quantity)
            lot.remaining_quantity -= consumed_quantity
            lot.remaining_cost -= consumed_cost
            remaining_to_match -= consumed_quantity
            matched_quantity += consumed_quantity
            matched_cost += consumed_cost

        matched_proceeds = pnl_quote_amount * (matched_quantity / pnl_quantity) if matched_quantity > EPSILON else None
        realized_pnl = matched_proceeds - matched_cost if matched_proceeds is not None else None
        realized_roi = (realized_pnl / matched_cost) * 100 if realized_pnl is not None and matched_cost else None
        if matched_quantity <= EPSILON:
            position_status = "unmatched"
        elif remaining_to_match > EPSILON:
            position_status = "partial_unmatched"
        else:
            position_status = "realized"

        update.update(
            {
                "cost_basis_amount": matched_cost if matched_quantity > EPSILON else None,
                "realized_pnl": realized_pnl,
                "realized_roi_percent": realized_roi,
                "roi_percent": realized_roi,
                "remaining_quantity": max(remaining_to_match, 0.0) if remaining_to_match > EPSILON else 0.0,
                "position_status": position_status,
            }
        )

    for lot_list in lots.values():
        for lot in lot_list:
            update = updates[lot.order_id]
            original_quantity = lot.original_quantity
            remaining_quantity = max(lot.remaining_quantity, 0.0)
            remaining_cost = max(lot.remaining_cost, 0.0)
            if remaining_quantity <= EPSILON:
                update.update(
                    {
                        "remaining_quantity": 0.0,
                        "remaining_cost_basis": 0.0,
                        "position_status": "closed",
                    }
                )
                continue

            order = orders_by_id[lot.order_id]
            position_status = "open" if abs(remaining_quantity - original_quantity) <= EPSILON else "partial"
            update["position_status"] = position_status
            _apply_open_lot_valuation(order, update, remaining_quantity, remaining_cost, market_prices, settings, fx_rates)

    return [order.model_copy(update=updates.get(order.id, {})) for order in orders]


def _commission(order: Order) -> tuple[str | None, float]:
    asset = order.raw.get("commissionAsset")
    amount = order.raw.get("commission")
    if not asset or amount in (None, ""):
        return None, 0.0
    try:
        return str(asset).upper(), float(amount)
    except (TypeError, ValueError):
        return None, 0.0


def _apply_trade_to_balances(order: Order, balances: dict[str, float]) -> None:
    base, quote = _split_pair(order.symbol)
    quote_amount = _order_quote_amount(order)
    if quote is None or quote_amount is None:
        return

    if order.side == "BUY":
        balances[base] += order.quantity
        balances[quote] -= quote_amount
    else:
        balances[base] -= order.quantity
        balances[quote] += quote_amount

    commission_asset, commission_amount = _commission(order)
    if commission_asset and commission_amount:
        balances[commission_asset] -= commission_amount


def _apply_ledger_event_to_balances(event: BinanceLedgerEvent, balances: dict[str, float]) -> None:
    if event.balance_changes:
        for asset, amount in event.balance_changes.items():
            balances[asset.upper()] += amount
        return
    if event.event_type == "deposit":
        balances[event.asset] += event.amount
    else:
        balances[event.asset] -= event.amount + event.fee


def _add_balance(balances: dict[str, float], asset: str | None, amount: float) -> None:
    if not asset or abs(amount) <= EPSILON:
        return
    key = asset.upper()
    balances[key] += amount
    if abs(balances[key]) <= EPSILON:
        balances.pop(key, None)


def _reverse_trade_from_balances(order: Order, balances: dict[str, float]) -> None:
    base, quote = _split_pair(order.symbol)
    quote_amount = _order_quote_amount(order)
    if quote is None or quote_amount is None:
        return

    if order.side == "BUY":
        _add_balance(balances, base, -order.quantity)
        _add_balance(balances, quote, quote_amount)
    else:
        _add_balance(balances, base, order.quantity)
        _add_balance(balances, quote, -quote_amount)

    commission_asset, commission_amount = _commission(order)
    _add_balance(balances, commission_asset, commission_amount)


def _reverse_ledger_event_from_balances(event: BinanceLedgerEvent, balances: dict[str, float]) -> None:
    if event.balance_changes:
        for asset, amount in event.balance_changes.items():
            _add_balance(balances, asset, -amount)
        return
    if event.event_type == "deposit":
        _add_balance(balances, event.asset, -event.amount)
    else:
        _add_balance(balances, event.asset, event.amount + event.fee)


def _nearest_historical_price(
    asset: str,
    when: datetime,
    historical_prices: dict[tuple[str, str, str], HistoricalPrice],
) -> tuple[HistoricalPrice | None, str | None]:
    key_time = _minute_key(when)
    exact = historical_prices.get((asset.upper(), "USD", key_time))
    if exact:
        return exact, None

    nearest: HistoricalPrice | None = None
    nearest_delta: timedelta | None = None
    for price in historical_prices.values():
        if price.asset.upper() != asset.upper() or price.currency.upper() != "USD":
            continue
        delta = abs(price.priced_at - when)
        if nearest_delta is None or delta < nearest_delta:
            nearest = price
            nearest_delta = delta

    if nearest is None or nearest_delta is None:
        return None, None
    warning = None
    if nearest_delta > timedelta(days=7):
        warning = f"using nearest {asset} price from {nearest.priced_at.date()}"
    return nearest, warning


def _total_binance_value(
    balances: dict[str, float],
    when: datetime,
    historical_prices: dict[tuple[str, str, str], HistoricalPrice],
    settings: Settings,
    fx_rates: dict[str, FxRate],
) -> tuple[float | None, list[str], dict[str, float]]:
    total = 0.0
    warnings: list[str] = []
    asset_values: dict[str, float] = {}

    for asset, quantity in balances.items():
        if abs(quantity) <= EPSILON:
            continue
        if quantity < -EPSILON:
            warnings.append(f"negative {asset} balance in replay")
        if asset in USD_LIKE_QUOTES:
            value = quantity
            total += value
            asset_values[asset] = round(value, 2)
            continue
        if asset == settings.base_currency:
            usd_rate = fx_rates.get("USD")
            if usd_rate and usd_rate.rate:
                value = quantity / usd_rate.rate
                total += value
                asset_values[asset] = round(value, 2)
            else:
                warnings.append(f"missing FX rate for {asset}->USD")
            continue
        fiat_rate = fx_rates.get(asset)
        usd_rate = fx_rates.get("USD")
        if fiat_rate and usd_rate and usd_rate.rate:
            value = (quantity * fiat_rate.rate) / usd_rate.rate
            total += value
            asset_values[asset] = round(value, 2)
            continue
        price, price_warning = _nearest_historical_price(asset, when, historical_prices)
        if price is None:
            warnings.append(f"missing historical USD price for {asset}")
            continue
        if price_warning:
            warnings.append(price_warning)
        value = quantity * price.price
        total += value
        asset_values[asset] = round(value, 2)

    return total, warnings, asset_values


def _current_binance_balances(holdings: list[Holding], cash_balances: list[CashBalance]) -> dict[str, float]:
    balances: dict[str, float] = defaultdict(float)
    for holding in holdings:
        if holding.source == "binance":
            _add_balance(balances, holding.symbol, holding.quantity)
    for cash in cash_balances:
        if cash.source == "binance":
            _add_balance(balances, cash.currency, cash.balance)
    return balances


def _display_balances(balances: dict[str, float]) -> dict[str, float]:
    return {
        asset: round(amount, 8)
        for asset, amount in sorted(balances.items())
        if amount > EPSILON
    }


def _historical_price_requirements_from_timeline(
    orders: list[Order],
    ledger_events: list[BinanceLedgerEvent],
) -> dict[datetime, set[str]]:
    requirements: dict[datetime, set[str]] = defaultdict(set)
    timeline: list[_TimelineEvent] = [
        *[_TimelineEvent(created_at=_order_sort_time(order), kind="trade", order=order) for order in orders if order.source == "binance"],
        *[_TimelineEvent(created_at=_event_sort_time(event.created_at), kind="ledger", ledger_event=event) for event in ledger_events if event.source == "binance"],
    ]
    timeline.sort(key=lambda event: (event.created_at, 0 if event.kind == "ledger" else 1))
    balances: dict[str, float] = defaultdict(float)

    for event in timeline:
        if event.kind == "ledger" and event.ledger_event:
            _apply_ledger_event_to_balances(event.ledger_event, balances)
        elif event.order:
            _apply_trade_to_balances(event.order, balances)
        else:
            continue

        assets = {
            asset.upper()
            for asset, amount in balances.items()
            if amount > EPSILON and asset.upper() not in USD_LIKE_QUOTES
        }
        if assets:
            requirements[_minute(event.created_at)].update(assets)

    return requirements


def _enrich_binance_capital_values(
    orders: list[Order],
    ledger_events: list[BinanceLedgerEvent],
    historical_prices: dict[tuple[str, str, str], HistoricalPrice],
    settings: Settings,
    fx_rates: dict[str, FxRate],
    current_balances: dict[str, float],
) -> tuple[list[Order], list[BinanceLedgerEvent]]:
    if not orders and not ledger_events:
        return orders, ledger_events

    order_updates: dict[str, dict[str, object]] = {}
    ledger_updates: dict[str, dict[str, object]] = {}
    timeline: list[_TimelineEvent] = [
        *[_TimelineEvent(created_at=_order_sort_time(order), kind="trade", order=order) for order in orders],
        *[_TimelineEvent(created_at=_event_sort_time(event.created_at), kind="ledger", ledger_event=event) for event in ledger_events],
    ]
    ledger_warning = None if ledger_events else "No Binance ledger events are cached; capital timeline may exclude transfers, fiat orders, or conversions."

    if any(event.event_type == "start" for event in ledger_events):
        balances: dict[str, float] = defaultdict(float)
        timeline.sort(key=lambda event: (event.created_at, 0 if event.kind == "ledger" else 1))
        for event in timeline:
            if event.kind == "ledger" and event.ledger_event:
                _apply_ledger_event_to_balances(event.ledger_event, balances)
                after, after_warnings, after_asset_values = _total_binance_value(
                    balances, event.created_at, historical_prices, settings, fx_rates
                )
                warnings = sorted(set([*after_warnings, *([ledger_warning] if ledger_warning else [])]))
                ledger_updates[event.ledger_event.id] = {
                    "account_value_after": round(after, 2) if after is not None else None,
                    "account_value_currency": "USDT",
                    "account_value_source": "binance_ledger_replay",
                    "account_value_warning": "; ".join(warnings) if warnings else None,
                    "account_balances_after": _display_balances(balances),
                    "account_asset_values_after": after_asset_values,
                }
                continue
            if event.order is None:
                continue

            before, before_warnings, _before_asset_values = _total_binance_value(
                balances, event.created_at, historical_prices, settings, fx_rates
            )
            _apply_trade_to_balances(event.order, balances)
            after, after_warnings, after_asset_values = _total_binance_value(
                balances, event.created_at, historical_prices, settings, fx_rates
            )
            warnings = sorted(set([*before_warnings, *after_warnings, *([ledger_warning] if ledger_warning else [])]))
            order_updates[event.order.id] = {
                "account_value_before": round(before, 2) if before is not None else None,
                "account_value_after": round(after, 2) if after is not None else None,
                "account_value_currency": "USDT",
                "account_value_source": "binance_ledger_replay",
                "account_value_warning": "; ".join(warnings) if warnings else None,
                "account_balances_after": _display_balances(balances),
                "account_asset_values_after": after_asset_values,
            }

        return (
            [order.model_copy(update=order_updates.get(order.id, {})) for order in orders],
            [event.model_copy(update=ledger_updates.get(event.id, {})) for event in ledger_events],
        )

    balances = defaultdict(float, {asset.upper(): amount for asset, amount in current_balances.items()})
    timeline.sort(key=lambda event: (event.created_at, 0 if event.kind == "ledger" else 1), reverse=True)

    for event in timeline:
        if event.kind == "ledger" and event.ledger_event:
            after, after_warnings, after_asset_values = _total_binance_value(
                balances, event.created_at, historical_prices, settings, fx_rates
            )
            warnings = sorted(set([*after_warnings, *([ledger_warning] if ledger_warning else [])]))
            ledger_updates[event.ledger_event.id] = {
                "account_value_after": round(after, 2) if after is not None else None,
                "account_value_currency": "USDT",
                "account_value_source": "binance_ledger_replay",
                "account_value_warning": "; ".join(warnings) if warnings else None,
                "account_balances_after": _display_balances(balances),
                "account_asset_values_after": after_asset_values,
            }
            _reverse_ledger_event_from_balances(event.ledger_event, balances)
            continue
        if event.order is None:
            continue

        after, after_warnings, after_asset_values = _total_binance_value(
            balances, event.created_at, historical_prices, settings, fx_rates
        )
        after_balances = _display_balances(balances)
        _reverse_trade_from_balances(event.order, balances)
        before, before_warnings, _before_asset_values = _total_binance_value(
            balances, event.created_at, historical_prices, settings, fx_rates
        )
        warnings = sorted(set([*before_warnings, *after_warnings, *([ledger_warning] if ledger_warning else [])]))
        order_updates[event.order.id] = {
            "account_value_before": round(before, 2) if before is not None else None,
            "account_value_after": round(after, 2) if after is not None else None,
            "account_value_currency": "USDT",
            "account_value_source": "binance_ledger_replay",
            "account_value_warning": "; ".join(warnings) if warnings else None,
            "account_balances_after": after_balances,
            "account_asset_values_after": after_asset_values,
        }

    return (
        [order.model_copy(update=order_updates.get(order.id, {})) for order in orders],
        [event.model_copy(update=ledger_updates.get(event.id, {})) for event in ledger_events],
    )


def _enrich_generic_order_history(orders: list[Order]) -> list[Order]:
    enriched: list[Order] = []
    for order in orders:
        quote_amount = _order_quote_amount(order)
        _base, quote = _split_pair(order.symbol)
        enriched.append(
            order.model_copy(
                update={
                    "quote_currency": quote,
                    "purchase_amount": quote_amount,
                    "cost_basis_amount": quote_amount if order.side == "BUY" else None,
                    "position_status": "unknown",
                }
            )
        )
    return enriched


def _enrich_order_history(
    orders: list[Order],
    market_prices: dict[tuple[str, str], MarketPrice],
    ledger_events: list[BinanceLedgerEvent],
    historical_prices: dict[tuple[str, str, str], HistoricalPrice],
    settings: Settings,
    fx_rates: dict[str, FxRate],
    current_binance_balances: dict[str, float],
) -> tuple[list[Order], list[BinanceLedgerEvent]]:
    binance_orders = [order for order in orders if order.source == "binance"]
    other_orders = [order for order in orders if order.source != "binance"]
    enriched_binance_orders = _enrich_binance_order_history(binance_orders, market_prices, settings, fx_rates)
    enriched_binance_orders, enriched_ledger_events = _enrich_binance_capital_values(
        enriched_binance_orders,
        ledger_events,
        historical_prices,
        settings,
        fx_rates,
        current_binance_balances,
    )
    enriched_by_id = {
        order.id: order
        for order in [
            *enriched_binance_orders,
            *_enrich_generic_order_history(other_orders),
        ]
    }
    return [enriched_by_id.get(order.id, order) for order in orders], enriched_ledger_events


def _binance_cost_basis_by_asset(orders: list[Order]) -> dict[str, list[tuple[str, float]]]:
    cost_basis: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for order in orders:
        if order.source != "binance" or order.side != "BUY":
            continue
        if order.remaining_quantity is None or order.remaining_quantity <= EPSILON:
            continue
        if order.remaining_cost_basis is None or order.remaining_cost_basis <= EPSILON or not order.quote_currency:
            continue
        base, _quote = _split_pair(order.symbol)
        cost_basis[base].append((order.quote_currency, order.remaining_cost_basis))
    return cost_basis


def _required_currencies(
    holdings: list[Holding],
    cash_balances: list[CashBalance],
    market_prices: dict[tuple[str, str], MarketPrice],
) -> set[str]:
    currencies = {holding.currency.upper() for holding in holdings}
    currencies.update(cash.currency.upper() for cash in cash_balances)
    currencies.update(price.currency.upper() for price in market_prices.values())
    currencies.add("BASE")
    return currencies


def _dedupe_cash_balances(cash_balances: list[CashBalance], settings: Settings) -> list[CashBalance]:
    regular: list[CashBalance] = []
    ibkr_rows: list[CashBalance] = []

    for cash in cash_balances:
        if cash.source == "ibkr":
            currency = settings.base_currency if cash.currency.upper() == "BASE" else cash.currency.upper()
            ibkr_rows.append(cash.model_copy(update={"currency": currency}))
        else:
            regular.append(cash)

    if not ibkr_rows:
        return regular

    concrete_rows = [cash for cash in ibkr_rows if cash.currency.upper() != "BASE"] or ibkr_rows
    by_currency: dict[str, CashBalance] = {}
    for cash in concrete_rows:
        key = cash.currency.upper()
        existing = by_currency.get(key)
        if existing is None or cash.updated_at > existing.updated_at:
            by_currency[key] = cash
    return [*regular, *by_currency.values()]


def _snapshot_from_rows(
    settings: Settings,
    holdings: list[Holding],
    cash_balances: list[CashBalance],
    open_orders: list[Order],
    order_history: list[Order],
    sync_status: list[SourceSyncStatus],
    market_prices: dict[tuple[str, str], MarketPrice],
    fx_rates: dict[str, FxRate],
    ledger_events: list[BinanceLedgerEvent],
    historical_prices: dict[tuple[str, str, str], HistoricalPrice],
) -> PortfolioSnapshot:
    warnings = _source_status_warnings(sync_status)
    cash_balances = _dedupe_cash_balances(cash_balances, settings)
    current_binance_balances = _current_binance_balances(holdings, cash_balances)
    order_history, ledger_events = _enrich_order_history(
        order_history,
        market_prices,
        ledger_events,
        historical_prices,
        settings,
        fx_rates,
        current_binance_balances,
    )
    binance_cost_basis = _binance_cost_basis_by_asset(order_history)

    if not holdings and not cash_balances and not open_orders:
        warnings.append("No local portfolio cache yet. Use Refresh to load manual, Binance, or IBKR data into SQLite.")

    platform_values: dict[str, float] = defaultdict(float)
    asset_class_values: dict[str, float] = defaultdict(float)
    invested = 0.0
    cash_total = 0.0
    valued_holdings: list[Holding] = []

    for holding in holdings:
        valued_holding, include_value = _price_for_holding(holding, market_prices, settings, warnings)
        if valued_holding.source == "binance":
            basis_parts = binance_cost_basis.get(valued_holding.symbol.upper(), [])
            converted_basis: list[float] = []
            for currency, amount in basis_parts:
                converted = _convert_between(amount, currency, valued_holding.currency, settings, fx_rates)
                if converted is not None:
                    converted_basis.append(converted)
            if converted_basis:
                cost_basis = sum(converted_basis)
                valued_holding = valued_holding.model_copy(
                    update={
                        "cost_basis": cost_basis,
                        "unrealized_pnl": valued_holding.market_value - cost_basis,
                    }
                )
        value = _convert(valued_holding.market_value, valued_holding.currency, settings, fx_rates, warnings) if include_value else 0
        valued_holding = valued_holding.model_copy(update={"value_in_base": round(value, 2)})
        valued_holdings.append(valued_holding)
        invested += value
        platform_values[valued_holding.platform] += value
        asset_class_values[valued_holding.asset_class] += value

    for cash in cash_balances:
        value = _convert(cash.balance, cash.currency, settings, fx_rates, warnings)
        cash.value_in_base = round(value, 2)
        cash_total += value
        platform_values[cash.platform] += value
        asset_class_values["cash"] += value

    net_worth = invested + cash_total
    top_positions = sorted(
        valued_holdings,
        key=lambda item: _convert(item.market_value, item.currency, settings, fx_rates, []),
        reverse=True,
    )[:10]

    return PortfolioSnapshot(
        generated_at=datetime.now(timezone.utc),
        base_currency=settings.base_currency,
        total_net_worth=round(net_worth, 2),
        total_cash=round(cash_total, 2),
        total_invested=round(invested, 2),
        holdings=valued_holdings,
        cash_balances=cash_balances,
        open_orders=open_orders,
        order_history=order_history,
        ledger_events=sorted(ledger_events, key=lambda event: _event_sort_time(event.created_at), reverse=True),
        platform_breakdown=_breakdown(platform_values, net_worth),
        asset_class_breakdown=_breakdown(asset_class_values, net_worth),
        top_positions=top_positions,
        data_warnings=sorted(set(warnings)),
        source_sync_status=sync_status,
        display_rates=_display_rates(settings, fx_rates),
    )


def build_snapshot(settings: Settings) -> PortfolioSnapshot:
    with connect(settings.data_dir) as conn:
        return _snapshot_from_rows(
            settings,
            load_holdings(conn),
            load_cash_balances(conn),
            load_open_orders(conn),
            load_order_history(conn),
            load_sync_status(conn),
            load_market_prices(conn),
            load_fx_rates(conn, settings.base_currency),
            load_ledger_events(conn),
            load_historical_prices(conn),
        )


def _is_failed_refresh(source: str, result: SourceResult) -> bool:
    if source == "manual":
        return False
    if result.holdings or result.cash_balances or result.open_orders or result.order_history:
        return False
    failure_markers = ("failed", "missing", "not installed", "not configured")
    return any(any(marker in warning.lower() for marker in failure_markers) for warning in result.warnings)


def _sync_status(source: str, result: SourceResult) -> str:
    if _is_failed_refresh(source, result):
        return "error"
    return "warning" if result.warnings else "success"


def _prices_from_source_result(source: str, result: SourceResult) -> list[MarketPrice]:
    prices: list[MarketPrice] = []
    for holding in result.holdings:
        if holding.current_price is None:
            continue
        prices.append(
            MarketPrice(
                symbol=holding.symbol.upper(),
                currency=holding.currency.upper(),
                price=holding.current_price,
                source=source,
                fetched_at=holding.updated_at,
            )
        )
    return prices


def _refresh_one(conn, settings: Settings, source: RefreshSource, progress: RefreshProgressCallback | None = None) -> None:
    if source == "manual":
        result = load_manual_data(settings.data_dir)
        replace_source_result(conn, "manual", result, open_orders=False, order_history=False)
        update_sync_status(conn, "manual", _sync_status("manual", result), result.warnings)
        return

    if source == "binance":
        existing_order_history = load_order_history(conn)
        existing_binance_orders = [order for order in existing_order_history if order.source == "binance"]
        result = fetch_binance(settings, [order.symbol for order in existing_binance_orders])
        if not _is_failed_refresh("binance", result):
            merged_order_history = {
                order.id: order
                for order in [
                    *existing_binance_orders,
                    *result.order_history,
                ]
            }
            replace_source_result(conn, "binance", result, order_history=False)
            replace_order_history(conn, "binance", merged_order_history.values())
            replace_market_prices(conn, _prices_from_source_result("binance", result))
        update_sync_status(conn, "binance", _sync_status("binance", result), result.warnings)
        return

    if source == "binance_ledger":
        events, prices, warnings = fetch_binance_ledger(
            settings,
            load_order_history(conn),
            load_ledger_events(conn),
            load_historical_prices(conn),
            progress=progress,
        )
        replace_ledger_events(conn, "binance", events)
        replace_historical_prices(conn, prices)
        status = "error" if any("missing" in warning.lower() and "credentials" in warning.lower() for warning in warnings) else "warning" if warnings else "success"
        update_sync_status(conn, "binance_ledger", status, warnings)
        return

    if source == "ibkr":
        result = fetch_ibkr(settings)
        if not _is_failed_refresh("ibkr", result):
            replace_source_result(conn, "ibkr", result, order_history=False)
            replace_market_prices(conn, _prices_from_source_result("ibkr", result))
        update_sync_status(conn, "ibkr", _sync_status("ibkr", result), result.warnings)
        return

    if source == "ibkr_history":
        result = fetch_ibkr_history(settings)
        if not _is_failed_refresh("ibkr_history", result):
            replace_source_result(
                conn,
                "ibkr",
                result,
                holdings=False,
                cash_balances=False,
                open_orders=False,
                order_history=True,
            )
        update_sync_status(conn, "ibkr_history", _sync_status("ibkr_history", result), result.warnings)
        return

    if source == "market_data":
        prices, warnings = fetch_market_prices(load_holdings(conn))
        replace_market_prices(conn, prices, clear=True)
        historical_requirements = _historical_price_requirements_from_timeline(
            load_order_history(conn),
            load_ledger_events(conn),
        )
        historical_prices, historical_warnings = fetch_binance_historical_prices(
            settings,
            historical_requirements,
            load_historical_prices(conn),
        )
        replace_historical_prices(conn, historical_prices)
        warnings.extend(historical_warnings)
        update_sync_status(conn, "market_data", "warning" if warnings else "success", warnings)
        return

    if source == "fx":
        market_prices = load_market_prices(conn)
        currencies = _required_currencies(load_holdings(conn), load_cash_balances(conn), market_prices)
        rates, warnings = fetch_fx_rates(settings, currencies)
        replace_fx_rates(conn, rates)
        update_sync_status(conn, "fx", "warning" if warnings else "success", warnings)
        return

    raise ValueError(f"Unsupported refresh source: {source}")


def refresh_steps_for_source(source: RefreshSource) -> list[RefreshSource]:
    if source == "all":
        return [
            "manual",
            "binance",
            "binance_ledger",
            "ibkr",
            "ibkr_history",
            "market_data",
            "fx",
        ]
    if source == "prices_fx":
        return ["market_data", "fx"]
    if source == "binance":
        return ["binance", "binance_ledger"]
    if source == "ibkr":
        return ["ibkr", "ibkr_history"]
    if source == "market_data":
        return ["market_data", "fx"]
    return [source]


def refresh_snapshot(
    settings: Settings,
    source: RefreshSource,
    progress: RefreshProgressCallback | None = None,
) -> PortfolioSnapshot:
    sources = refresh_steps_for_source(source)
    total_steps = len(sources) + 1
    with connect(settings.data_dir) as conn:
        for index, item in enumerate(sources, start=1):
            if progress:
                progress(item, REFRESH_STEP_LABELS.get(item, item), index, total_steps)
            _refresh_one(conn, settings, item, progress)
        conn.commit()
        if progress:
            progress("snapshot", REFRESH_STEP_LABELS["snapshot"], total_steps, total_steps)
        return _snapshot_from_rows(
            settings,
            load_holdings(conn),
            load_cash_balances(conn),
            load_open_orders(conn),
            load_order_history(conn),
            load_sync_status(conn),
            load_market_prices(conn),
            load_fx_rates(conn, settings.base_currency),
            load_ledger_events(conn),
            load_historical_prices(conn),
        )
