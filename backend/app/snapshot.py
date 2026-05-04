from app.config import get_settings
from app.models import PortfolioSnapshot, RefreshSource
from app.services.portfolio import build_snapshot, refresh_snapshot


def get_portfolio_snapshot() -> PortfolioSnapshot:
    return build_snapshot(get_settings())


def refresh_portfolio_snapshot(source: RefreshSource) -> PortfolioSnapshot:
    return refresh_snapshot(get_settings(), source)
