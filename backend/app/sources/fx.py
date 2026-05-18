from __future__ import annotations

from datetime import datetime, timezone

import requests

from app.config import Settings
from app.models import FxRate


STABLECOIN_ALIASES = {"USDC", "USDT", "FDUSD"}
FRANKFURTER_URL = "https://api.frankfurter.app/latest"


def canonical_fx_currency(currency: str, base_currency: str) -> str:
    currency = currency.upper()
    if currency == "BASE":
        return base_currency.upper()
    if currency in STABLECOIN_ALIASES:
        return "USD"
    return currency


def fetch_fx_rates(settings: Settings, currencies: set[str]) -> tuple[list[FxRate], list[str]]:
    base_currency = settings.base_currency.upper()
    now = datetime.now(timezone.utc)
    rates: list[FxRate] = [
        FxRate(currency=base_currency, base_currency=base_currency, rate=1.0, source="system", fetched_at=now),
        FxRate(currency="BASE", base_currency=base_currency, rate=1.0, source="system", fetched_at=now),
    ]
    warnings: list[str] = []

    canonical_currencies = {
        canonical_fx_currency(currency, base_currency)
        for currency in currencies
        if currency and canonical_fx_currency(currency, base_currency) != base_currency
    }

    fetched: dict[str, FxRate] = {}
    for currency in sorted(canonical_currencies):
        try:
            response = requests.get(
                FRANKFURTER_URL,
                params={"from": currency, "to": base_currency},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            rate = float(data["rates"][base_currency])
            fetched[currency] = FxRate(
                currency=currency,
                base_currency=base_currency,
                rate=rate,
                source="frankfurter",
                fetched_at=now,
            )
        except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
            warnings.append(f"FX fetch failed for {currency}->{base_currency}: {exc}")

    rates.extend(fetched.values())

    usd_rate = fetched.get("USD")
    if usd_rate:
        for stablecoin in STABLECOIN_ALIASES:
            if stablecoin in {currency.upper() for currency in currencies}:
                rates.append(
                    FxRate(
                        currency=stablecoin,
                        base_currency=base_currency,
                        rate=usd_rate.rate,
                        source="usd-stablecoin-alias",
                        fetched_at=now,
                    )
                )

    return rates, warnings
