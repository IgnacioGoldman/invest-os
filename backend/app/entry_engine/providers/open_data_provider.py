from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import requests

from app.config import PROJECT_DIR
from app.entry_engine.data_provider import OpenDataMetricProvider
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
from app.sources.market_data import STOOQ_URL, _stooq_symbols


logger = logging.getLogger(__name__)

SEC_TICKER_MAPPING_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_TICKER_EXCHANGE_MAPPING_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
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
SUPPORTED_FX_CURRENCIES = {"USD", "EUR", "GBP", "DKK", "CHF", "CAD", "TWD", "JPY", "CNY", "HKD"}


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


class OpenDataProvider(OpenDataMetricProvider):
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
        self.stooq_api_key = os.getenv("STOOQ_API_KEY") or None
        self._yfinance_info_cache: dict[str, dict[str, Any] | None] = {}

    def _get(self, url: str, *, timeout: float | None = None, **kwargs: Any) -> requests.Response:
        attempts = self.retry_attempts
        last_error: requests.RequestException | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.get(url, timeout=timeout or self.request_timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                sleep_for = self.retry_backoff * (2 ** (attempt - 1))
                logger.warning("GET failed for %s on attempt %s/%s: %s", url, attempt, attempts, exc)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        assert last_error is not None
        raise last_error

    def get_open_data_snapshot(self, ticker: str) -> OpenDataSnapshot:
        symbol = ticker.upper().strip()
        metadata = self.resolve_company_metadata(symbol)
        cik = int(metadata["cik"])
        companyfacts = self.fetch_companyfacts(cik)
        price_history = self.fetch_price_history(symbol)
        price = self._latest_price_from_history(symbol, price_history) or self.fetch_latest_price(symbol)
        forward_pe_estimate = self.fetch_forward_pe_estimate(symbol)
        market_cap_estimate = self.fetch_market_cap_estimate(symbol)
        company_context = self.fetch_company_context(cik)
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

        if symbol == "GOOGL":
            return dict(GOOGL_FALLBACK_METADATA)
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
                            "region": row.get("region"),
                            "sector": row.get("sector"),
                            "industry": row.get("industry"),
                        }
            self.cache.set("stocks_universe_metadata.json", universe)
        if not isinstance(universe, dict):
            return {}
        row = universe.get(symbol.upper())
        return row if isinstance(row, dict) else {}

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
        cached = self.cache.get(cache_name, timedelta(hours=12))
        if cached is not None:
            return cached
        data = self._sec_get_json(SEC_COMPANYFACTS_URL.format(cik=cik))
        self.cache.set(cache_name, data)
        return data

    def fetch_company_context(self, cik: int) -> OpenDataCompanyContext | None:
        cache_name = f"sec_submissions_CIK{cik:010d}.json"
        submissions = self.cache.get(cache_name, timedelta(hours=12))
        if submissions is None:
            try:
                submissions = self._sec_get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
                self.cache.set(cache_name, submissions)
            except requests.RequestException:
                logger.exception("SEC submissions fetch failed for CIK %s", cik)
                return None
        return self._company_context_from_submissions(cik, submissions)

    def fetch_latest_price(self, ticker: str) -> LatestPrice | None:
        cached = self.cache.get(f"latest_price_{ticker.upper()}.json", timedelta(minutes=45))
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
        cached = self.cache.get(f"price_history_{symbol}.json", timedelta(hours=12))
        if cached is not None:
            try:
                return [HistoricalPricePoint.model_validate(row) for row in cached]
            except ValueError:
                pass

        history = self._fetch_stooq_history(symbol) or self._fetch_yfinance_history(symbol)
        if history:
            self.cache.set(f"price_history_{symbol}.json", [point.model_dump(mode="json") for point in history])
        return history

    def fetch_forward_pe_estimate(self, ticker: str) -> OpenDataMetric | None:
        symbol = ticker.upper().strip()
        cached = self.cache.get(f"forward_pe_estimate_{symbol}.json", timedelta(hours=12))
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
        cached = self.cache.get(f"market_cap_estimate_{symbol}.json", timedelta(hours=12))
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
        cached = self.cache.get(cache_name, timedelta(hours=12))
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
            filing = OpenDataCompanyFiling(
                accession_number=accession_number,
                form=form,
                filing_date=filing_date,
                report_date=self._recent_value(recent, "reportDate", index),
                acceptance_datetime=self._recent_value(recent, "acceptanceDateTime", index),
                primary_document=primary_document,
                primary_document_description=self._recent_value(recent, "primaryDocDescription", index),
                items=self._filing_items(self._recent_value(recent, "items", index)),
                exhibits=self._fetch_filing_exhibits(cik, accession_number),
                source_url=source_url,
                notes="Recent company-specific SEC filing metadata. This is factual context, not an assessment.",
            )
            filings.append(filing)
            if len(filings) >= 8:
                break

        as_of = max((filing.filing_date for filing in filings), default=date.today().isoformat())
        return OpenDataCompanyContext(
            source="sec_submissions",
            as_of=as_of,
            recent_filings=filings,
            notes="Company context is collected from SEC submissions and filing index metadata. The app does not classify the news as good or bad.",
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
        index_json = self.cache.get(cache_name, timedelta(days=7))
        if index_json is None:
            try:
                index_json = self._sec_get_json(f"{SEC_ARCHIVES_BASE_URL}/{cik}/{accession}/index.json")
                self.cache.set(cache_name, index_json)
            except requests.RequestException:
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

    def _latest_price_from_history(self, ticker: str, history: list[HistoricalPricePoint]) -> LatestPrice | None:
        usable_history = [point for point in history if math.isfinite(point.close) and point.close > 0]
        if not usable_history:
            return None
        latest = sorted(usable_history, key=lambda point: point.date)[-1]
        return LatestPrice(
            ticker=ticker.upper(),
            price=latest.close,
            currency="USD",
            source=latest.source,
            as_of=latest.date,
        )

    def _sec_get_json(self, url: str) -> Any:
        response = self._get(
            url,
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
            currency="USD",
            source="yfinance",
            as_of=as_of,
        )

    def _fetch_yfinance_forward_pe(self, ticker: str) -> OpenDataMetric | None:
        info = self._fetch_yfinance_info(ticker)
        if info is None:
            return None

        raw_value = info.get("forwardPE")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if value <= 0:
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
                    volume = float(row["Volume"]) if row.get("Volume") not in (None, "", "N/D") else None
                    if volume is not None and not math.isfinite(volume):
                        volume = None
                    history.append(
                        HistoricalPricePoint(
                            date=raw_date,
                            close=close_value,
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

    def _fetch_yfinance_history(self, ticker: str) -> list[HistoricalPricePoint]:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError:
            return []

        try:
            frame = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=False)
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
                    volume=volume_value,
                    source="yfinance_history",
                )
            )
        history.sort(key=lambda point: point.date)
        return history
