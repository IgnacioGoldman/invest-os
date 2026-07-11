from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.models import CashBalance, Holding, SourceResult  # noqa: E402
from app.services.connections import UserConnectionUpdate, disconnect_user_connection, load_user_connections, save_user_connection  # noqa: E402
from app.services.storage import connect, load_cash_balances, load_holdings, replace_source_result  # noqa: E402


class UserConnectionsTest(unittest.TestCase):
    def test_disconnect_connection_disables_and_clears_cached_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))
            save_user_connection(
                settings,
                "ibkr",
                UserConnectionUpdate(
                    ibkr_host="127.0.0.1",
                    ibkr_port=4001,
                    ibkr_client_id=1,
                    ibkr_flex_query_id="1554875",
                    ibkr_flex_token="secret",
                ),
            )
            with connect(settings.data_dir) as conn:
                replace_source_result(
                    conn,
                    "ibkr",
                    SourceResult(
                        holdings=[
                            Holding(
                                id="ibkr-holding",
                                source="ibkr",
                                platform="Interactive Brokers",
                                symbol="VWCE",
                                asset_class="equity",
                                quantity=1,
                                currency="EUR",
                                current_price=100,
                                market_value=100,
                                confidence="api",
                            )
                        ],
                        cash_balances=[
                            CashBalance(
                                id="ibkr-cash",
                                source="ibkr",
                                platform="Interactive Brokers",
                                currency="EUR",
                                balance=50,
                            )
                        ],
                    ),
                )
                conn.commit()

            deleted = disconnect_user_connection(settings, "ibkr")
            connections = load_user_connections(settings)
            with connect(settings.data_dir) as conn:
                holdings = load_holdings(conn)
                cash = load_cash_balances(conn)

        self.assertFalse(deleted.configured)
        self.assertFalse(next(item for item in connections if item.source == "ibkr").configured)
        self.assertEqual(holdings, [])
        self.assertEqual(cash, [])


if __name__ == "__main__":
    unittest.main()
