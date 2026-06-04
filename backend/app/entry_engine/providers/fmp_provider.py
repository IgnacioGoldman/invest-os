from __future__ import annotations

import logging
import math
import os
import time
from datetime import date, timedelta
from typing import Any

import requests

from app.entry_engine.data_provider import DataProvider
from app.entry_engine.models import BusinessHealth, PriceOpportunity, StockUniverseItem, Valuation
from app.entry_engine.utils.http import RetryConfig, get_json


logger = logging.getLogger(__name__)


class FMPProvider(DataProvider):
    source = "fmp"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://financialmodelingprep.com/stable",
        request_delay_seconds: float | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("FMP_API_KEY is not configured.")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.retry_config = retry_config or RetryConfig()
        self.request_delay_seconds = (
            request_delay_seconds
            if request_delay_seconds is not None
            else float(os.getenv("FMP_REQUEST_DELAY_SECONDS", "0.15"))
        )
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], Any] = {}

    def get_top_liquid_stocks(self, limit: int) -> list[StockUniverseItem]:
        rows = self._request(
            "company-screener",
            {
                "isActivelyTrading": "true",
                "isEtf": "false",
                "limit": max(limit * 3, limit),
            },
        )
        items = [self._universe_item(row) for row in self._rows(rows)]
        filtered = [item for item in items if item.ticker]
        filtered.sort(key=lambda item: ((item.avg_volume or 0), (item.market_cap or 0)), reverse=True)
        return filtered[:limit]

    def get_business_health(self, ticker: str) -> BusinessHealth:
        income = self._rows(self._request("income-statement", {"symbol": ticker, "period": "annual", "limit": 4}))
        balance = self._rows(
            self._request("balance-sheet-statement", {"symbol": ticker, "period": "annual", "limit": 1})
        )
        cashflow = self._rows(
            self._request("cash-flow-statement", {"symbol": ticker, "period": "annual", "limit": 1})
        )
        ratios = self._rows(self._request("ratios", {"symbol": ticker, "period": "annual", "limit": 1}))
        key_metrics = self._rows(self._request("key-metrics", {"symbol": ticker, "period": "annual", "limit": 1}))

        latest_income = self._first(income)
        latest_balance = self._first(balance)
        latest_cashflow = self._first(cashflow)
        latest_ratios = self._first(ratios)
        latest_key_metrics = self._first(key_metrics)

        revenue_series = [self._number(row, "revenue") for row in income]
        eps_series = [
            self._number(row, "epsdiluted", "epsDiluted", "dilutedEPS", "eps")
            for row in income
        ]

        cash = self._number(latest_balance, "cashAndCashEquivalents", "cashAndShortTermInvestments")
        debt = self._number(latest_balance, "totalDebt")
        if debt is None:
            short_debt = self._number(latest_balance, "shortTermDebt")
            long_debt = self._number(latest_balance, "longTermDebt")
            debt = self._sum_optional(short_debt, long_debt)

        fcf = self._number(latest_cashflow, "freeCashFlow")
        if fcf is None:
            operating_cash = self._number(latest_cashflow, "netCashProvidedByOperatingActivities", "operatingCashFlow")
            capex = self._number(latest_cashflow, "capitalExpenditure", "capitalExpenditures")
            fcf = self._sum_optional(operating_cash, capex)

        return BusinessHealth(
            revenue_growth_yoy=self._growth_pct(revenue_series, 0, 1),
            revenue_cagr_3y=self._cagr_pct(revenue_series, 0, 3),
            eps_growth_yoy=self._growth_pct(eps_series, 0, 1),
            eps_cagr_3y=self._cagr_pct(eps_series, 0, 3),
            gross_margin=self._ratio_pct(
                latest_income,
                "grossProfitRatio",
                numerator_key="grossProfit",
                denominator_key="revenue",
            ),
            operating_margin=self._ratio_pct(
                latest_income,
                "operatingIncomeRatio",
                numerator_key="operatingIncome",
                denominator_key="revenue",
            ),
            net_margin=self._ratio_pct(
                latest_income,
                "netIncomeRatio",
                numerator_key="netIncome",
                denominator_key="revenue",
            ),
            free_cash_flow=fcf,
            roe=self._percent_value(self._number(latest_ratios, "returnOnEquity", "returnOnEquityRatio")),
            roic=self._percent_value(
                self._number(
                    latest_key_metrics,
                    "roic",
                    "returnOnInvestedCapital",
                    "returnOnCapitalEmployed",
                )
            ),
            cash=cash,
            debt=debt,
            debt_to_equity=self._number(latest_ratios, "debtEquityRatio", "debtToEquity"),
        )

    def get_price_opportunity(self, ticker: str) -> PriceOpportunity:
        quote = self._first(self._rows(self._request("quote", {"symbol": ticker})))
        history = self._historical_prices(ticker)
        current_price = self._number(quote, "price") or (history[0]["close"] if history else None)
        if current_price is None:
            return PriceOpportunity()

        year_high = self._number(quote, "yearHigh", "priceAvg200")
        year_low = self._number(quote, "yearLow")
        last_year = [row["close"] for row in history[:260] if row.get("close") is not None]
        if year_high is None and last_year:
            year_high = max(last_year)
        if year_low is None and last_year:
            year_low = min(last_year)
        all_closes = [row["close"] for row in history if row.get("close") is not None]
        ath = max(all_closes) if all_closes else None

        return PriceOpportunity(
            current_price=current_price,
            change_1d=self._number(quote, "changesPercentage")
            if self._number(quote, "changesPercentage") is not None
            else self._period_change(current_price, history, 1),
            change_1w=self._period_change(current_price, history, 7),
            change_1m=self._period_change(current_price, history, 30),
            change_3m=self._period_change(current_price, history, 91),
            change_6m=self._period_change(current_price, history, 182),
            change_1y=self._period_change(current_price, history, 365),
            change_2y=self._period_change(current_price, history, 365 * 2),
            change_5y=self._period_change(current_price, history, 365 * 5),
            distance_from_ath=self._distance_pct(current_price, ath),
            distance_from_52w_high=self._distance_pct(current_price, year_high),
            distance_from_52w_low=self._distance_pct(current_price, year_low),
        )

    def get_valuation(self, ticker: str) -> Valuation:
        quote = self._first(self._rows(self._request("quote", {"symbol": ticker})))
        ratios = self._first(self._rows(self._request("ratios", {"symbol": ticker, "period": "annual", "limit": 1})))
        key_metrics = self._first(
            self._rows(self._request("key-metrics", {"symbol": ticker, "period": "annual", "limit": 1}))
        )
        market_cap = self._number(quote, "marketCap") or self._number(key_metrics, "marketCap")
        free_cash_flow = self._number(key_metrics, "freeCashFlowPerShare")
        if free_cash_flow is not None and market_cap is not None:
            shares = self._number(quote, "sharesOutstanding")
            free_cash_flow = free_cash_flow * shares if shares else None

        fcf_yield = self._percent_value(self._number(key_metrics, "freeCashFlowYield", "fcfYield"))
        if fcf_yield is None and free_cash_flow is not None and market_cap:
            fcf_yield = (free_cash_flow / market_cap) * 100

        return Valuation(
            pe=self._number(quote, "pe") or self._number(ratios, "priceEarningsRatio", "peRatio"),
            forward_pe=self._number(quote, "forwardPE", "forwardPe") or self._number(key_metrics, "forwardPE"),
            peg=self._number(ratios, "priceEarningsToGrowthRatio", "pegRatio") or self._number(key_metrics, "pegRatio"),
            price_to_sales=self._number(ratios, "priceToSalesRatio") or self._number(key_metrics, "priceToSalesRatio"),
            ev_to_ebitda=self._number(
                key_metrics,
                "enterpriseValueOverEBITDA",
                "enterpriseValueOverEbitda",
                "evToEbitda",
            ),
            fcf_yield=fcf_yield,
        )

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        request_params = {**(params or {}), "apikey": self.api_key}
        cache_key = (path, tuple(sorted((key, str(value)) for key, value in request_params.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)

        data = get_json(
            self.session,
            f"{self.base_url}/{path.lstrip('/')}",
            params=request_params,
            retry_config=self.retry_config,
        )
        self._cache[cache_key] = data
        return data

    def _historical_prices(self, ticker: str) -> list[dict[str, Any]]:
        start = (date.today() - timedelta(days=365 * 6)).isoformat()
        rows = self._rows(self._request("historical-price-eod/full", {"symbol": ticker, "from": start}))
        if len(rows) == 1 and isinstance(rows[0].get("historical"), list):
            rows = rows[0]["historical"]
        parsed = []
        for row in rows:
            close = self._number(row, "adjClose", "close")
            raw_date = row.get("date")
            if close is None or not raw_date:
                continue
            parsed.append({"date": str(raw_date), "close": close})
        parsed.sort(key=lambda row: row["date"], reverse=True)
        return parsed

    def _universe_item(self, row: dict[str, Any]) -> StockUniverseItem:
        return StockUniverseItem(
            ticker=str(row.get("symbol") or row.get("ticker") or "").upper(),
            name=row.get("companyName") or row.get("name"),
            exchange=row.get("exchangeShortName") or row.get("exchange"),
            country=row.get("country"),
            sector=row.get("sector"),
            industry=row.get("industry"),
            market_cap=self._number(row, "marketCap", "market_cap"),
            avg_volume=self._number(row, "avgVolume", "averageVolume", "volume"),
        )

    @staticmethod
    def _rows(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("historical"), list):
                return [row for row in data["historical"] if isinstance(row, dict)]
            return [data]
        return []

    @staticmethod
    def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return rows[0] if rows else {}

    @staticmethod
    def _number(row: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                return number
        return None

    @staticmethod
    def _sum_optional(*values: float | None) -> float | None:
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    def _ratio_pct(
        self,
        row: dict[str, Any],
        ratio_key: str,
        *,
        numerator_key: str,
        denominator_key: str,
    ) -> float | None:
        ratio = self._number(row, ratio_key)
        if ratio is not None:
            return self._percent_value(ratio)
        numerator = self._number(row, numerator_key)
        denominator = self._number(row, denominator_key)
        if numerator is None or not denominator:
            return None
        return (numerator / denominator) * 100

    @staticmethod
    def _percent_value(value: float | None) -> float | None:
        if value is None:
            return None
        return value * 100 if abs(value) <= 1.5 else value

    @staticmethod
    def _growth_pct(values: list[float | None], latest_index: int, prior_index: int) -> float | None:
        if len(values) <= prior_index:
            return None
        latest = values[latest_index]
        prior = values[prior_index]
        if latest is None or prior in (None, 0):
            return None
        return ((latest - prior) / abs(prior)) * 100

    @staticmethod
    def _cagr_pct(values: list[float | None], latest_index: int, prior_index: int) -> float | None:
        if len(values) <= prior_index:
            return None
        latest = values[latest_index]
        prior = values[prior_index]
        if latest is None or prior is None or latest <= 0 or prior <= 0:
            return None
        years = prior_index - latest_index
        if years <= 0:
            return None
        return (((latest / prior) ** (1 / years)) - 1) * 100

    @staticmethod
    def _period_change(current_price: float, history: list[dict[str, Any]], days: int) -> float | None:
        if not history:
            return None
        target = date.today() - timedelta(days=days)
        candidates = [row for row in history if row["date"] <= target.isoformat()]
        basis = candidates[0] if candidates else history[-1]
        basis_price = basis.get("close")
        if not basis_price:
            return None
        return ((current_price - basis_price) / basis_price) * 100

    @staticmethod
    def _distance_pct(current_price: float, reference_price: float | None) -> float | None:
        if not reference_price:
            return None
        return ((current_price - reference_price) / reference_price) * 100

