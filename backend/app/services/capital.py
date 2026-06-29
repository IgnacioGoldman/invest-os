from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


ManualCapitalEntryKind = Literal["bank_cash", "stock", "other_asset"]


class ManualCapitalEntryRequest(BaseModel):
    kind: ManualCapitalEntryKind
    platform: str = Field(min_length=1)
    currency: str = Field(default="EUR", min_length=2, max_length=8)
    account_name: str | None = None
    balance: float | None = None
    purpose: str | None = None
    symbol: str | None = None
    name: str | None = None
    asset_class: str | None = None
    quantity: float | None = None
    estimated_price: float | None = None
    cost_basis: float | None = None
    sector: str | None = None
    vertical: str | None = None
    geography: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_entry(self) -> "ManualCapitalEntryRequest":
        if self.kind == "bank_cash":
            if self.balance is None:
                raise ValueError("Bank cash requires a balance.")
            return self

        if not self.symbol:
            raise ValueError("Assets require a symbol.")
        if self.quantity is None:
            raise ValueError("Assets require a quantity.")
        return self


class ManualCapitalSnapshot(BaseModel):
    cash: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    cash_path: str
    assets_path: str


def _manual_dir(data_dir: Path) -> Path:
    path = data_dir / "manual"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(payload, list):
        raise ValueError(f"{path.name} must contain a YAML list.")
    return [item for item in payload if isinstance(item, dict)]


def _write_yaml_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=False), encoding="utf-8")


def load_manual_capital(data_dir: Path) -> ManualCapitalSnapshot:
    manual_dir = _manual_dir(data_dir)
    cash_path = manual_dir / "cash.yaml"
    assets_path = manual_dir / "assets.yaml"
    return ManualCapitalSnapshot(
        cash=_read_yaml_list(cash_path),
        assets=_read_yaml_list(assets_path),
        cash_path=str(cash_path),
        assets_path=str(assets_path),
    )


def add_manual_capital_entry(data_dir: Path, request: ManualCapitalEntryRequest) -> ManualCapitalSnapshot:
    manual_dir = _manual_dir(data_dir)
    now = datetime.now(timezone.utc).isoformat()

    if request.kind == "bank_cash":
        path = manual_dir / "cash.yaml"
        rows = _read_yaml_list(path)
        rows.append(
            {
                "account_name": request.account_name or request.platform,
                "platform": request.platform,
                "currency": request.currency.upper(),
                "balance": request.balance,
                "purpose": request.purpose or "other",
                "updated_at": now,
                **({"notes": request.notes} if request.notes else {}),
            }
        )
        _write_yaml_list(path, rows)
        return load_manual_capital(data_dir)

    path = manual_dir / "assets.yaml"
    rows = _read_yaml_list(path)
    asset_class = request.asset_class or ("stock" if request.kind == "stock" else "manual")
    rows.append(
        {
            "symbol": (request.symbol or "").upper(),
            "name": request.name or request.symbol,
            "asset_class": asset_class,
            "platform": request.platform,
            "quantity": request.quantity,
            "currency": request.currency.upper(),
            **({"estimated_price": request.estimated_price} if request.estimated_price is not None else {}),
            **({"cost_basis": request.cost_basis} if request.cost_basis is not None else {}),
            **({"sector": request.sector} if request.sector else {}),
            **({"vertical": request.vertical} if request.vertical else {}),
            **({"geography": request.geography} if request.geography else {}),
            "updated_at": now,
            **({"notes": request.notes} if request.notes else {}),
        }
    )
    _write_yaml_list(path, rows)
    return load_manual_capital(data_dir)
