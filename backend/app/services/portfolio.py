from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.config import Settings
from app.models import BreakdownItem, CashBalance, Holding, Order, PortfolioSnapshot, RefreshSource, SourceResult, SourceSyncStatus
from app.services.normalization import stable_id
from app.services.storage import (
    connect,
    load_cash_balances,
    load_holdings,
    load_open_orders,
    load_order_history,
    load_sync_status,
    replace_source_result,
    update_sync_status,
)
from app.sources.binance import fetch_binance
from app.sources.ibkr import fetch_ibkr, fetch_ibkr_history
from app.sources.manual import load_manual_data


def _convert(value: float, currency: str, settings: Settings, warnings: list[str]) -> float:
    currency = currency.upper()
    if currency == settings.base_currency:
        return value
    rate = settings.fx_rates.get(currency)
    if rate is None:
        warnings.append(
            f"Missing FX rate for {currency}->{settings.base_currency}; excluded {value:.2f} {currency} from totals."
        )
        return 0
    return value * rate


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


def _snapshot_from_rows(
    settings: Settings,
    holdings: list[Holding],
    cash_balances: list[CashBalance],
    open_orders: list[Order],
    order_history: list[Order],
    sync_status: list[SourceSyncStatus],
) -> PortfolioSnapshot:
    warnings = _source_status_warnings(sync_status)

    if not holdings and not cash_balances and not open_orders:
        warnings.append("No local portfolio cache yet. Use Refresh to load manual, Binance, or IBKR data into SQLite.")

    platform_values: dict[str, float] = defaultdict(float)
    asset_class_values: dict[str, float] = defaultdict(float)
    invested = 0.0
    cash_total = 0.0

    for holding in holdings:
        value = _convert(holding.market_value, holding.currency, settings, warnings)
        invested += value
        platform_values[holding.platform] += value
        asset_class_values[holding.asset_class] += value

    for cash in cash_balances:
        value = _convert(cash.balance, cash.currency, settings, warnings)
        cash_total += value
        platform_values[cash.platform] += value
        asset_class_values["cash"] += value

    net_worth = invested + cash_total
    top_positions = sorted(holdings, key=lambda item: _convert(item.market_value, item.currency, settings, []), reverse=True)[:10]

    return PortfolioSnapshot(
        generated_at=datetime.now(timezone.utc),
        base_currency=settings.base_currency,
        total_net_worth=round(net_worth, 2),
        total_cash=round(cash_total, 2),
        total_invested=round(invested, 2),
        holdings=holdings,
        cash_balances=cash_balances,
        open_orders=open_orders,
        order_history=order_history,
        platform_breakdown=_breakdown(platform_values, net_worth),
        asset_class_breakdown=_breakdown(asset_class_values, net_worth),
        top_positions=top_positions,
        data_warnings=sorted(set(warnings)),
        source_sync_status=sync_status,
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


def _refresh_one(conn, settings: Settings, source: RefreshSource) -> None:
    if source == "manual":
        result = load_manual_data(settings.data_dir)
        replace_source_result(conn, "manual", result, open_orders=False, order_history=False)
        update_sync_status(conn, "manual", _sync_status("manual", result), result.warnings)
        return

    if source == "binance":
        result = fetch_binance(settings)
        if not _is_failed_refresh("binance", result):
            replace_source_result(conn, "binance", result)
        update_sync_status(conn, "binance", _sync_status("binance", result), result.warnings)
        return

    if source == "ibkr":
        result = fetch_ibkr(settings)
        if not _is_failed_refresh("ibkr", result):
            replace_source_result(conn, "ibkr", result, order_history=False)
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

    raise ValueError(f"Unsupported refresh source: {source}")


def refresh_snapshot(settings: Settings, source: RefreshSource) -> PortfolioSnapshot:
    sources: list[RefreshSource] = ["manual", "binance", "ibkr", "ibkr_history"] if source == "all" else [source]
    with connect(settings.data_dir) as conn:
        for item in sources:
            _refresh_one(conn, settings, item)
        conn.commit()
        return _snapshot_from_rows(
            settings,
            load_holdings(conn),
            load_cash_balances(conn),
            load_open_orders(conn),
            load_order_history(conn),
            load_sync_status(conn),
        )
