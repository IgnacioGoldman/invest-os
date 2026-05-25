from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import RefreshRequest
from app.services.recommendations import Recommendation, evaluate, generate_and_store
from app.snapshot import get_portfolio_snapshot, refresh_portfolio_snapshot


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
def recommendations() -> list[Recommendation]:
    return evaluate(get_portfolio_snapshot())


@app.post("/api/recommendations")
def generate_recommendations() -> list[Recommendation]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")
    try:
        return generate_and_store(get_portfolio_snapshot(), settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI recommendations failed: {exc}") from exc


@app.post("/api/refresh")
def refresh(request: RefreshRequest):
    # Refresh is read-only: it fetches source data and replaces only that source's local SQLite cache.
    return refresh_portfolio_snapshot(request.source)
