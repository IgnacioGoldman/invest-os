from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.entry_engine.build_entry_snapshot import build_entry_snapshot
from app.entry_engine.models import EntrySnapshotFile, EntrySnapshotRequest
from app.entry_engine.open_data_models import OpenDataSnapshot
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.entry_engine.utils.file_storage import (
    load_latest_entry_snapshot,
    load_latest_open_data_stock_snapshot,
    load_latest_open_data_stock_snapshots,
    save_open_data_stock_snapshot,
)
from app.models import RefreshRequest
from app.services.asset_opportunities import (
    AssetOpportunity,
    AssetOpportunityFile,
    load_asset_opportunities_by_class,
    load_latest_asset_opportunities,
)
from app.services.recommendations import (
    RecommendationFollowUpCodexResultRequest,
    RecommendationFollowUpRequest,
    RecommendationFollowUpResponse,
    RecommendationSnapshot,
    answer_recommendation_followup,
    generate_and_store,
    load_recommendation_followup_result,
    load_recommendation_followups,
    load_saved_recommendation_snapshot,
    submit_recommendation_followup_codex_result,
)
from app.services.refresh_jobs import RefreshJob, list_refresh_jobs, start_refresh_job
from app.services.stock_candidate_analysis import StockCandidateAnalysis, load_latest_stock_candidate_analysis
from app.services.stock_entry_analysis import StockEntryAnalysis, analyze_latest_open_data_stock_entries, analyze_latest_open_data_stock_entry
from app.snapshot import get_portfolio_snapshot


app = FastAPI(title="Invest OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/snapshot")
def snapshot():
    return get_portfolio_snapshot()


@app.get("/api/holdings")
def holdings():
    return get_portfolio_snapshot().holdings


@app.get("/api/cash")
def cash():
    return get_portfolio_snapshot().cash_balances


@app.get("/api/orders/open")
def open_orders():
    return get_portfolio_snapshot().open_orders


@app.get("/api/orders/history")
def order_history():
    return get_portfolio_snapshot().order_history


@app.get("/api/recommendations")
def recommendations() -> RecommendationSnapshot:
    return load_saved_recommendation_snapshot()


@app.post("/api/recommendations")
def generate_recommendations() -> RecommendationSnapshot:
    settings = get_settings()
    try:
        generate_and_store(get_portfolio_snapshot(), settings)
        return load_saved_recommendation_snapshot(settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI recommendations failed: {exc}") from exc


@app.post("/api/recommendations/follow-up")
def recommendation_follow_up(request: RecommendationFollowUpRequest) -> RecommendationFollowUpResponse:
    settings = get_settings()
    try:
        return answer_recommendation_followup(get_portfolio_snapshot(), request, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Recommendation follow-up failed: {exc}") from exc


@app.get("/api/recommendations/follow-ups")
def recommendation_follow_ups() -> list[RecommendationFollowUpResponse]:
    return load_recommendation_followups(get_settings())


@app.get("/api/recommendations/follow-up/{request_id}")
def recommendation_follow_up_result(request_id: str) -> RecommendationFollowUpResponse:
    response = load_recommendation_followup_result(request_id, get_settings())
    if response is None:
        raise HTTPException(status_code=404, detail="Recommendation follow-up request was not found.")
    return response


@app.post("/api/recommendations/follow-up/codex-result")
def recommendation_follow_up_codex_result(
    request: RecommendationFollowUpCodexResultRequest,
) -> RecommendationFollowUpResponse:
    try:
        response = submit_recommendation_followup_codex_result(request, get_settings())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Recommendation follow-up request was not found.")
    return response


@app.get("/api/entry/snapshot")
def latest_entry_snapshot() -> EntrySnapshotFile:
    snapshot = load_latest_entry_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No entry snapshot has been generated yet.")
    return snapshot


@app.post("/api/entry/snapshot")
def generate_entry_snapshot(request: EntrySnapshotRequest) -> EntrySnapshotFile:
    settings = get_settings()
    if not settings.fmp_api_key:
        raise HTTPException(status_code=400, detail="FMP_API_KEY is not configured.")
    try:
        return build_entry_snapshot(limit=request.limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Entry snapshot generation failed: {exc}") from exc


@app.get("/api/open-data/stocks")
def open_data_stocks() -> list[OpenDataSnapshot]:
    return load_latest_open_data_stock_snapshots()


@app.get("/api/open-data/stocks/analysis")
def open_data_stock_analyses() -> dict[str, StockEntryAnalysis]:
    analyses = analyze_latest_open_data_stock_entries()
    if not analyses:
        raise HTTPException(status_code=404, detail="No collected open-data stock facts.")
    return analyses


@app.get("/api/open-data/stocks/candidate-analysis")
def open_data_stock_candidate_analysis() -> StockCandidateAnalysis:
    analysis = load_latest_stock_candidate_analysis()
    if analysis is None:
        raise HTTPException(status_code=404, detail="No AI stock candidate analysis has been saved yet.")
    return analysis


@app.get("/api/open-data/assets")
def open_data_assets() -> AssetOpportunityFile:
    payload = load_latest_asset_opportunities()
    if payload is None:
        raise HTTPException(status_code=404, detail="No multi-asset derived signals have been generated yet.")
    return payload


@app.get("/api/open-data/assets/etfs")
def open_data_etfs() -> list[AssetOpportunity]:
    return load_asset_opportunities_by_class("etf")


@app.get("/api/open-data/assets/commodities")
def open_data_commodities() -> list[AssetOpportunity]:
    return load_asset_opportunities_by_class("commodity_proxy")


@app.get("/api/open-data/assets/crypto")
def open_data_crypto() -> list[AssetOpportunity]:
    return load_asset_opportunities_by_class("crypto")


@app.get("/api/open-data/stocks/{ticker}")
def open_data_stock(ticker: str) -> OpenDataSnapshot:
    saved = load_latest_open_data_stock_snapshot(ticker)
    if saved is not None:
        return saved
    return refresh_open_data_stock(ticker)


@app.get("/api/open-data/stocks/{ticker}/analysis")
def open_data_stock_analysis(ticker: str) -> StockEntryAnalysis:
    analysis = analyze_latest_open_data_stock_entry(ticker)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No collected open-data facts for {ticker.upper()}.")
    return analysis


@app.post("/api/open-data/stocks/{ticker}/refresh")
def refresh_open_data_stock(ticker: str) -> OpenDataSnapshot:
    try:
        snapshot = OpenDataProvider().get_open_data_snapshot(ticker)
        save_open_data_stock_snapshot(snapshot)
        return snapshot
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Open data stock fetch failed: {exc}") from exc


@app.post("/api/refresh")
def refresh(request: RefreshRequest) -> RefreshJob:
    # Refresh is read-only: it fetches source data and replaces only that source's local SQLite cache.
    return start_refresh_job(get_settings(), request.source)


@app.get("/api/refresh/jobs")
def refresh_jobs() -> list[RefreshJob]:
    return list_refresh_jobs()
