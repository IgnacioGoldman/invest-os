from __future__ import annotations

from abc import ABC, abstractmethod

from app.entry_engine.models import BusinessHealth, PriceOpportunity, StockUniverseItem, Valuation
from app.entry_engine.open_data_models import OpenDataSnapshot


class DataProvider(ABC):
    source = "unknown"

    @abstractmethod
    def get_top_liquid_stocks(self, limit: int) -> list[StockUniverseItem]:
        raise NotImplementedError

    @abstractmethod
    def get_business_health(self, ticker: str) -> BusinessHealth:
        raise NotImplementedError

    @abstractmethod
    def get_price_opportunity(self, ticker: str) -> PriceOpportunity:
        raise NotImplementedError

    @abstractmethod
    def get_valuation(self, ticker: str) -> Valuation:
        raise NotImplementedError


class OpenDataMetricProvider(ABC):
    source = "unknown"

    @abstractmethod
    def get_open_data_snapshot(self, ticker: str) -> OpenDataSnapshot:
        raise NotImplementedError
