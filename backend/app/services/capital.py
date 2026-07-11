from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.services.normalization import parse_datetime, stable_id
from app.services.storage import (
    connect,
    delete_user_capital_entry_payload,
    load_user_capital_entry_payload,
    load_user_capital_entry_payloads,
    save_user_capital_entry_payload,
)


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


class ManualCapitalEntry(ManualCapitalEntryRequest):
    id: str
    updated_at: datetime


class ManualCapitalSnapshot(BaseModel):
    cash: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    cash_path: str = "user_context"
    assets_path: str = "user_context"


def _manual_paths(data_dir: Path) -> tuple[Path, Path]:
    manual_dir = data_dir / "manual"
    return manual_dir / "cash.yaml", manual_dir / "assets.yaml"


def _read_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(payload, list):
        raise ValueError(f"{path.name} must contain a YAML list.")
    return [item for item in payload if isinstance(item, dict)]


def _entry_to_row(entry: ManualCapitalEntry) -> dict[str, Any]:
    return entry.model_dump(mode="json", exclude_none=True)


def _entry_from_request(request: ManualCapitalEntryRequest, entry_id: str | None = None) -> ManualCapitalEntry:
    now = datetime.now(timezone.utc)
    if request.kind == "bank_cash":
        return ManualCapitalEntry(
            id=entry_id or uuid4().hex,
            kind="bank_cash",
            platform=request.platform,
            account_name=request.account_name or request.platform,
            currency=request.currency.upper(),
            balance=request.balance,
            purpose=request.purpose or "other",
            notes=request.notes,
            updated_at=now,
        )

    return ManualCapitalEntry(
        id=entry_id or uuid4().hex,
        kind=request.kind,
        platform=request.platform,
        currency=request.currency.upper(),
        symbol=(request.symbol or "").upper(),
        name=request.name or request.symbol,
        asset_class=request.asset_class or ("stock" if request.kind == "stock" else "manual"),
        quantity=request.quantity,
        estimated_price=request.estimated_price,
        cost_basis=request.cost_basis,
        sector=request.sector,
        vertical=request.vertical,
        geography=request.geography,
        notes=request.notes,
        updated_at=now,
    )


def _entry_from_payload(entry_id: str, updated_at: datetime, payload: str) -> ManualCapitalEntry | None:
    try:
        entry = ManualCapitalEntry.model_validate_json(payload)
    except ValidationError:
        return None
    return entry.model_copy(update={"id": entry.id or entry_id, "updated_at": entry.updated_at or updated_at})


def _save_entry(data_dir: Path, entry: ManualCapitalEntry) -> None:
    with connect(data_dir) as conn:
        save_user_capital_entry_payload(
            conn,
            entry.id,
            entry.kind,
            entry.updated_at,
            entry.model_dump_json(),
        )
        conn.commit()


def _legacy_cash_entry(item: dict[str, Any]) -> ManualCapitalEntry:
    updated_at = parse_datetime(item.get("updated_at"))
    platform = str(item.get("platform") or item.get("account_name") or "Bank")
    account_name = str(item.get("account_name") or platform)
    currency = str(item.get("currency") or "EUR").upper()
    return ManualCapitalEntry(
        id=stable_id("legacy-manual-cash", platform, currency, account_name),
        kind="bank_cash",
        platform=platform,
        account_name=account_name,
        currency=currency,
        balance=float(item.get("balance") or 0),
        purpose=str(item.get("purpose") or "other"),
        notes=item.get("notes"),
        updated_at=updated_at,
    )


def _legacy_asset_entry(item: dict[str, Any]) -> ManualCapitalEntry:
    updated_at = parse_datetime(item.get("updated_at"))
    symbol = str(item.get("symbol") or "").upper()
    platform = str(item.get("platform") or "manual")
    return ManualCapitalEntry(
        id=stable_id("legacy-manual-asset", platform, symbol, item.get("name")),
        kind="stock" if str(item.get("asset_class") or "").lower() in {"stock", "equity", "etf"} else "other_asset",
        platform=platform,
        currency=str(item.get("currency") or "EUR").upper(),
        symbol=symbol,
        name=item.get("name") or symbol,
        asset_class=str(item.get("asset_class") or "manual"),
        quantity=float(item.get("quantity") or 0),
        estimated_price=float(item["estimated_price"]) if item.get("estimated_price") not in (None, "") else None,
        cost_basis=float(item["cost_basis"]) if item.get("cost_basis") not in (None, "") else None,
        sector=item.get("sector"),
        vertical=item.get("vertical"),
        geography=item.get("geography"),
        notes=item.get("notes"),
        updated_at=updated_at,
    )


def migrate_legacy_manual_capital(data_dir: Path) -> int:
    with connect(data_dir) as conn:
        existing = load_user_capital_entry_payloads(conn)
        if existing:
            return 0

    cash_path, assets_path = _manual_paths(data_dir)
    entries = [
        *[_legacy_cash_entry(item) for item in _read_yaml_list(cash_path)],
        *[_legacy_asset_entry(item) for item in _read_yaml_list(assets_path)],
    ]
    if not entries:
        return 0

    with connect(data_dir) as conn:
        for entry in entries:
            save_user_capital_entry_payload(conn, entry.id, entry.kind, entry.updated_at, entry.model_dump_json())
        conn.commit()
    return len(entries)


def load_manual_capital_entries(data_dir: Path) -> list[ManualCapitalEntry]:
    migrate_legacy_manual_capital(data_dir)
    with connect(data_dir) as conn:
        rows = load_user_capital_entry_payloads(conn)
    entries = [
        entry
        for entry in (_entry_from_payload(entry_id, updated_at, payload) for entry_id, _kind, updated_at, payload in rows)
        if entry is not None
    ]
    return entries


def load_manual_capital(data_dir: Path) -> ManualCapitalSnapshot:
    entries = load_manual_capital_entries(data_dir)
    cash = [_entry_to_row(entry) for entry in entries if entry.kind == "bank_cash"]
    assets = [_entry_to_row(entry) for entry in entries if entry.kind != "bank_cash"]
    return ManualCapitalSnapshot(cash=cash, assets=assets)


def add_manual_capital_entry(data_dir: Path, request: ManualCapitalEntryRequest) -> ManualCapitalSnapshot:
    entry = _entry_from_request(request)
    _save_entry(data_dir, entry)
    return load_manual_capital(data_dir)


def update_manual_capital_entry(
    data_dir: Path,
    entry_id: str,
    request: ManualCapitalEntryRequest,
) -> ManualCapitalSnapshot:
    with connect(data_dir) as conn:
        row = load_user_capital_entry_payload(conn, entry_id)
    if row is None:
        raise KeyError(entry_id)

    entry = _entry_from_request(request, entry_id=entry_id)
    _save_entry(data_dir, entry)
    return load_manual_capital(data_dir)


def delete_manual_capital_entry(data_dir: Path, entry_id: str) -> ManualCapitalSnapshot:
    with connect(data_dir) as conn:
        deleted = delete_user_capital_entry_payload(conn, entry_id)
        conn.commit()
    if not deleted:
        raise KeyError(entry_id)
    return load_manual_capital(data_dir)
