import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"


@dataclass(frozen=True)
class Settings:
    base_currency: str = "EUR"
    data_dir: Path = DATA_DIR
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1
    fx_rates: Dict[str, float] = field(default_factory=lambda: {"EUR": 1.0})
    enable_demo_fallback: bool = True
    market_price_stale_hours: int = 24
    binance_ledger_start_date: datetime = datetime(2020, 1, 1, tzinfo=timezone.utc)
    openai_api_key: str | None = None
    openai_recommendation_model: str = "gpt-5-mini"


def _load_fx_rates(raw: str | None) -> Dict[str, float]:
    rates: Dict[str, float] = {"EUR": 1.0}
    if not raw:
        return rates
    try:
        parsed = json.loads(raw)
        for currency, value in parsed.items():
            rates[str(currency).upper()] = float(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        # Keep settings load non-fatal; the snapshot will warn when conversions are missing.
        pass
    return rates


def _load_datetime(raw: str | None, default: datetime) -> datetime:
    if not raw:
        return default
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return default


def get_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")
    ledger_start = _load_datetime(os.getenv("BINANCE_LEDGER_START_DATE"), datetime(2020, 1, 1, tzinfo=timezone.utc))
    return Settings(
        base_currency=os.getenv("BASE_CURRENCY", "EUR").upper(),
        binance_api_key=os.getenv("BINANCE_API_KEY") or None,
        binance_api_secret=os.getenv("BINANCE_API_SECRET") or None,
        ibkr_host=os.getenv("IBKR_HOST", "127.0.0.1"),
        ibkr_port=int(os.getenv("IBKR_PORT", "7497")),
        ibkr_client_id=int(os.getenv("IBKR_CLIENT_ID", "1")),
        fx_rates=_load_fx_rates(os.getenv("FX_RATES_JSON")),
        enable_demo_fallback=os.getenv("ENABLE_DEMO_FALLBACK", "true").lower() == "true",
        market_price_stale_hours=int(os.getenv("MARKET_PRICE_STALE_HOURS", "24")),
        binance_ledger_start_date=ledger_start,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_recommendation_model=os.getenv("OPENAI_RECOMMENDATION_MODEL", "gpt-5-mini"),
    )
