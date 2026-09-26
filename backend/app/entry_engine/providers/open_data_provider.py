from __future__ import annotations

import csv
import html
import json
import logging
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from pathlib import Path
from typing import Any

import requests

from app.config import PROJECT_DIR
from app.entry_engine.open_data_metrics import compute_open_data_snapshot
from app.entry_engine.open_data_models import (
    HistoricalPricePoint,
    LatestPrice,
    OpenDataCompanyContext,
    OpenDataCompanyFiling,
    OpenDataFilingExhibit,
    OpenDataMetric,
    OpenDataSnapshot,
)


logger = logging.getLogger(__name__)

SEC_TICKER_MAPPING_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_TICKER_EXCHANGE_MAPPING_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
SEC_REQUEST_INTERVAL_SECONDS = float(os.getenv("SEC_REQUEST_INTERVAL_SECONDS", "0.5"))
SEC_429_COOLDOWN_SECONDS = float(os.getenv("SEC_429_COOLDOWN_SECONDS", "30"))
SEC_503_COOLDOWN_SECONDS = float(os.getenv("SEC_503_COOLDOWN_SECONDS", "15"))
SEC_RETRY_AFTER_MAX_SECONDS = float(os.getenv("SEC_RETRY_AFTER_MAX_SECONDS", "120"))
SEC_ARCHIVE_LOOKUP_LIMIT = int(os.getenv("SEC_ARCHIVE_LOOKUP_LIMIT", "2"))
SEC_ARCHIVE_FAILURE_CACHE_TTL = timedelta(hours=float(os.getenv("SEC_ARCHIVE_FAILURE_CACHE_HOURS", "6")))
STOOQ_URL = "https://stooq.com/q/l/"
STOOQ_DAILY_HISTORY_URL = "https://stooq.com/q/d/l/"
FRANKFURTER_LATEST_URL = "https://api.frankfurter.dev/v1/latest"
GOOGL_FALLBACK_CIK = 1652044
GOOGL_FALLBACK_METADATA = {
    "ticker": "GOOGL",
    "name": "Alphabet Inc.",
    "cik": GOOGL_FALLBACK_CIK,
    "exchange": "NASDAQ",
    "country": "US",
    "sector": "Communication Services",
    "industry": "Internet Content & Information",
}
ADR_RATIO_BY_TICKER = {
    "ASML": {
        "ratio": 1.0,
        "source": "ASML New York registry share ratio: 1 ADS represents 1 ordinary share.",
    },
    "AZN": {
        "ratio": 2.0,
        "source": "AstraZeneca ADS ratio: 1 ADS represents 2 ordinary shares.",
    },
    "HSBC": {
        "ratio": 5.0,
        "source": "HSBC ADS ratio: 1 ADS represents 5 ordinary shares.",
    },
    "NVO": {
        "ratio": 1.0,
        "source": "Novo Nordisk ADR ratio: 1 ADR represents 1 B share.",
    },
    "NVS": {
        "ratio": 1.0,
        "source": "Novartis ADR ratio: 1 ADR represents 1 ordinary share.",
    },
    "NOK": {
        "ratio": 1.0,
        "source": "Nokia 2025 Form 20-F: ADSs each represent one share.",
    },
    "TSM": {
        "ratio": 5.0,
        "source": "TSMC ADS ratio: 1 ADS represents 5 common shares.",
    },
}
SUPPORTED_FX_CURRENCIES = {"USD", "EUR", "GBP", "SEK", "DKK", "CHF", "CAD", "TWD", "JPY", "CNY", "HKD"}
ADJUSTED_EPS_LABEL_RE = re.compile(
    r"\b(?:non[-\s]?gaap|adjusted)\s+(?:diluted\s+)?(?:eps|earnings\s+per\s+share)\b",
    re.IGNORECASE,
)
ADJUSTED_EPS_SKIP_RE = re.compile(
    r"\b(?:outlook|guidance|anticipate|anticipated|expect|expected|forecast|estimate|estimated|definition|"
    r"reconciliation|limitation|weighted-average|weighted average|per share amounts|q[1-4]\s+\d{4}\s+outlook)\b",
    re.IGNORECASE,
)
ADJUSTED_EPS_GROWTH_RE = re.compile(
    r"(?:grew|growth(?:\s+of)?|increased|up|rose)\s*(?:by\s*)?([+-]?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


class RequestPacer:
    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0
        self._cooldown_until = 0.0

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                wait_until = max(self._next_allowed_at, self._cooldown_until)
                if now >= wait_until:
                    self._next_allowed_at = now + self.interval_seconds
                    return
                sleep_for = wait_until - now
            time.sleep(sleep_for)

    def cooldown(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)


SEC_REQUEST_PACER = RequestPacer(SEC_REQUEST_INTERVAL_SECONDS)


def _stooq_symbols(symbol: str, currency: str) -> list[str]:
    normalized = symbol.strip().lower()
    if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
        return []
    if "." in normalized:
        return [normalized]
    if currency.upper() == "EUR":
        return [f"{normalized}.de", f"{normalized}.nl", f"{normalized}.mi", f"{normalized}.pa", f"{normalized}.as"]
    if currency.upper() == "GBP":
        return [f"{normalized}.uk", f"{normalized}.us"]
    return [f"{normalized}.us", f"{normalized}.de", f"{normalized}.nl"]


def _positive_float(value: Any) -> float | None:
    if value in (None, "", "N/D"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _finite_float(value: Any) -> float | None:
    if value in (None, "", "N/D"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date_from_yfinance_column(column: Any) -> date | None:
    if hasattr(column, "date"):
        try:
            return column.date()
        except TypeError:
            pass
    raw = str(column)[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _period_start(period_end: date, *, annual: bool) -> date:
    if annual:
        return date(period_end.year, 1, 1)
    month = ((period_end.month - 1) // 3) * 3 + 1
    return date(period_end.year, month, 1)


def _fiscal_period(period_end: date, *, annual: bool) -> str:
    if annual:
        return "FY"
    quarter = ((period_end.month - 1) // 3) + 1
    return f"Q{quarter}"


def _yfinance_fact_row(value: float, period_end: date, *, annual: bool) -> dict[str, Any]:
    return {
        "val": value,
        "start": _period_start(period_end, annual=annual).isoformat(),
        "end": period_end.isoformat(),
        "filed": period_end.isoformat(),
        "form": "YF-ANNUAL" if annual else "YF-QUARTER",
        "fp": _fiscal_period(period_end, annual=annual),
        "fy": period_end.year,
        "frame": f"YF{period_end.year}" if annual else f"YF{period_end.year}{_fiscal_period(period_end, annual=annual)}",
    }


def _frame_value(frame: Any, row_name: str, column: Any) -> float | None:
    try:
        if row_name not in frame.index:
            return None
        return _finite_float(frame.at[row_name, column])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


class JsonFileCache:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or PROJECT_DIR / ".cache" / "open_data"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, name: str, max_age: timedelta) -> Any | None:
        path = self.cache_dir / name
        if not path.exists():
            return None
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if age > max_age:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, name: str, value: Any) -> None:
        path = self.cache_dir / name
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{threading.get_ident()}")
        tmp_path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)


class OpenDataProvider:
    source = "open_free_public"

    def __init__(
        self,
        *,
        cache: JsonFileCache | None = None,
        session: requests.Session | None = None,
        sec_user_agent: str | None = None,
        request_timeout: float = 20,
        retry_attempts: int = 2,
        retry_backoff: float = 0.75,
        include_filing_details: bool = True,
        max_sec_archive_lookups: int | None = None,
        force_refresh: bool = False,
    ) -> None:
        self.cache = cache or JsonFileCache()
        self.session = session or requests.Session()
        self.sec_user_agent = sec_user_agent or os.getenv(
            "SEC_USER_AGENT",
            "Invest OS OpenDataProvider/0.1 contact=local-invest-os@example.com",
        )
        self.request_timeout = request_timeout
        self.retry_attempts = max(1, retry_attempts)
        self.retry_backoff = max(0, retry_backoff)
        self.include_filing_details = include_filing_details
        self.max_sec_archive_lookups = max(
            0,
            SEC_ARCHIVE_LOOKUP_LIMIT if max_sec_archive_lookups is None else max_sec_archive_lookups,
        )
        self.force_refresh = force_refresh
        self.stooq_api_key = os.getenv("STOOQ_API_KEY") or None
        self._yfinance_info_cache: dict[str, dict[str, Any] | None] = {}

    def _get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        pacer: RequestPacer | None = None,
        retry_after_on_429: float | None = None,
        retry_after_by_status: dict[int, float] | None = None,
        retry_sleep_cap: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        attempts = self.retry_attempts
        last_error: requests.RequestException | None = None
        for attempt in range(1, attempts + 1):
            try:
                if pacer is not None:
                    pacer.wait()
                response = self.session.get(url, timeout=timeout or self.request_timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                retry_after = self._retry_after_delay_seconds(exc.response if isinstance(exc, requests.HTTPError) else None)
                status = self._http_status(exc)
                if retry_after is None and status == 429:
                    retry_after = retry_after_on_429
                if retry_after is None and retry_after_by_status is not None and status is not None:
                    retry_after = retry_after_by_status.get(status)
                if retry_after is not None and retry_sleep_cap is not None:
                    retry_after = min(retry_after, retry_sleep_cap)
                if retry_after is not None and pacer is not None:
                    pacer.cooldown(retry_after)
                if attempt >= attempts:
                    break
                sleep_for = max(self.retry_backoff * (2 ** (attempt - 1)), retry_after or 0)
                logger.warning("GET failed for %s on attempt %s/%s: %s", url, attempt, attempts, exc)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        assert last_error is not None
        raise last_error

    def _http_status(self, exc: requests.RequestException) -> int | None:
        response = exc.response if isinstance(exc, requests.HTTPError) else None
        return response.status_code if response is not None else None

    def _retry_after_delay_seconds(self, response: requests.Response | None) -> float | None:
        if response is None:
            return None
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, seconds)

    def get_open_data_snapshot(self, ticker: str) -> OpenDataSnapshot:
        symbol = ticker.upper().strip()
        metadata = self.resolve_company_metadata(symbol)
        raw_cik = metadata.get("cik")
        cik = int(raw_cik) if raw_cik is not None else None
        companyfacts = self.fetch_companyfacts(cik) if cik is not None else self.fetch_yfinance_companyfacts(symbol, metadata)
        price_history = self.fetch_price_history(symbol)
        price_currency = str(metadata.get("currency") or "USD").upper()
        price = self._latest_price_from_history(symbol, price_history, currency=price_currency) or self.fetch_latest_price(symbol)
        forward_pe_estimate = self.fetch_forward_pe_estimate(symbol)
        market_cap_estimate = self.fetch_market_cap_estimate(symbol)
        company_context = self.fetch_company_context(cik) if cik is not None else self._yfinance_company_context(symbol)
        adjusted_eps_growth_yoy = self.fetch_adjusted_eps_growth_yoy(cik) if cik is not None else None
        statement_currency_rates = self.fetch_statement_currency_rates(companyfacts, price)
        adr = ADR_RATIO_BY_TICKER.get(symbol, {"ratio": 1.0, "source": None})
        return compute_open_data_snapshot(
            ticker=symbol,
            cik=cik,
            companyfacts=companyfacts,
            price=price,
            price_history=price_history,
            exchange=metadata.get("exchange"),
            country=metadata.get("country"),
            sector=metadata.get("sector"),
            industry=metadata.get("industry"),
            forward_pe_estimate=forward_pe_estimate,
            company_context=company_context,
            adjusted_eps_growth_yoy=adjusted_eps_growth_yoy,
            statement_currency_rates=statement_currency_rates,
            market_cap_estimate=market_cap_estimate,
            adr_ratio=float(adr["ratio"]),
            adr_ratio_source=adr["source"],
        )

    def resolve_company_metadata(self, ticker: str) -> dict[str, Any]:
        symbol = ticker.upper().strip()
        mapping = self.cache.get("sec_company_tickers_exchange.json", timedelta(days=7))
        if mapping is None:
            try:
                mapping = self._sec_get_json(SEC_TICKER_EXCHANGE_MAPPING_URL)
                self.cache.set("sec_company_tickers_exchange.json", mapping)
            except requests.RequestException:
                logger.exception("SEC ticker exchange mapping fetch failed; using local fallback for %s", symbol)
                mapping = None

        row = self._find_exchange_mapping_row(mapping, symbol)
        if row is not None:
            universe_metadata = self._universe_metadata(symbol)
            metadata = {
                "ticker": row.get("ticker") or symbol,
                "name": universe_metadata.get("name") or row.get("name") or GOOGL_FALLBACK_METADATA["name"],
                "cik": int(row.get("cik") or row.get("cik_str") or GOOGL_FALLBACK_CIK),
                "exchange": row.get("exchange") or GOOGL_FALLBACK_METADATA["exchange"],
                "country": universe_metadata.get("region") or "US",
                "sector": universe_metadata.get("sector") or GOOGL_FALLBACK_METADATA["sector"],
                "industry": universe_metadata.get("industry") or GOOGL_FALLBACK_METADATA["industry"],
            }
            return metadata

        universe_metadata = self._universe_metadata(symbol)
        if universe_metadata.get("cik") is not None:
            return {
                "ticker": symbol,
                "name": universe_metadata.get("name") or GOOGL_FALLBACK_METADATA["name"],
                "cik": int(universe_metadata["cik"]),
                "exchange": universe_metadata.get("exchange") or GOOGL_FALLBACK_METADATA["exchange"],
                "country": universe_metadata.get("country") or universe_metadata.get("region") or "US",
                "sector": universe_metadata.get("sector") or GOOGL_FALLBACK_METADATA["sector"],
                "industry": universe_metadata.get("industry") or GOOGL_FALLBACK_METADATA["industry"],
            }

        if symbol == "GOOGL":
            return dict(GOOGL_FALLBACK_METADATA)
        yahoo_metadata = self._resolve_yfinance_metadata(symbol, universe_metadata)
        if yahoo_metadata is not None:
            return yahoo_metadata
        raise ValueError(f"Could not resolve metadata for {symbol}.")

    def resolve_cik(self, ticker: str) -> int:
        metadata = self.resolve_company_metadata(ticker)
        return int(metadata["cik"])

    def _find_exchange_mapping_row(self, mapping: Any, symbol: str) -> dict[str, Any] | None:
        if isinstance(mapping, dict) and isinstance(mapping.get("fields"), list) and isinstance(mapping.get("data"), list):
            fields = [str(field) for field in mapping["fields"]]
            for raw_row in mapping["data"]:
                if not isinstance(raw_row, list):
                    continue
                row = {field: raw_row[index] for index, field in enumerate(fields) if index < len(raw_row)}
                if str(row.get("ticker") or "").upper() == symbol:
                    return row

        if isinstance(mapping, dict):
            for raw_row in mapping.values():
                if not isinstance(raw_row, dict):
                    continue
                if str(raw_row.get("ticker") or "").upper() == symbol:
                    return raw_row
        return None

    def _universe_metadata(self, symbol: str) -> dict[str, Any]:
        universe = self.cache.get("stocks_universe_metadata.json", timedelta(minutes=15))
        if universe is None:
            universe_path = PROJECT_DIR / "data" / "stocks" / "stocks.json"
            try:
                payload = json.loads(universe_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                universe = {}
            else:
                rows = payload.get("rows") if isinstance(payload, dict) else payload
                universe = {}
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        row_symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
                        if not row_symbol:
                            continue
                        universe[row_symbol] = {
                            "name": row.get("name"),
                            "cik": row.get("cik"),
                            "exchange": row.get("exchange"),
                            "region": row.get("region"),
                            "country": row.get("country"),
                            "sector": row.get("sector"),
                            "industry": row.get("industry"),
                        }
            self.cache.set("stocks_universe_metadata.json", universe)
        if not isinstance(universe, dict):
            return {}
        row = universe.get(symbol.upper())
        return row if isinstance(row, dict) else {}

    def _resolve_yfinance_metadata(self, symbol: str, universe_metadata: dict[str, Any]) -> dict[str, Any] | None:
        info = self._fetch_yfinance_info(symbol)
        if not info:
            return None
        quote_type = str(info.get("quoteType") or "").upper()
        if quote_type and quote_type not in {"EQUITY", "ADR"}:
            return None
        name = (
            universe_metadata.get("name")
            or info.get("longName")
            or info.get("shortName")
            or info.get("displayName")
            or symbol
        )
        currency = str(info.get("currency") or info.get("financialCurrency") or universe_metadata.get("currency") or "USD").upper()
        return {
            "ticker": symbol,
            "name": name,
            "cik": None,
            "exchange": universe_metadata.get("exchange") or info.get("fullExchangeName") or info.get("exchange"),
            "country": universe_metadata.get("country") or universe_metadata.get("region") or info.get("country"),
            "sector": universe_metadata.get("sector") or info.get("sector"),
            "industry": universe_metadata.get("industry") or info.get("industry"),
            "currency": currency,
        }

    def fetch_yfinance_companyfacts(self, ticker: str, metadata: dict[str, Any]) -> dict[str, Any]:
        symbol = ticker.upper().strip()
        cache_name = f"yfinance_companyfacts_{symbol.replace('/', '_')}.json"
        cached = None if self.force_refresh else self.cache.get(cache_name, timedelta(hours=12))
        if cached is not None:
            return cached
        facts = self._build_yfinance_companyfacts(symbol, metadata)
        self.cache.set(cache_name, facts)
        return facts

    def _build_yfinance_companyfacts(self, symbol: str, metadata: dict[str, Any]) -> dict[str, Any]:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError(f"yfinance is required to collect non-SEC fundamentals for {symbol}.") from exc

        ticker = yf.Ticker(symbol)
        info = self._fetch_yfinance_info(symbol) or {}
        currency = str(
            metadata.get("currency")
            or info.get("financialCurrency")
            or info.get("currency")
            or "USD"
        ).upper()
        frames = {
            "income_annual": self._safe_yfinance_frame(ticker, "income_stmt", symbol),
            "income_quarterly": self._safe_yfinance_frame(ticker, "quarterly_income_stmt", symbol),
            "cashflow_annual": self._safe_yfinance_frame(ticker, "cashflow", symbol),
            "cashflow_quarterly": self._safe_yfinance_frame(ticker, "quarterly_cashflow", symbol),
            "balance_annual": self._safe_yfinance_frame(ticker, "balance_sheet", symbol),
            "balance_quarterly": self._safe_yfinance_frame(ticker, "quarterly_balance_sheet", symbol),
        }
        return self._yfinance_companyfacts_from_frames(symbol, metadata, info, frames, currency)

    def _safe_yfinance_frame(self, ticker: Any, attribute: str, symbol: str) -> Any:
        try:
            return getattr(ticker, attribute)
        except Exception as exc:
            logger.warning("yfinance %s fetch failed for %s: %s", attribute, symbol, exc)
            return None

    def _yfinance_companyfacts_from_frames(
        self,
        symbol: str,
        metadata: dict[str, Any],
        info: dict[str, Any],
        frames: dict[str, Any],
        currency: str,
    ) -> dict[str, Any]:
        facts: dict[str, Any] = {"yfinance": {}}

        def add_fact(concept: str, unit: str, row: dict[str, Any]) -> None:
            facts["yfinance"].setdefault(concept, {"units": {}})
            facts["yfinance"][concept]["units"].setdefault(unit, [])
            facts["yfinance"][concept]["units"][unit].append(row)

        def add_frame(frame: Any, mappings: dict[str, tuple[str, str]], *, annual: bool) -> None:
            if frame is None or getattr(frame, "empty", True):
                return
            for column in getattr(frame, "columns", []):
                period_end = _date_from_yfinance_column(column)
                if period_end is None:
                    continue
                for source_row, (concept, unit_kind) in mappings.items():
                    value = _frame_value(frame, source_row, column)
                    if value is None:
                        continue
                    unit = "shares" if unit_kind == "shares" else f"{currency}/shares" if unit_kind == "eps" else currency
                    add_fact(concept, unit, _yfinance_fact_row(value, period_end, annual=annual))

        income_mappings = {
            "Total Revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "currency"),
            "Gross Profit": ("GrossProfit", "currency"),
            "Cost Of Revenue": ("CostOfRevenue", "currency"),
            "Operating Income": ("OperatingIncomeLoss", "currency"),
            "Total Operating Income As Reported": ("OperatingIncomeLoss", "currency"),
            "Net Income": ("NetIncomeLoss", "currency"),
            "Net Income Common Stockholders": ("NetIncomeLoss", "currency"),
            "Diluted EPS": ("EarningsPerShareDiluted", "eps"),
            "Diluted Average Shares": ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
        }
        cashflow_mappings = {
            "Operating Cash Flow": ("NetCashProvidedByUsedInOperatingActivities", "currency"),
            "Capital Expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment", "currency"),
        }
        balance_mappings = {
            "Cash Cash Equivalents And Short Term Investments": ("CashCashEquivalentsAndShortTermInvestments", "currency"),
            "Cash And Cash Equivalents": ("CashAndCashEquivalentsAtCarryingValue", "currency"),
            "Total Debt": ("DebtCurrent", "currency"),
            "Stockholders Equity": ("StockholdersEquity", "currency"),
        }
        add_frame(frames.get("income_annual"), income_mappings, annual=True)
        add_frame(frames.get("income_quarterly"), income_mappings, annual=False)
        add_frame(frames.get("cashflow_annual"), cashflow_mappings, annual=True)
        add_frame(frames.get("cashflow_quarterly"), cashflow_mappings, annual=False)
        add_frame(frames.get("balance_annual"), balance_mappings, annual=True)
        add_frame(frames.get("balance_quarterly"), balance_mappings, annual=False)
        self._add_yfinance_synthetic_facts(facts, frames, currency)

        return {
            "entityName": metadata.get("name") or info.get("longName") or info.get("shortName") or symbol,
            "source": "yfinance_statement_tables",
            "facts": facts,
        }

    def _add_yfinance_synthetic_facts(self, companyfacts: dict[str, Any], frames: dict[str, Any], currency: str) -> None:
        for frame_name, annual in (("income_annual", True), ("income_quarterly", False)):
            frame = frames.get(frame_name)
            if frame is None or getattr(frame, "empty", True):
                continue
            for column in getattr(frame, "columns", []):
                period_end = _date_from_yfinance_column(column)
                if period_end is None:
                    continue
                ebitda = _frame_value(frame, "EBITDA", column)
                operating_income = _frame_value(frame, "Operating Income", column)
                if ebitda is not None and operating_income is not None:
                    self._append_yfinance_fact(
                        companyfacts,
                        "DepreciationAndAmortisationExpense",
                        currency,
                        ebitda - operating_income,
                        period_end,
                        annual=annual,
                    )

        for frame_name, annual in (("cashflow_annual", True), ("cashflow_quarterly", False)):
            frame = frames.get(frame_name)
            if frame is None or getattr(frame, "empty", True):
                continue
            for column in getattr(frame, "columns", []):
                if _frame_value(frame, "Capital Expenditure", column) is not None:
                    continue
                period_end = _date_from_yfinance_column(column)
                if period_end is None:
                    continue
                operating_cash_flow = _frame_value(frame, "Operating Cash Flow", column)
                free_cash_flow = _frame_value(frame, "Free Cash Flow", column)
                if operating_cash_flow is None or free_cash_flow is None:
                    continue
                self._append_yfinance_fact(
                    companyfacts,
                    "PaymentsToAcquirePropertyPlantAndEquipment",
                    currency,
                    operating_cash_flow - free_cash_flow,
                    period_end,
                    annual=annual,
                )

    def _append_yfinance_fact(
        self,
        companyfacts: dict[str, Any],
        concept: str,
        unit: str,
        value: float,
        period_end: date,
        *,
        annual: bool,
    ) -> None:
        taxonomy = (
            companyfacts.setdefault("yfinance", {})
            if "facts" not in companyfacts
            else companyfacts.setdefault("facts", {}).setdefault("yfinance", {})
        )
        taxonomy.setdefault(concept, {"units": {}})
        taxonomy[concept]["units"].setdefault(unit, [])
        taxonomy[concept]["units"][unit].append(_yfinance_fact_row(value, period_end, annual=annual))

    def _yfinance_company_context(self, symbol: str) -> OpenDataCompanyContext:
        return OpenDataCompanyContext(
            source="yfinance",
            as_of=date.today().isoformat(),
            recent_filings=[],
            known_context_gaps=[
                "SEC submissions are unavailable for this non-SEC-listed ticker.",
                "Issuer investor-relations reports are not yet parsed by the deterministic provider.",
            ],
            notes=(
                "Basic market metadata and statement tables are collected from Yahoo Finance/yfinance. "
                "Company filing/news context is not classified."
            ),
        )

    def _legacy_resolve_cik(self, ticker: str) -> int:
        symbol = ticker.upper().strip()
        mapping = self.cache.get("sec_company_tickers.json", timedelta(days=7))
        if mapping is None:
            try:
                mapping = self._sec_get_json(SEC_TICKER_MAPPING_URL)
                self.cache.set("sec_company_tickers.json", mapping)
            except requests.RequestException:
                logger.exception("SEC ticker mapping fetch failed; using local fallback for %s", symbol)
                mapping = None

        if isinstance(mapping, dict):
            for row in mapping.values():
                if not isinstance(row, dict):
                    continue
                if str(row.get("ticker") or "").upper() == symbol:
                    try:
                        return int(row["cik_str"])
                    except (KeyError, TypeError, ValueError):
                        break

        if symbol == "GOOGL":
            return GOOGL_FALLBACK_CIK
        raise ValueError(f"Could not resolve SEC CIK for {symbol}.")

    def fetch_companyfacts(self, cik: int) -> dict[str, Any]:
        cache_name = f"sec_companyfacts_CIK{cik:010d}.json"
        cached = None if self.force_refresh else self.cache.get(cache_name, timedelta(hours=12))
        if cached is not None:
            return cached
        data = self._sec_get_json(SEC_COMPANYFACTS_URL.format(cik=cik))
        self.cache.set(cache_name, data)
        return data

    def fetch_company_context(self, cik: int) -> OpenDataCompanyContext | None:
        submissions = self._fetch_sec_submissions(cik)
        if submissions is None:
            return None
        return self._company_context_from_submissions(cik, submissions)

    def fetch_adjusted_eps_growth_yoy(self, cik: int) -> OpenDataMetric | None:
        cache_name = f"adjusted_eps_growth_CIK{cik:010d}.json"
        cached = None if self.force_refresh else self.cache.get(cache_name, timedelta(hours=12))
        if cached is not None:
            if isinstance(cached, dict) and cached.get("unavailable") is True:
                cached_lookup_limit = cached.get("max_sec_archive_lookups")
                try:
                    lookup_limit = int(cached_lookup_limit) if cached_lookup_limit is not None else None
                except (TypeError, ValueError):
                    lookup_limit = None
                if lookup_limit is not None and lookup_limit >= self.max_sec_archive_lookups:
                    return None
            else:
                try:
                    return OpenDataMetric.model_validate(cached)
                except ValueError:
                    pass
        if not self.include_filing_details or self.max_sec_archive_lookups <= 0:
            return None

        submissions = self._fetch_sec_submissions(cik)
        if submissions is None:
            return None
        metric = self._adjusted_eps_growth_from_submissions(cik, submissions)
        self.cache.set(
            cache_name,
            metric.model_dump(mode="json")
            if metric is not None
            else {"unavailable": True, "max_sec_archive_lookups": self.max_sec_archive_lookups},
        )
        return metric

    def _fetch_sec_submissions(self, cik: int) -> dict[str, Any] | None:
        cache_name = f"sec_submissions_CIK{cik:010d}.json"
        submissions = None if self.force_refresh else self.cache.get(cache_name, timedelta(hours=12))
        if submissions is None:
            try:
                submissions = self._sec_get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
                self.cache.set(cache_name, submissions)
            except requests.RequestException:
                logger.exception("SEC submissions fetch failed for CIK %s", cik)
                return None
        return submissions if isinstance(submissions, dict) else None

    def fetch_latest_price(self, ticker: str) -> LatestPrice | None:
        cached = None if self.force_refresh else self.cache.get(f"latest_price_{ticker.upper()}.json", timedelta(minutes=45))
        if cached is not None:
            try:
                return LatestPrice.model_validate(cached)
            except ValueError:
                pass

        price = self._fetch_yfinance_price(ticker) or self._fetch_stooq_price(ticker)
        if price is not None:
            self.cache.set(f"latest_price_{ticker.upper()}.json", price.model_dump(mode="json"))
        return price

    def fetch_price_history(self, ticker: str) -> list[HistoricalPricePoint]:
        symbol = ticker.upper().strip()
        cached = None if self.force_refresh else self.cache.get(f"price_history_{symbol}.json", timedelta(hours=12))
        if cached is not None:
            try:
                return [HistoricalPricePoint.model_validate(row) for row in cached]
            except ValueError:
                pass

        history = self._fetch_stooq_history(symbol) or self._fetch_yfinance_history(symbol)
        if history:
            self.cache.set(f"price_history_{symbol}.json", [point.model_dump(mode="json") for point in history])
        return history

    def fetch_price_history_since(self, ticker: str, start_date: str) -> list[HistoricalPricePoint]:
        """Fetch a recent daily-candle window for merging into persisted history."""
        symbol = ticker.upper().strip()
        history = self._fetch_yfinance_history(symbol, start_date=start_date)
        if history:
            return history
        return [point for point in self._fetch_stooq_history(symbol) if point.date >= start_date]

    def fetch_forward_pe_estimate(self, ticker: str) -> OpenDataMetric | None:
        symbol = ticker.upper().strip()
        cached = None if self.force_refresh else self.cache.get(f"forward_pe_estimate_{symbol}.json", timedelta(hours=12))
        if cached is not None:
            try:
                return OpenDataMetric.model_validate(cached)
            except ValueError:
                pass

        estimate = self._fetch_yfinance_forward_pe(symbol)
        if estimate is not None:
            self.cache.set(f"forward_pe_estimate_{symbol}.json", estimate.model_dump(mode="json"))
        return estimate

    def fetch_market_cap_estimate(self, ticker: str) -> OpenDataMetric | None:
        symbol = ticker.upper().strip()
        cached = None if self.force_refresh else self.cache.get(f"market_cap_estimate_{symbol}.json", timedelta(hours=12))
        if cached is not None:
            try:
                return OpenDataMetric.model_validate(cached)
            except ValueError:
                pass

        estimate = self._fetch_yfinance_market_cap(symbol)
        if estimate is not None:
            self.cache.set(f"market_cap_estimate_{symbol}.json", estimate.model_dump(mode="json"))
        return estimate

    def fetch_statement_currency_rates(
        self,
        companyfacts: dict[str, Any],
        price: LatestPrice | None,
    ) -> dict[str, OpenDataMetric]:
        if price is None:
            return {}
        target_currency = price.currency.upper()
        currencies = self._statement_monetary_currencies(companyfacts)
        rates: dict[str, OpenDataMetric] = {}
        for currency in sorted(currencies):
            if currency == target_currency:
                continue
            rate = self.fetch_fx_rate(currency, target_currency)
            if rate is not None:
                rates[currency] = rate
        return rates

    def fetch_fx_rate(self, from_currency: str, to_currency: str) -> OpenDataMetric | None:
        source_currency = from_currency.upper()
        target_currency = to_currency.upper()
        if source_currency == target_currency:
            return OpenDataMetric(
                value=1.0,
                source="fx:identity",
                tier="exact_public_fact",
                as_of=date.today().isoformat(),
                notes=f"Identity FX rate for {source_currency}/{target_currency}.",
            )
        cache_name = f"fx_rate_{source_currency}_{target_currency}.json"
        cached = None if self.force_refresh else self.cache.get(cache_name, timedelta(hours=12))
        if cached is not None:
            try:
                return OpenDataMetric.model_validate(cached)
            except ValueError:
                pass

        try:
            response = self._get(
                FRANKFURTER_LATEST_URL,
                params={"base": source_currency, "symbols": target_currency},
                headers={"User-Agent": "Invest OS OpenDataProvider/0.1"},
            )
            data = response.json()
            value = float(data["rates"][target_currency])
            as_of = str(data.get("date") or date.today().isoformat())
            metric = OpenDataMetric(
                value=value,
                source=f"frankfurter:{source_currency}/{target_currency}",
                tier="exact_public_fact",
                as_of=as_of,
                notes=f"Public reference FX rate from Frankfurter for {source_currency} to {target_currency}.",
            )
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            logger.warning("Frankfurter FX fetch failed for %s/%s: %s", source_currency, target_currency, exc)
            metric = self._fetch_yfinance_fx_rate(source_currency, target_currency)
            if metric is None:
                return None

        self.cache.set(cache_name, metric.model_dump(mode="json"))
        return metric

    def _fetch_yfinance_fx_rate(self, from_currency: str, to_currency: str) -> OpenDataMetric | None:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            return None

        for source_currency, target_currency, invert in (
            (from_currency, to_currency, False),
            (to_currency, from_currency, True),
        ):
            ticker = f"{source_currency}{target_currency}=X"
            try:
                history = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
            except Exception as exc:
                logger.warning("yfinance FX fetch failed for %s: %s", ticker, exc)
                continue
            if history is None or history.empty or "Close" not in history:
                continue
            closes = history["Close"].dropna()
            closes = closes[[math.isfinite(float(value)) for value in closes]]
            if closes.empty:
                continue
            close = float(closes.iloc[-1])
            if close <= 0:
                continue
            latest_index = closes.index[-1]
            as_of = latest_index.date().isoformat() if hasattr(latest_index, "date") else date.today().isoformat()
            value = (1 / close) if invert else close
            return OpenDataMetric(
                value=value,
                source=f"yfinance_fx:{from_currency}/{to_currency}",
                tier="proxy_estimate",
                as_of=as_of,
                notes=(
                    f"Free public FX rate from Yahoo Finance for {from_currency} to {to_currency}. "
                    "Used only when the primary Frankfurter reference feed is unavailable for the pair."
                ),
            )
        return None

    def _statement_monetary_currencies(self, companyfacts: dict[str, Any]) -> set[str]:
        currencies: set[str] = set()
        facts = companyfacts.get("facts", {})
        if not isinstance(facts, dict):
            return currencies
        for taxonomy in facts.values():
            if not isinstance(taxonomy, dict):
                continue
            for concept_data in taxonomy.values():
                units = concept_data.get("units", {}) if isinstance(concept_data, dict) else {}
                if not isinstance(units, dict):
                    continue
                for unit in units:
                    currency = str(unit).split("/", 1)[0].upper()
                    if currency in SUPPORTED_FX_CURRENCIES:
                        currencies.add(currency)
        return currencies

    def _company_context_from_submissions(self, cik: int, submissions: Any) -> OpenDataCompanyContext | None:
        if not isinstance(submissions, dict):
            return None
        recent = submissions.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return None
        forms = recent.get("form") if isinstance(recent.get("form"), list) else []
        filings: list[OpenDataCompanyFiling] = []
        target_forms = {"8-K", "10-Q", "10-K"}
        archive_lookups = 0

        for index, raw_form in enumerate(forms):
            form = str(raw_form or "")
            if form not in target_forms:
                continue
            accession_number = self._recent_value(recent, "accessionNumber", index)
            filing_date = self._recent_value(recent, "filingDate", index)
            if not accession_number or not filing_date:
                continue
            source_url = self._filing_source_url(cik, accession_number)
            primary_document = self._recent_value(recent, "primaryDocument", index)
            exhibits: list[OpenDataFilingExhibit] = []
            if self.include_filing_details and archive_lookups < self.max_sec_archive_lookups:
                archive_lookups += 1
                exhibits = self._fetch_filing_exhibits(cik, accession_number)
            filing = OpenDataCompanyFiling(
                accession_number=accession_number,
                form=form,
                filing_date=filing_date,
                report_date=self._recent_value(recent, "reportDate", index),
                acceptance_datetime=self._recent_value(recent, "acceptanceDateTime", index),
                primary_document=primary_document,
                primary_document_description=self._recent_value(recent, "primaryDocDescription", index),
                items=self._filing_items(self._recent_value(recent, "items", index)),
                exhibits=exhibits,
                source_url=source_url,
                notes="Recent company-specific SEC filing metadata. This is factual context, not an assessment.",
            )
            filings.append(filing)
            if len(filings) >= 8:
                break

        as_of = max((filing.filing_date for filing in filings), default=date.today().isoformat())
        known_context_gaps: list[str] = []
        if not self.include_filing_details:
            known_context_gaps.append("SEC filing archive exhibit details were skipped for batch collection scalability.")
        elif archive_lookups < len(filings):
            known_context_gaps.append(
                f"SEC filing archive exhibit lookups were limited to the {archive_lookups} newest filings "
                "to keep EDGAR requests moderate."
            )
        return OpenDataCompanyContext(
            source="sec_submissions",
            as_of=as_of,
            recent_filings=filings,
            known_context_gaps=known_context_gaps,
            notes=(
                "Company context is collected from SEC submissions and filing index metadata. "
                "The app does not classify the news as good or bad."
                if self.include_filing_details
                else (
                    "Company context is collected from SEC submissions metadata. "
                    "Per-filing archive exhibit lookups were skipped for batch collection scalability. "
                    "The app does not classify the news as good or bad."
                )
            ),
        )

    def _recent_value(self, recent: dict[str, Any], key: str, index: int) -> str | None:
        values = recent.get(key)
        if not isinstance(values, list) or index >= len(values):
            return None
        value = values[index]
        if value in (None, ""):
            return None
        return str(value)

    def _filing_items(self, raw_items: str | None) -> list[str]:
        if not raw_items:
            return []
        return [item.strip() for item in raw_items.replace(";", ",").split(",") if item.strip()]

    def _filing_source_url(self, cik: int, accession_number: str) -> str:
        accession = accession_number.replace("-", "")
        return f"{SEC_ARCHIVES_BASE_URL}/{cik}/{accession}/"

    def _fetch_filing_exhibits(self, cik: int, accession_number: str) -> list[OpenDataFilingExhibit]:
        accession = accession_number.replace("-", "")
        cache_name = f"sec_filing_index_CIK{cik:010d}_{accession}.json"
        failure_cache_name = f"sec_filing_index_failure_CIK{cik:010d}_{accession}.json"
        if not self.force_refresh and self.cache.get(failure_cache_name, SEC_ARCHIVE_FAILURE_CACHE_TTL) is not None:
            return []
        index_json = None if self.force_refresh else self.cache.get(cache_name, timedelta(days=7))
        if index_json is None:
            index_url = f"{SEC_ARCHIVES_BASE_URL}/{cik}/{accession}/index.json"
            try:
                index_json = self._sec_get_json(index_url)
                self.cache.set(cache_name, index_json)
            except requests.RequestException as exc:
                self.cache.set(
                    failure_cache_name,
                    {
                        "unavailable": True,
                        "url": index_url,
                        "status": self._http_status(exc),
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                return []
        directory_items = index_json.get("directory", {}).get("item", []) if isinstance(index_json, dict) else []
        if not isinstance(directory_items, list):
            return []
        exhibits: list[OpenDataFilingExhibit] = []
        for item in directory_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            description = str(item.get("description") or "") or None
            filing_type = str(item.get("type") or "") or None
            if not self._is_meaningful_filing_exhibit(name, filing_type, description):
                continue
            exhibit_type = self._infer_exhibit_type(name, filing_type, description)
            exhibits.append(
                OpenDataFilingExhibit(
                    document=name,
                    description=description,
                    type=exhibit_type,
                    url=f"{SEC_ARCHIVES_BASE_URL}/{cik}/{accession}/{name}" if name else None,
                )
            )
            if len(exhibits) >= 8:
                break
        return exhibits

    def _adjusted_eps_growth_from_submissions(self, cik: int, submissions: dict[str, Any]) -> OpenDataMetric | None:
        if not self.include_filing_details or self.max_sec_archive_lookups <= 0:
            return None
        recent = submissions.get("filings", {}).get("recent", {})
        if not isinstance(recent, dict):
            return None
        forms = recent.get("form") if isinstance(recent.get("form"), list) else []
        archive_lookups = 0
        for index, raw_form in enumerate(forms):
            form = str(raw_form or "")
            if form not in {"8-K", "6-K"}:
                continue
            accession_number = self._recent_value(recent, "accessionNumber", index)
            filing_date = self._recent_value(recent, "filingDate", index)
            if not accession_number or not filing_date:
                continue
            items = self._filing_items(self._recent_value(recent, "items", index))
            if form == "8-K" and items and not any(item.startswith("2.02") or item.startswith("9.01") for item in items):
                continue
            if archive_lookups >= self.max_sec_archive_lookups:
                break
            archive_lookups += 1
            for exhibit in self._earnings_release_exhibits(cik, accession_number):
                if not exhibit.url:
                    continue
                text = self._fetch_sec_document_text(cik, accession_number, exhibit.document, exhibit.url)
                if not text:
                    continue
                parsed = self._parse_adjusted_eps_growth_yoy(text)
                if parsed is None:
                    continue
                return OpenDataMetric(
                    value=parsed,
                    source=f"sec_earnings_release:{exhibit.url}",
                    tier="exact_public_fact",
                    as_of=filing_date,
                    notes=(
                        "Adjusted EPS growth YoY parsed from an official SEC earnings-release exhibit. "
                        "Accepted only when a high-confidence Non-GAAP EPS or Adjusted EPS row states a YoY percentage."
                    ),
                )
        return None

    def _earnings_release_exhibits(self, cik: int, accession_number: str) -> list[OpenDataFilingExhibit]:
        exhibits = self._fetch_filing_exhibits(cik, accession_number)
        scored: list[tuple[int, OpenDataFilingExhibit]] = []
        for exhibit in exhibits:
            haystack = " ".join(
                value.lower()
                for value in (exhibit.document, exhibit.description or "", exhibit.type or "")
                if value
            )
            if "99" not in haystack and "earnings" not in haystack and "press" not in haystack:
                continue
            score = 0
            if (exhibit.type or "").upper().startswith("EX-99"):
                score += 4
            if "earnings" in haystack:
                score += 3
            if "result" in haystack or "financial" in haystack:
                score += 2
            if "press" in haystack or "release" in haystack:
                score += 2
            if "99.1" in haystack:
                score += 1
            scored.append((score, exhibit))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [exhibit for score, exhibit in scored if score >= 3][:3]

    def _fetch_sec_document_text(self, cik: int, accession_number: str, document_name: str, url: str) -> str | None:
        accession = accession_number.replace("-", "")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", document_name)[:120]
        cache_name = f"sec_document_CIK{cik:010d}_{accession}_{safe_name}.json"
        cached = None if self.force_refresh else self.cache.get(cache_name, timedelta(days=7))
        if isinstance(cached, dict) and isinstance(cached.get("text"), str):
            return cached["text"]
        try:
            response = self._get(
                url,
                pacer=SEC_REQUEST_PACER,
                retry_after_on_429=SEC_429_COOLDOWN_SECONDS,
                retry_after_by_status={503: SEC_503_COOLDOWN_SECONDS},
                retry_sleep_cap=SEC_RETRY_AFTER_MAX_SECONDS,
                headers={
                    "User-Agent": self.sec_user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        except requests.RequestException:
            return None
        text = response.text
        self.cache.set(cache_name, {"text": text})
        return text

    def _parse_adjusted_eps_growth_yoy(self, raw_text: str) -> float | None:
        lines = self._document_text_lines(raw_text)
        for line in lines:
            if not ADJUSTED_EPS_LABEL_RE.search(line):
                continue
            if ADJUSTED_EPS_SKIP_RE.search(line):
                continue
            label_match = ADJUSTED_EPS_LABEL_RE.search(line)
            if label_match is None:
                continue
            after_label = line[label_match.end():]
            growth_match = ADJUSTED_EPS_GROWTH_RE.search(after_label)
            if growth_match:
                return float(growth_match.group(1))
            percent_matches = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*(?:\|\s*)?%", after_label)
            if len(percent_matches) == 1:
                return float(percent_matches[0])
        return None

    def _document_text_lines(self, raw_text: str) -> list[str]:
        text = re.sub(r"</(?:td|th)[^>]*>", " | ", raw_text, flags=re.IGNORECASE)
        text = re.sub(r"</(?:tr|p|div|br|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text).replace("\xa0", " ")
        lines = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" \t|")
            if line:
                lines.append(line)
        return lines

    def _is_meaningful_filing_exhibit(
        self,
        document_name: str,
        filing_type: str | None,
        description: str | None,
    ) -> bool:
        name = document_name.lower()
        if not name:
            return False
        if name.endswith((".gif", ".jpg", ".jpeg", ".png", ".css", ".js", ".xsd", ".xml")):
            return False
        upper_type = (filing_type or "").upper()
        upper_description = (description or "").upper()
        upper_name = document_name.upper()
        if upper_type.startswith("EX-"):
            return True
        if upper_name.startswith("EX-") or upper_name.startswith("EX"):
            return True
        if name.endswith((".htm", ".html")) and "exhibit" in name:
            return True
        if name.endswith((".htm", ".html")) and (
            "earnings" in name
            or ("press" in name and "relea" in name)
            or "results" in name
        ):
            return True
        if "EX-99" in upper_description or "EX-10" in upper_description:
            return True
        return False

    def _infer_exhibit_type(
        self,
        document_name: str,
        filing_type: str | None,
        description: str | None,
    ) -> str | None:
        upper_type = (filing_type or "").upper()
        if upper_type.startswith("EX-"):
            return upper_type
        upper_description = (description or "").upper()
        match = re.search(r"EX[-\s]?(\d{1,3})(?:[._-]?(\d{1,2}))?", upper_description)
        if match:
            suffix = f".{match.group(2)}" if match.group(2) else ""
            return f"EX-{match.group(1)}{suffix}"
        name = document_name.lower()
        match = re.search(r"exhibit(\d+)", name)
        if match:
            return self._format_compact_exhibit_number(match.group(1))
        match = re.search(r"dex(\d+)", name)
        if match:
            return self._format_compact_exhibit_number(match.group(1))
        return upper_type or None

    def _format_compact_exhibit_number(self, digits: str) -> str:
        if digits.startswith("99") and len(digits) > 2:
            return f"EX-99.{digits[2:].lstrip('0') or digits[2:]}"
        if digits.startswith("10") and len(digits) > 2:
            return f"EX-10.{digits[2:].lstrip('0') or digits[2:]}"
        if digits.startswith("31") and len(digits) > 2:
            return f"EX-31.{digits[2:].lstrip('0') or digits[2:]}"
        if digits.startswith("32") and len(digits) > 2:
            return f"EX-32.{digits[2:].lstrip('0') or digits[2:]}"
        if digits.startswith("4") and len(digits) > 1:
            return f"EX-4.{digits[1:].lstrip('0') or digits[1:]}"
        return f"EX-{digits}"

    def _latest_price_from_history(
        self,
        ticker: str,
        history: list[HistoricalPricePoint],
        *,
        currency: str = "USD",
    ) -> LatestPrice | None:
        usable_history = [point for point in history if math.isfinite(point.close) and point.close > 0]
        if not usable_history:
            return None
        latest = sorted(usable_history, key=lambda point: point.date)[-1]
        return LatestPrice(
            ticker=ticker.upper(),
            price=latest.close,
            currency=currency.upper(),
            source=latest.source,
            as_of=latest.date,
        )

    def _sec_get_json(self, url: str) -> Any:
        response = self._get(
            url,
            pacer=SEC_REQUEST_PACER,
            retry_after_on_429=SEC_429_COOLDOWN_SECONDS,
            retry_after_by_status={503: SEC_503_COOLDOWN_SECONDS},
            retry_sleep_cap=SEC_RETRY_AFTER_MAX_SECONDS,
            headers={
                "User-Agent": self.sec_user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        return response.json()

    def _fetch_yfinance_price(self, ticker: str) -> LatestPrice | None:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            history = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
        except Exception:
            logger.exception("yfinance price fetch failed for %s", ticker)
            return None

        if history is None or history.empty or "Close" not in history:
            return None
        closes = history["Close"].dropna()
        closes = closes[[math.isfinite(float(value)) for value in closes]]
        if closes.empty:
            return None
        latest_index = closes.index[-1]
        as_of = latest_index.date().isoformat() if hasattr(latest_index, "date") else date.today().isoformat()
        return LatestPrice(
            ticker=ticker.upper(),
            price=float(closes.iloc[-1]),
            currency=self._yfinance_currency(ticker),
            source="yfinance",
            as_of=as_of,
        )

    def _yfinance_currency(self, ticker: str) -> str:
        info = self._fetch_yfinance_info(ticker) or {}
        return str(info.get("currency") or info.get("financialCurrency") or "USD").upper()

    def _fetch_yfinance_forward_pe(self, ticker: str) -> OpenDataMetric | None:
        info = self._fetch_yfinance_info(ticker)
        if info is None:
            return None

        raw_value = info.get("forwardPE")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        return OpenDataMetric(
            value=value,
            source="yfinance:forwardPE",
            tier="proxy_estimate",
            as_of=date.today().isoformat(),
            notes=(
                "Free public forward PE estimate from yfinance/Yahoo Finance. "
                "This is not an SEC fact, and the underlying analyst-estimate methodology is not independently verified by this app."
            ),
        )

    def _fetch_yfinance_market_cap(self, ticker: str) -> OpenDataMetric | None:
        info = self._fetch_yfinance_info(ticker)
        if info is None:
            return None

        raw_value = info.get("marketCap")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return OpenDataMetric(
            value=value,
            source="yfinance:marketCap",
            tier="proxy_estimate",
            as_of=date.today().isoformat(),
            notes=(
                "Free public market-cap estimate from yfinance/Yahoo Finance. "
                "Used when SEC diluted shares are unavailable, so this is not an SEC-derived market cap."
            ),
        )

    def _fetch_yfinance_info(self, ticker: str) -> dict[str, Any] | None:
        symbol = ticker.upper().strip()
        if symbol in self._yfinance_info_cache:
            return self._yfinance_info_cache[symbol]
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            self._yfinance_info_cache[symbol] = None
            return None

        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            logger.warning("yfinance info fetch failed for %s: %s", symbol, exc)
            self._yfinance_info_cache[symbol] = None
            return None
        if not isinstance(info, dict):
            self._yfinance_info_cache[symbol] = None
            return None
        self._yfinance_info_cache[symbol] = info
        return info

    def _fetch_stooq_price(self, ticker: str) -> LatestPrice | None:
        for query_symbol in _stooq_symbols(ticker, "USD"):
            try:
                response = self._get(
                    STOOQ_URL,
                    params={"s": query_symbol, "f": "sd2t2c", "h": "", "e": "csv"},
                    timeout=min(self.request_timeout, 10),
                )
            except requests.RequestException:
                continue

            rows = list(csv.DictReader(StringIO(response.text)))
            if not rows:
                continue
            row = rows[0]
            close = row.get("Close")
            raw_date = row.get("Date")
            if not close or close == "N/D":
                continue
            try:
                close_value = float(close)
                if not math.isfinite(close_value) or close_value <= 0:
                    continue
                return LatestPrice(
                    ticker=ticker.upper(),
                    price=close_value,
                    currency="USD",
                    source=f"stooq:{query_symbol.upper()}",
                    as_of=raw_date if raw_date and raw_date != "N/D" else date.today().isoformat(),
                )
            except ValueError:
                continue

        return None

    def _fetch_stooq_history(self, ticker: str) -> list[HistoricalPricePoint]:
        for query_symbol in _stooq_symbols(ticker, "USD"):
            try:
                response = self._get(
                    STOOQ_DAILY_HISTORY_URL,
                    params={
                        "s": query_symbol,
                        "i": "d",
                        **({"apikey": self.stooq_api_key} if self.stooq_api_key else {}),
                    },
                )
            except requests.RequestException:
                continue

            rows = list(csv.DictReader(StringIO(response.text)))
            history: list[HistoricalPricePoint] = []
            for row in rows:
                raw_date = row.get("Date")
                close = row.get("Close")
                if not raw_date or not close or close == "N/D":
                    continue
                try:
                    close_value = float(close)
                    if not math.isfinite(close_value) or close_value <= 0:
                        continue
                    high_value = _positive_float(row.get("High"))
                    low_value = _positive_float(row.get("Low"))
                    volume = float(row["Volume"]) if row.get("Volume") not in (None, "", "N/D") else None
                    if volume is not None and not math.isfinite(volume):
                        volume = None
                    history.append(
                        HistoricalPricePoint(
                            date=raw_date,
                            close=close_value,
                            high=high_value,
                            low=low_value,
                            volume=volume,
                            source=f"stooq_history:{query_symbol.upper()}",
                        )
                    )
                except ValueError:
                    continue
            if history:
                history.sort(key=lambda point: point.date)
                return history

        return []

    def _fetch_yfinance_history(self, ticker: str, *, start_date: str | None = None) -> list[HistoricalPricePoint]:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            return []

        try:
            history_args: dict[str, Any] = {"interval": "1d", "auto_adjust": False}
            if start_date:
                history_args["start"] = start_date
            else:
                history_args["period"] = "max"
            frame = yf.Ticker(ticker).history(**history_args)
        except Exception:
            logger.exception("yfinance historical price fetch failed for %s", ticker)
            return []

        if frame is None or frame.empty or "Close" not in frame:
            return []

        history: list[HistoricalPricePoint] = []
        for index, row in frame.iterrows():
            close = row.get("Close")
            if close is None:
                continue
            try:
                close_value = float(close)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(close_value) or close_value <= 0:
                continue
            as_of = index.date().isoformat() if hasattr(index, "date") else str(index)[:10]
            high_value = _positive_float(row.get("High"))
            low_value = _positive_float(row.get("Low"))
            volume = row.get("Volume")
            try:
                volume_value = float(volume) if volume is not None else None
                if volume_value is not None and not math.isfinite(volume_value):
                    volume_value = None
            except (TypeError, ValueError):
                volume_value = None
            history.append(
                HistoricalPricePoint(
                    date=as_of,
                    close=close_value,
                    high=high_value,
                    low=low_value,
                    volume=volume_value,
                    source="yfinance_history",
                )
            )
        history.sort(key=lambda point: point.date)
        return history
