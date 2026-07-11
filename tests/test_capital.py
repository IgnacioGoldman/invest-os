from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.capital import (  # noqa: E402
    ManualCapitalEntryRequest,
    add_manual_capital_entry,
    delete_manual_capital_entry,
    load_manual_capital,
    migrate_legacy_manual_capital,
    update_manual_capital_entry,
)


class CapitalManualEntryTest(unittest.TestCase):
    def test_add_bank_cash_entry_to_user_context(self) -> None:
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
        self.assertIn("id", snapshot.cash[0])
        self.assertEqual(loaded.cash[0]["account_name"], "Reserve")
        self.assertEqual(loaded.cash[0]["purpose"], "emergency_fund")

    def test_add_stock_entry_to_user_context(self) -> None:
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

    def test_update_entry(self) -> None:
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
            entry_id = snapshot.cash[0]["id"]

            updated = update_manual_capital_entry(
                data_dir,
                str(entry_id),
                ManualCapitalEntryRequest(
                    kind="bank_cash",
                    platform="Bank",
                    account_name="Reserve",
                    currency="EUR",
                    balance=2500,
                    purpose="emergency_fund",
                ),
            )

        self.assertEqual(updated.cash[0]["id"], entry_id)
        self.assertEqual(updated.cash[0]["balance"], 2500)

    def test_delete_entry(self) -> None:
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
            entry_id = str(snapshot.cash[0]["id"])

            updated = delete_manual_capital_entry(data_dir, entry_id)

        self.assertEqual(updated.cash, [])
        self.assertEqual(updated.assets, [])

    def test_migrate_legacy_manual_files_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            manual_dir = data_dir / "manual"
            manual_dir.mkdir()
            (manual_dir / "cash.yaml").write_text(
                """
- account_name: Main checking
  platform: Bank
  currency: EUR
  balance: 6000
  purpose: monthly_spending
""",
                encoding="utf-8",
            )
            (manual_dir / "assets.yaml").write_text(
                """
- symbol: DT
  name: Dynatrace RSU
  asset_class: rsu
  platform: Etrade
  quantity: 1557
  currency: USD
""",
                encoding="utf-8",
            )

            first = migrate_legacy_manual_capital(data_dir)
            second = migrate_legacy_manual_capital(data_dir)
            snapshot = load_manual_capital(data_dir)

        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        self.assertEqual(len(snapshot.cash), 1)
        self.assertEqual(len(snapshot.assets), 1)


if __name__ == "__main__":
    unittest.main()
