from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.user_profile import (  # noqa: E402
    InvestorProfile,
    active_allocation,
    load_investor_profile,
    save_investor_profile,
)


class UserProfileTest(unittest.TestCase):
    def test_save_and_load_custom_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))
            saved = save_investor_profile(
                InvestorProfile(
                    personality="custom",
                    customAllocation={
                        "vwce": 55,
                        "cashBonds": 15,
                        "individualStocks": 20,
                        "crypto": 10,
                    },
                ),
                settings,
            )

            loaded = load_investor_profile(settings)

        self.assertIsNotNone(saved.updated_at)
        self.assertEqual(loaded.personality, "custom")
        self.assertEqual(active_allocation(loaded).crypto, 10)
        self.assertEqual(active_allocation(loaded).individual_stocks, 20)

    def test_invalid_custom_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))
            with self.assertRaises(ValueError):
                save_investor_profile(
                    InvestorProfile(
                        personality="custom",
                        customAllocation={
                            "vwce": 55,
                            "cashBonds": 15,
                            "individualStocks": 20,
                            "crypto": 9,
                        },
                    ),
                    settings,
                )


if __name__ == "__main__":
    unittest.main()
