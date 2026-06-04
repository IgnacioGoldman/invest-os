from __future__ import annotations

import logging
import time
from datetime import date as date_type

from app.entry_engine.data_provider import DataProvider
from app.entry_engine.models import EntrySnapshotFile, EntryStockSnapshot
from app.entry_engine.providers.fmp_provider import FMPProvider
from app.entry_engine.utils.file_storage import save_entry_snapshot


logger = logging.getLogger(__name__)


def build_entry_snapshot(
    limit: int = 2000,
    date: str | None = None,
    *,
    provider: DataProvider | None = None,
    batch_size: int = 25,
    batch_pause_seconds: float = 1.0,
) -> EntrySnapshotFile:
    snapshot_date = date or date_type.today().isoformat()
    data_provider = provider or FMPProvider()

    logger.info("Fetching top %s liquid stocks from %s", limit, data_provider.source)
    universe = data_provider.get_top_liquid_stocks(limit)
    stocks: list[EntryStockSnapshot] = []
    failed_tickers: list[str] = []

    for start in range(0, len(universe), batch_size):
        batch = universe[start : start + batch_size]
        logger.info("Processing entry snapshot batch %s-%s of %s", start + 1, start + len(batch), len(universe))
        for item in batch:
            try:
                stocks.append(
                    EntryStockSnapshot(
                        date=snapshot_date,
                        ticker=item.ticker,
                        name=item.name,
                        exchange=item.exchange,
                        country=item.country,
                        sector=item.sector,
                        industry=item.industry,
                        market_cap=item.market_cap,
                        avg_volume=item.avg_volume,
                        business_health=data_provider.get_business_health(item.ticker),
                        price_opportunity=data_provider.get_price_opportunity(item.ticker),
                        valuation=data_provider.get_valuation(item.ticker),
                    )
                )
            except Exception:
                failed_tickers.append(item.ticker)
                logger.exception("Entry snapshot failed for %s", item.ticker)

        if start + batch_size < len(universe) and batch_pause_seconds > 0:
            time.sleep(batch_pause_seconds)

    snapshot = EntrySnapshotFile(
        date=snapshot_date,
        source=data_provider.source,
        count=len(stocks),
        failed_tickers=failed_tickers,
        stocks=stocks,
    )
    save_entry_snapshot(snapshot)
    logger.info("Stored entry snapshot for %s with %s stocks and %s failures", snapshot_date, len(stocks), len(failed_tickers))
    return snapshot

