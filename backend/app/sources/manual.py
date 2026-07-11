from __future__ import annotations

from pathlib import Path

from app.models import CashBalance, Holding, SourceResult
from app.services.capital import load_manual_capital_entries
from app.services.normalization import as_float


def load_manual_data(data_dir: Path) -> SourceResult:
    entries = load_manual_capital_entries(data_dir)
    cash_balances: list[CashBalance] = []
    holdings: list[Holding] = []

    for entry in entries:
        if entry.kind == "bank_cash":
            balance = as_float(entry.balance)
            if balance == 0:
                continue
            cash_balances.append(
                CashBalance(
                    id=entry.id,
                    source="manual",
                    platform=entry.platform,
                    currency=entry.currency.upper(),
                    balance=balance,
                    purpose=entry.purpose or "other",
                    updated_at=entry.updated_at,
                )
            )
            continue

        quantity = as_float(entry.quantity)
        if quantity == 0:
            continue
        price = as_float(entry.estimated_price)
        market_value = quantity * price
        cost_basis = entry.cost_basis
        holdings.append(
            Holding(
                id=entry.id,
                source="manual",
                platform=entry.platform,
                symbol=(entry.symbol or "").upper(),
                name=entry.name,
                asset_class=entry.asset_class or "manual",
                quantity=quantity,
                currency=entry.currency.upper(),
                current_price=price or None,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=(market_value - cost_basis) if cost_basis is not None and price else None,
                sector=entry.sector,
                vertical=entry.vertical,
                geography=entry.geography,
                confidence="manual_verified",
                updated_at=entry.updated_at,
            )
        )

    return SourceResult(holdings=holdings, cash_balances=cash_balances)
