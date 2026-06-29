from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.services.storage import connect, load_user_profile_payload, save_user_profile_payload


PROFILE_ID = "default"
InvestorPersonalityId = Literal["low_risk", "high_risk", "custom"]


class InvestorAllocation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vwce: int = Field(ge=0, le=100)
    cash_bonds: int = Field(ge=0, le=100, alias="cashBonds")
    individual_stocks: int = Field(ge=0, le=100, alias="individualStocks")
    crypto: int = Field(ge=0, le=100)


class InvestorProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    personality: InvestorPersonalityId = "low_risk"
    custom_allocation: InvestorAllocation = Field(alias="customAllocation")
    updated_at: datetime | None = None


LOW_RISK_ALLOCATION = InvestorAllocation(vwce=70, cashBonds=20, individualStocks=10, crypto=0)
HIGH_RISK_ALLOCATION = InvestorAllocation(vwce=50, cashBonds=10, individualStocks=25, crypto=15)
DEFAULT_CUSTOM_ALLOCATION = InvestorAllocation(vwce=60, cashBonds=20, individualStocks=15, crypto=5)
DEFAULT_INVESTOR_PROFILE = InvestorProfile(
    personality="low_risk",
    customAllocation=DEFAULT_CUSTOM_ALLOCATION,
)


def allocation_total(allocation: InvestorAllocation) -> int:
    return allocation.vwce + allocation.cash_bonds + allocation.individual_stocks + allocation.crypto


def active_allocation(profile: InvestorProfile) -> InvestorAllocation:
    if profile.personality == "low_risk":
        return LOW_RISK_ALLOCATION
    if profile.personality == "high_risk":
        return HIGH_RISK_ALLOCATION
    return profile.custom_allocation


def _normalise_for_save(profile: InvestorProfile) -> InvestorProfile:
    if profile.personality == "custom":
        if allocation_total(profile.custom_allocation) != 100:
            raise ValueError("Custom allocation must total 100%.")
        return profile

    custom_allocation = profile.custom_allocation
    if allocation_total(custom_allocation) != 100:
        custom_allocation = DEFAULT_CUSTOM_ALLOCATION
    return InvestorProfile(
        personality=profile.personality,
        customAllocation=custom_allocation,
        updated_at=profile.updated_at,
    )


def load_investor_profile(settings: Settings | None = None) -> InvestorProfile:
    settings = settings or get_settings()
    with connect(settings.data_dir) as conn:
        row = load_user_profile_payload(conn, PROFILE_ID)
    if row is None:
        return DEFAULT_INVESTOR_PROFILE

    payload, updated_at = row
    try:
        profile = InvestorProfile.model_validate_json(payload)
    except ValidationError:
        return DEFAULT_INVESTOR_PROFILE
    return InvestorProfile(
        personality=profile.personality,
        customAllocation=profile.custom_allocation,
        updated_at=profile.updated_at or updated_at,
    )


def save_investor_profile(profile: InvestorProfile, settings: Settings | None = None) -> InvestorProfile:
    settings = settings or get_settings()
    saved = _normalise_for_save(profile)
    saved = InvestorProfile(
        personality=saved.personality,
        customAllocation=saved.custom_allocation,
        updated_at=datetime.now(timezone.utc),
    )
    with connect(settings.data_dir) as conn:
        save_user_profile_payload(
            conn,
            PROFILE_ID,
            saved.updated_at or datetime.now(timezone.utc),
            saved.model_dump_json(by_alias=True),
        )
        conn.commit()
    return saved


def investor_profile_context(profile: InvestorProfile) -> dict[str, Any]:
    target = active_allocation(profile)
    return {
        "personality": profile.personality,
        "saved_profile": profile.model_dump(mode="json", by_alias=True),
        "active_target_allocation": target.model_dump(mode="json", by_alias=True),
        "target_total_percent": allocation_total(target),
        "notes": [
            "Use the active target allocation as the user's preferred risk profile.",
            "Do not recommend reducing risk solely because an exposure is high if it is still within the saved target.",
            "Do flag concentration, stale data, duplicated risk sleeves, or reserved cash conflicts even when the broad target allows risk.",
        ],
    }
