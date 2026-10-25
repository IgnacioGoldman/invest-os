import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = DATA_DIR
    fmp_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"


def get_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")
    return Settings(
        fmp_api_key=os.getenv("FMP_API_KEY") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip() or None,
        gemini_model=(os.getenv("GEMINI_MODEL", "").strip() or "gemini-3-flash-preview").removeprefix("models/"),
    )
