from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.capital import ManualCapitalEntryRequest, add_manual_capital_entry, load_manual_capital  # noqa: E402


class CapitalManualEntryTest(unittest.TestCase):
    def test_add_bank_cash_entry_to_manual_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            snapshot = add_manual_capital_entry(
                data_dir,
                ManualCapitalEntryRequest(
                    kind="bank_cash",
                    platform="Bank",
                    account_name="Reserve",
                    currency="EUR",
                    balance=1234,
                    purpose="emergency_fund",
                ),
            )

            loaded = load_manual_capital(data_dir)

        self.assertEqual(len(snapshot.cash), 1)
        self.assertEqual(loaded.cash[0]["account_name"], "Reserve")
        self.assertEqual(loaded.cash[0]["purpose"], "emergency_fund")

    def test_add_stock_entry_to_manual_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            snapshot = add_manual_capital_entry(
                data_dir,
                ManualCapitalEntryRequest(
                    kind="stock",
                    platform="Broker",
                    currency="USD",
                    symbol="AAPL",
                    quantity=3,
                    estimated_price=200,
                    asset_class="stock",
                ),
            )

        self.assertEqual(len(snapshot.assets), 1)
        self.assertEqual(snapshot.assets[0]["symbol"], "AAPL")
        self.assertEqual(snapshot.assets[0]["estimated_price"], 200)


if __name__ == "__main__":
    unittest.main()
