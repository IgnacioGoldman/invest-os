from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import RefreshRequest
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


@app.post("/api/refresh")
def refresh(request: RefreshRequest):
    # Refresh is read-only: it fetches source data and replaces only that source's local SQLite cache.
    return refresh_portfolio_snapshot(request.source)
