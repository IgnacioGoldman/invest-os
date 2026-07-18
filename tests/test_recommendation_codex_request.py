from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.recommendations import (  # noqa: E402
    Recommendation,
    RecommendationCodexRequest,
    RecommendationFollowUpRequest,
    RecommendationFollowUpCodexResultRequest,
    _codex_followup_command,
    create_recommendation_codex_request,
    recommendation_key,
    submit_recommendation_followup_codex_result,
)
from app.services.user_profile import DEFAULT_INVESTOR_PROFILE  # noqa: E402


class RecommendationCodexRequestTest(unittest.TestCase):
    def test_recommendation_key_prefers_internal_id(self) -> None:
        first = Recommendation(
            id="allocation-run-1",
            severity="warning",
            category="allocation",
            title="Codex allocation review",
            detail="Created from Analyze.",
        )
        second = Recommendation(
            id="allocation-run-2",
            severity="warning",
            category="allocation",
            title="Codex allocation review",
            detail="Created from Analyze.",
        )

        self.assertEqual(recommendation_key(first), "id:allocation-run-1")
        self.assertEqual(recommendation_key(second), "id:allocation-run-2")
        self.assertNotEqual(recommendation_key(first), recommendation_key(second))

    def test_codex_request_prompt_contains_registered_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(data_dir=Path(tmp))
            recommendation = Recommendation(
                severity="warning",
                category="allocation",
                title="Codex allocation review",
                detail="Created from Analyze.",
            )
            pending = create_recommendation_codex_request(
                RecommendationCodexRequest(
                    recommendation=recommendation,
                    question="Start allocation recommendation workflow.",
                    prompt="Analyze Portfolio using just skills/portfolio-recommendations/.",
                ),
                settings,
            )
            completed = submit_recommendation_followup_codex_result(
                RecommendationFollowUpCodexResultRequest(
                    request_id=pending.follow_up_id or "",
                    answer="Final allocation answer.",
                ),
                settings,
            )

        self.assertEqual(pending.status, "pending_codex")
        self.assertEqual(pending.recommendation_key, recommendation_key(recommendation))
        self.assertIsNotNone(pending.follow_up_id)
        self.assertIn("Analyze Portfolio using just skills/portfolio-recommendations/.", pending.codex_command or "")
        self.assertIn("Frontend recommendation writing guide", pending.codex_command or "")
        self.assertIn("the chat should show hidden and the user can expand", pending.codex_command or "")
        self.assertIn("POST http://127.0.0.1:8000/api/recommendations/follow-up/codex-result", pending.codex_command or "")
        self.assertIn(f"request_id: {pending.follow_up_id}", pending.codex_command or "")
        self.assertIsNotNone(completed)
        self.assertEqual(completed.recommendation_key, pending.recommendation_key)
        self.assertEqual(completed.follow_up_id, pending.follow_up_id)
        self.assertEqual(completed.answer, "Final allocation answer.")

    def test_follow_up_codex_prompt_contains_frontend_writing_guide(self) -> None:
        recommendation = Recommendation(
            severity="warning",
            category="allocation",
            title="Codex allocation review",
            detail="Created from Analyze.",
        )
        command = _codex_followup_command(
            "request-123",
            RecommendationFollowUpRequest(
                recommendation=recommendation,
                question="What should the card summary emphasize?",
            ),
            [],
            DEFAULT_INVESTOR_PROFILE,
        )

        self.assertIn("Frontend recommendation writing guide", command)
        self.assertIn("the chat should show hidden and the user can expand", command)
        self.assertIn("request-123", command)


if __name__ == "__main__":
    unittest.main()
