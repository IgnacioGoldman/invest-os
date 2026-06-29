from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.models import MarketPrice, Order  # noqa: E402
from app.services.portfolio import _enrich_generic_order_history, _is_transient_ibkr_history_warning  # noqa: E402
from app.sources.ibkr import _parse_flex_trades, _flex_retryable_error, _flex_statement_url  # noqa: E402


class IbkrFlexImportTest(unittest.TestCase):
    def test_parse_flex_trade_rows_into_order_history(self) -> None:
        rows = _parse_flex_trades(
            """
            <FlexQueryResponse>
              <Trades>
                <Trade
                  accountId="U123"
                  assetCategory="STK"
                  symbol="VWCE"
                  buySell="BUY"
                  quantity="12.3456"
                  tradePrice="103.21"
                  tradeMoney="1274.28"
                  currency="EUR"
                  dateTime="2026-06-20;14:15:16"
                  tradeID="987654"
                  transactionType="ExchTrade"
                  ibCommission="-1.25"
                  ibCommissionCurrency="EUR"
                />
              </Trades>
            </FlexQueryResponse>
            """
        )

        self.assertEqual(len(rows), 1)
        order = rows[0]
        self.assertEqual(order.source, "ibkr")
        self.assertEqual(order.platform, "Interactive Brokers")
        self.assertEqual(order.symbol, "VWCE")
        self.assertEqual(order.side, "BUY")
        self.assertEqual(order.order_type, "ExchTrade")
        self.assertAlmostEqual(order.quantity, 12.3456)
        self.assertAlmostEqual(order.limit_price or 0, 103.21)
        self.assertAlmostEqual(order.purchase_amount or 0, 1274.28)
        self.assertEqual(order.quote_currency, "EUR")
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.raw["source"], "flex_web_service")
        self.assertEqual(order.raw["commission"], 1.25)
        self.assertEqual(order.raw["commissionAsset"], "EUR")

    def test_normalizes_statement_url_returned_by_flex_request(self) -> None:
        self.assertEqual(
            _flex_statement_url("gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"),
            "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
        )
        self.assertEqual(
            _flex_statement_url("/Universal/servlet/FlexStatementService.GetStatement"),
            "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
        )

    def test_detects_retryable_flex_statement_generation_errors(self) -> None:
        self.assertTrue(_flex_retryable_error("1019: Statement generation in progress. Please try again shortly."))
        self.assertTrue(_flex_retryable_error("1001: Statement could not be generated at this time."))
        self.assertFalse(_flex_retryable_error("1012: Invalid token"))
        self.assertTrue(
            _is_transient_ibkr_history_warning(
                ["IBKR Flex request failed: 1001: Statement could not be generated at this time. Please try again shortly."]
            )
        )
        self.assertFalse(_is_transient_ibkr_history_warning(["IBKR Flex request failed: 1012: Invalid token"]))

    def test_enriches_flex_symbol_without_quote_suffix(self) -> None:
        orders = [
            Order(
                id="buy-1",
                source="ibkr",
                platform="Interactive Brokers",
                symbol="VWCE",
                side="BUY",
                quantity=10,
                limit_price=100,
                quote_currency="EUR",
                raw={"quoteQty": 1000},
                created_at="2026-01-01T10:00:00Z",
            ),
            Order(
                id="buy-2",
                source="ibkr",
                platform="Interactive Brokers",
                symbol="VWCE",
                side="BUY",
                quantity=5,
                limit_price=120,
                quote_currency="EUR",
                raw={"quoteQty": 600},
                created_at="2026-02-01T10:00:00Z",
            ),
            Order(
                id="sell-1",
                source="ibkr",
                platform="Interactive Brokers",
                symbol="VWCE",
                side="SELL",
                quantity=8,
                limit_price=130,
                quote_currency="EUR",
                raw={"quoteQty": 1040},
                created_at="2026-03-01T10:00:00Z",
            ),
        ]
        market_prices = {
            ("VWCE", "EUR"): MarketPrice(symbol="VWCE", currency="EUR", price=150, source="test"),
        }

        enriched = {order.id: order for order in _enrich_generic_order_history(orders, market_prices, Settings(), {})}

        self.assertEqual(enriched["buy-1"].quote_currency, "EUR")
        self.assertAlmostEqual(enriched["buy-1"].remaining_quantity or 0, 2)
        self.assertAlmostEqual(enriched["buy-1"].unrealized_pnl or 0, 100)
        self.assertAlmostEqual(enriched["buy-1"].unrealized_roi_percent or 0, 50)
        self.assertAlmostEqual(enriched["buy-1"].realized_pnl or 0, 240)
        self.assertAlmostEqual(enriched["buy-1"].realized_roi_percent or 0, 30)
        self.assertAlmostEqual(enriched["buy-2"].remaining_quantity or 0, 5)
        self.assertAlmostEqual(enriched["buy-2"].unrealized_pnl or 0, 150)
        self.assertAlmostEqual(enriched["sell-1"].cost_basis_amount or 0, 800)
        self.assertAlmostEqual(enriched["sell-1"].realized_pnl or 0, 240)
        self.assertAlmostEqual(enriched["sell-1"].realized_roi_percent or 0, 30)


if __name__ == "__main__":
    unittest.main()
