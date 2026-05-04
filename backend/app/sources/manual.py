from __future__ import annotations

from pathlib import Path

import yaml

from app.models import CashBalance, Holding, SourceResult
from app.services.normalization import as_float, parse_datetime, stable_id, uppercase


def _load_yaml_list(path: Path) -> tuple[list[dict], str | None]:
    if not path.exists():
        return [], f"Manual file missing: {path}"
    try:
        data = yaml.safe_load(path.read_text()) or []
    except (OSError, yaml.YAMLError) as exc:
        return [], f"Could not read manual file {path}: {exc}"
    if not isinstance(data, list):
        return [], f"Manual file {path} must contain a YAML list."
    return [item for item in data if isinstance(item, dict)], None


def load_manual_data(data_dir: Path) -> SourceResult:
    manual_dir = data_dir / "manual"
    cash_items, cash_warning = _load_yaml_list(manual_dir / "cash.yaml")
    asset_items, asset_warning = _load_yaml_list(manual_dir / "assets.yaml")

    warnings = [warning for warning in [cash_warning, asset_warning] if warning]
    cash_balances: list[CashBalance] = []
    holdings: list[Holding] = []

    for item in cash_items:
        balance = as_float(item.get("balance"))
        if balance == 0:
            continue
        platform = item.get("platform") or item.get("account_name") or "manual"
        currency = uppercase(item.get("currency"), "EUR")
        updated_at = parse_datetime(item.get("updated_at"))
        cash_balances.append(
            CashBalance(
                id=stable_id("manual-cash", platform, currency, item.get("account_name")),
                source="manual",
                platform=str(platform),
                currency=currency,
                balance=balance,
                purpose=str(item.get("purpose") or "other"),
                updated_at=updated_at,
            )
        )

    for item in asset_items:
        quantity = as_float(item.get("quantity"))
        price = as_float(item.get("estimated_price"))
        if quantity == 0:
            continue
        symbol = uppercase(item.get("symbol"))
        currency = uppercase(item.get("currency"), "EUR")
        market_value = quantity * price
        cost_basis = item.get("cost_basis")
        cost_basis_value = as_float(cost_basis) if cost_basis not in (None, "") else None
        holdings.append(
            Holding(
                id=stable_id("manual-asset", item.get("platform"), symbol),
                source="manual",
                platform=str(item.get("platform") or "manual"),
                symbol=symbol,
                name=item.get("name"),
                asset_class=str(item.get("asset_class") or "manual"),
                quantity=quantity,
                currency=currency,
                current_price=price or None,
                market_value=market_value,
                cost_basis=cost_basis_value,
                unrealized_pnl=(market_value - cost_basis_value) if cost_basis_value is not None else None,
                sector=item.get("sector"),
                vertical=item.get("vertical"),
                geography=item.get("geography"),
                confidence="manual_verified" if item.get("updated_at") else "manual_unverified",
                updated_at=parse_datetime(item.get("updated_at")),
            )
        )

    return SourceResult(holdings=holdings, cash_balances=cash_balances, warnings=warnings)
