from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.entry_engine.open_data_models import HistoricalPricePoint, OpenDataSnapshot
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.entry_engine.utils.file_storage import load_stock_universe
from app.services.open_data_stock_store import (
    activate_stock,
    deactivate_stock,
    load_active_tickers,
    load_all_db_stock_snapshots,
    load_db_stock_snapshot,
    load_db_or_backfill_price_history,
    load_db_or_backfill_stock_snapshots,
    save_stock_snapshot_to_db,
)
from app.services.refresh_jobs import RefreshJob, list_refresh_jobs, start_refresh_job


class RefreshRequest(BaseModel):
    source: str = "exploration_beta"


class StockUniverseItem(BaseModel):
    symbol: str
    name: str | None = None
    quote_type: str | None = None
    region: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    active: bool = False
    loaded: bool = False


app = FastAPI(title="Exploration Beta", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/open-data/stocks")
def open_data_stocks() -> list[OpenDataSnapshot]:
    return load_db_or_backfill_stock_snapshots(get_settings())


@app.get("/api/stocks/universe")
def stock_universe() -> list[StockUniverseItem]:
    settings = get_settings()
    active = set(load_active_tickers(settings))
    loaded = {snapshot.ticker for snapshot in load_all_db_stock_snapshots(settings)}
    rows = []
    for row in load_stock_universe():
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        rows.append(
            StockUniverseItem(
                symbol=symbol,
                name=row.get("name"),
                quote_type=row.get("quote_type"),
                region=row.get("region"),
                country=row.get("country"),
                sector=row.get("sector"),
                industry=row.get("industry"),
                active=symbol in active,
                loaded=symbol in loaded,
            )
        )
    return rows


@app.post("/api/stocks/active/{ticker}")
def add_stock_to_table(ticker: str) -> OpenDataSnapshot:
    settings = get_settings()
    symbol = ticker.upper().strip()
    universe = {row["symbol"] for row in load_stock_universe()}
    if symbol not in universe:
        raise HTTPException(status_code=404, detail=f"{symbol} was not found in the stock universe.")
    activate_stock(settings, symbol)
    snapshot = load_db_stock_snapshot(settings, symbol)
    if snapshot is not None:
        return snapshot
    return refresh_open_data_stock(symbol)


@app.delete("/api/stocks/active/{ticker}")
def remove_stock_from_table(ticker: str) -> dict[str, str]:
    symbol = ticker.upper().strip()
    deactivate_stock(get_settings(), symbol)
    return {"status": "removed", "ticker": symbol}


@app.get("/api/open-data/stocks/{ticker}")
def open_data_stock(ticker: str) -> OpenDataSnapshot:
    saved = load_db_stock_snapshot(get_settings(), ticker)
    if saved is not None:
        return saved
    return refresh_open_data_stock(ticker)


@app.get("/api/open-data/stocks/{ticker}/price-history")
def open_data_stock_price_history(ticker: str) -> list[HistoricalPricePoint]:
    return load_db_or_backfill_price_history(get_settings(), ticker)


@app.post("/api/open-data/stocks/{ticker}/refresh")
def refresh_open_data_stock(ticker: str) -> OpenDataSnapshot:
    try:
        snapshot = OpenDataProvider(force_refresh=True, include_filing_details=False).get_open_data_snapshot(ticker)
        save_stock_snapshot_to_db(get_settings(), snapshot)
        return snapshot
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open data stock fetch failed: {exc}") from exc


@app.post("/api/refresh")
def refresh(request: RefreshRequest) -> RefreshJob:
    if request.source != "exploration_beta":
        raise HTTPException(status_code=400, detail="Only exploration_beta refresh is supported in this branch.")
    return start_refresh_job(get_settings(), "exploration_beta")


@app.get("/api/refresh/jobs")
def refresh_jobs() -> list[RefreshJob]:
    return list_refresh_jobs()
