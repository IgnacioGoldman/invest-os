"""Saved AI stock candidate analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.config import DATA_DIR


STOCK_CANDIDATE_ANALYSIS_DIR = DATA_DIR / "stocks" / "ai_candidate_analysis"

CandidateDecision = Literal[
    "starter_entry_candidate",
    "watchlist",
    "wait",
    "tactical_candidate",
    "no_clean_candidate",
]
CandidateHorizon = Literal[
    "long_term_accumulation",
    "tactical_entry",
    "long_term",
    "short_term",
    "both",
]


class StockCandidate(BaseModel):
    ticker: str
    name: str | None = None
    horizon: CandidateHorizon | None = None
    conviction: float = Field(ge=0, le=10)
    decision: CandidateDecision
    entry_quality: str = ""
    why_now: str = ""
    thesis: str = ""
    business_evidence: list[str] = Field(default_factory=list)
    valuation_evidence: list[str] = Field(default_factory=list)
    price_evidence: list[str] = Field(default_factory=list)
    support_1d_evidence: list[str] = Field(default_factory=list)
    derived_signal_evidence: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    main_risks: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class StockRunnerUp(BaseModel):
    ticker: str
    name: str | None = None
    horizon: CandidateHorizon
    reason: str


class StockRejectedCandidate(BaseModel):
    ticker: str
    name: str | None = None
    reason: str


class StockCandidateAnalysis(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    as_of: str
    source: str = "codex_stock_entry_analyst"
    skill: str = "skills/stock-analysis/stock-entry-analyst.md"
    deterministic_inputs: list[str] = Field(default_factory=list)
    live_context_used: bool = False
    best_long_term_candidate: StockCandidate | None = None
    best_short_term_candidate: StockCandidate | None = None
    runner_ups: list[StockRunnerUp] = Field(default_factory=list)
    rejected_interesting_names: list[StockRejectedCandidate] = Field(default_factory=list)
    data_quality_notes: list[str] = Field(default_factory=list)


def latest_stock_candidate_analysis_path(data_dir: Path = STOCK_CANDIDATE_ANALYSIS_DIR) -> Path:
    return data_dir / "latest.json"


def save_stock_candidate_analysis(
    analysis: StockCandidateAnalysis,
    data_dir: Path = STOCK_CANDIDATE_ANALYSIS_DIR,
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(analysis.model_dump(mode="json"), indent=2, sort_keys=False)
    dated_path = data_dir / f"{analysis.as_of}.json"
    latest_path = latest_stock_candidate_analysis_path(data_dir)
    dated_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return latest_path


def load_latest_stock_candidate_analysis(
    data_dir: Path = STOCK_CANDIDATE_ANALYSIS_DIR,
) -> StockCandidateAnalysis | None:
    path = latest_stock_candidate_analysis_path(data_dir)
    if not path.exists():
        return None
    return StockCandidateAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
