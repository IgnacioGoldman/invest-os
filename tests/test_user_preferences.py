from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.user_preferences import UserPreferences, load_user_preferences, save_user_preferences  # noqa: E402


class UserPreferencesTest(unittest.TestCase):
    def test_sidebar_order_is_saved_and_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))
            saved = save_user_preferences(
                UserPreferences(
                    sidebar_order=[
                        "eye",
                        "capital",
                        "eye",
                        "personality",
                    ],
                ),
                settings,
            )
            loaded = load_user_preferences(settings)

        self.assertIsNotNone(saved.updated_at)
        self.assertEqual(
            loaded.sidebar_order,
            ["eye", "capital", "personality", "consultancy", "exploration", "notes"],
        )


if __name__ == "__main__":
    unittest.main()
