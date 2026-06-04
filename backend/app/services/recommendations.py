"""AI-generated portfolio recommendations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.models import PortfolioSnapshot
from app.services.storage import connect, load_recommendation_payloads, replace_recommendations


PROJECT_DIR = Path(__file__).resolve().parents[3]
PORTFOLIO_RECOMMENDATIONS_SKILL_DIR = PROJECT_DIR / "skills" / "portfolio-recommendations"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class Recommendation(BaseModel):
    severity: Literal["info", "warning", "critical"]
    category: Literal[
        "allocation",
        "drawdown_reserve",
        "trim_or_exit",
        "capital_move",
        "entry",
        "concentration",
        "theme",
    ] = "allocation"
    title: str
    detail: str


class RecommendationList(BaseModel):
    recommendations: list[Recommendation]


RECOMMENDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommendations": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                    "category": {
                        "type": "string",
                        "enum": [
                            "allocation",
                            "drawdown_reserve",
                            "trim_or_exit",
                            "capital_move",
                            "entry",
                            "concentration",
                            "theme",
                        ],
                    },
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["severity", "category", "title", "detail"],
            },
        }
    },
    "required": ["recommendations"],
}


def _skill_text() -> str:
    if PORTFOLIO_RECOMMENDATIONS_SKILL_DIR.exists():
        skill_parts = []
        for path in sorted(PORTFOLIO_RECOMMENDATIONS_SKILL_DIR.glob("*.md")):
            skill_parts.append(f"# Skill file: {path.name}\n\n{path.read_text(encoding='utf-8')}")
        if skill_parts:
            return "\n\n---\n\n".join(skill_parts)
    return (
        "Analyze the portfolio snapshot as a read-only portfolio advisor. "
        "Return concise, actionable recommendations without placing trades."
    )


def _snapshot_payload(snapshot: PortfolioSnapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True)


def _extract_text(response_json: dict[str, Any]) -> str:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text

    parts: list[str] = []
    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def load_saved_recommendations(settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        return [
            Recommendation.model_validate_json(payload)
            for payload in load_recommendation_payloads(conn)
        ]


def save_recommendations(recommendations: list[Recommendation], settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        replace_recommendations(conn, datetime.now(timezone.utc), recommendations)
        conn.commit()
    return recommendations


def generate_recommendations(snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        return []

    instructions = (
        f"{_skill_text()}\n\n"
        "Return only JSON matching the provided schema. Keep recommendations specific to the supplied snapshot. "
        "Do not use fixed portfolio thresholds unless they are explicitly present in the supplied context."
    )
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_recommendation_model,
            "instructions": instructions,
            "input": f"Portfolio snapshot JSON:\n{_snapshot_payload(snapshot)}",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "portfolio_recommendations",
                    "schema": RECOMMENDATION_SCHEMA,
                    "strict": True,
                }
            },
        },
        timeout=45,
    )
    response.raise_for_status()

    try:
        parsed = RecommendationList.model_validate_json(_extract_text(response.json()))
        return parsed.recommendations
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"AI recommendations response did not match expected format: {exc}") from exc


def generate_and_store(snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    settings = settings or get_settings()
    recommendations = generate_recommendations(snapshot, settings)
    if recommendations:
        save_recommendations(recommendations, settings)
    return recommendations


def evaluate(_snapshot: PortfolioSnapshot, settings: Settings | None = None) -> list[Recommendation]:
    return load_saved_recommendations(settings)
