from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings, get_settings
from app.services.storage import connect, load_user_preferences_payload, save_user_preferences_payload


PREFERENCES_ID = "default"
SidebarView = Literal["personality", "capital", "consultancy", "exploration", "eye", "notes"]
DEFAULT_SIDEBAR_ORDER: list[SidebarView] = [
    "personality",
    "capital",
    "consultancy",
    "exploration",
    "eye",
    "notes",
]
SIDEBAR_VIEW_SET = set(DEFAULT_SIDEBAR_ORDER)


class UserPreferences(BaseModel):
    sidebar_order: list[SidebarView] = Field(default_factory=lambda: DEFAULT_SIDEBAR_ORDER.copy())
    updated_at: datetime | None = None


def normalise_sidebar_order(order: list[str]) -> list[SidebarView]:
    seen: set[str] = set()
    normalised: list[SidebarView] = []
    for item in order:
        if item in SIDEBAR_VIEW_SET and item not in seen:
            normalised.append(item)  # type: ignore[arg-type]
            seen.add(item)
    for item in DEFAULT_SIDEBAR_ORDER:
        if item not in seen:
            normalised.append(item)
    return normalised


def load_user_preferences(settings: Settings | None = None) -> UserPreferences:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        row = load_user_preferences_payload(conn, PREFERENCES_ID)
    if row is None:
        return UserPreferences()

    payload, updated_at = row
    try:
        preferences = UserPreferences.model_validate_json(payload)
    except ValidationError:
        return UserPreferences()
    return UserPreferences(
        sidebar_order=normalise_sidebar_order(preferences.sidebar_order),
        updated_at=preferences.updated_at or updated_at,
    )


def save_user_preferences(preferences: UserPreferences, settings: Settings | None = None) -> UserPreferences:
    settings = settings or get_settings()
    saved = UserPreferences(
        sidebar_order=normalise_sidebar_order(preferences.sidebar_order),
        updated_at=datetime.now(timezone.utc),
    )
    with connect(settings.data_dir) as conn:
        save_user_preferences_payload(
            conn,
            PREFERENCES_ID,
            saved.updated_at or datetime.now(timezone.utc),
            saved.model_dump_json(),
        )
        conn.commit()
    return saved
