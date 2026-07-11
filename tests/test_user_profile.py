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
    investor_profile_context,
    load_investor_profile,
    normalise_personality_id,
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

    def test_profile_context_includes_public_allocation_roles(self) -> None:
        profile = InvestorProfile(
            personality="balanced_conviction",
            customAllocation={
                "vwce": 60,
                "cashBonds": 20,
                "individualStocks": 15,
                "crypto": 5,
            },
        )

        context = investor_profile_context(profile)

        self.assertEqual(context["allocation_role_guide"]["vwce"]["public_label"], "Core global equities")
        self.assertEqual(context["allocation_role_guide"]["cashBonds"]["public_label"], "Defensive assets")
        self.assertEqual(context["allocation_role_guide"]["individualStocks"]["public_label"], "Active equities")
        self.assertIn("allocation_role_guide", " ".join(context["notes"]))

    def test_new_persona_allocation_and_legacy_aliases(self) -> None:
        profile = InvestorProfile(
            personality="aggressive_growth",
            customAllocation={
                "vwce": 55,
                "cashBonds": 15,
                "individualStocks": 20,
                "crypto": 10,
            },
        )

        target = active_allocation(profile)

        self.assertEqual(target.vwce, 45)
        self.assertEqual(target.crypto, 15)
        self.assertEqual(normalise_personality_id("low_risk"), "steady_growth")
        self.assertEqual(normalise_personality_id("high_risk"), "aggressive_growth")
        self.assertEqual(normalise_personality_id("starter"), "steady_growth")
        self.assertEqual(normalise_personality_id("high_risk_explorer"), "aggressive_growth")


if __name__ == "__main__":
    unittest.main()
