from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.services.storage import connect, load_user_profile_payload, save_user_profile_payload


PROFILE_ID = "default"
InvestorPersonalityId = Literal[
    "capital_preservation",
    "steady_growth",
    "balanced_conviction",
    "aggressive_growth",
    "high_risk_explorer",
    "starter",
    "custom",
    "low_risk",
    "high_risk",
]


class InvestorAllocation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vwce: int = Field(ge=0, le=100)
    cash_bonds: int = Field(ge=0, le=100, alias="cashBonds")
    individual_stocks: int = Field(ge=0, le=100, alias="individualStocks")
    crypto: int = Field(ge=0, le=100)


class InvestorProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    personality: InvestorPersonalityId = "steady_growth"
    custom_allocation: InvestorAllocation = Field(alias="customAllocation")
    updated_at: datetime | None = None


CAPITAL_PRESERVATION_ALLOCATION = InvestorAllocation(vwce=40, cashBonds=55, individualStocks=5, crypto=0)
STEADY_GROWTH_ALLOCATION = InvestorAllocation(vwce=70, cashBonds=20, individualStocks=10, crypto=0)
BALANCED_CONVICTION_ALLOCATION = InvestorAllocation(vwce=55, cashBonds=15, individualStocks=25, crypto=5)
AGGRESSIVE_GROWTH_ALLOCATION = InvestorAllocation(vwce=45, cashBonds=5, individualStocks=35, crypto=15)
LOW_RISK_ALLOCATION = STEADY_GROWTH_ALLOCATION
HIGH_RISK_ALLOCATION = AGGRESSIVE_GROWTH_ALLOCATION
DEFAULT_CUSTOM_ALLOCATION = BALANCED_CONVICTION_ALLOCATION
DEFAULT_INVESTOR_PROFILE = InvestorProfile(
    personality="steady_growth",
    customAllocation=DEFAULT_CUSTOM_ALLOCATION,
)

PERSONALITY_ALLOCATIONS: dict[str, InvestorAllocation] = {
    "capital_preservation": CAPITAL_PRESERVATION_ALLOCATION,
    "steady_growth": STEADY_GROWTH_ALLOCATION,
    "balanced_conviction": BALANCED_CONVICTION_ALLOCATION,
    "aggressive_growth": AGGRESSIVE_GROWTH_ALLOCATION,
    "low_risk": LOW_RISK_ALLOCATION,
    "high_risk": HIGH_RISK_ALLOCATION,
}

ALLOCATION_ROLE_GUIDE = {
    "vwce": {
        "public_label": "Core global equities",
        "role": "Broad market growth engine.",
        "plain_examples": ["VWCE", "low-cost global index ETF"],
        "recommendation_guidance": "Treat as diversified equity exposure, not as a single-stock conviction sleeve.",
    },
    "cashBonds": {
        "public_label": "Defensive assets",
        "role": "Cash, bonds, gold, and similar diversifiers used for flexibility, drawdown resilience, and near-term needs.",
        "plain_examples": ["bank cash", "money market fund", "short bond ETF", "government bond ETF", "gold ETF"],
        "recommendation_guidance": "Separate required cash reserves from investable capital before recommending risk increases.",
    },
    "individualStocks": {
        "public_label": "Active equities",
        "role": "User-selected companies with concentration and stock-specific risk.",
        "plain_examples": ["Apple", "Microsoft", "ASML", "MercadoLibre", "Nvidia"],
        "recommendation_guidance": "Recommend only when valuation, business quality, concentration, and position sizing are coherent.",
    },
    "crypto": {
        "public_label": "Crypto / speculative",
        "role": "High-volatility speculative sleeve with unusually wide outcomes.",
        "plain_examples": ["Bitcoin", "Ethereum"],
        "recommendation_guidance": "Cap sizing strictly and avoid treating crypto drawdowns like normal equity volatility.",
    },
}


def normalise_personality_id(personality: InvestorPersonalityId) -> InvestorPersonalityId:
    if personality == "low_risk":
        return "steady_growth"
    if personality == "high_risk":
        return "aggressive_growth"
    if personality == "high_risk_explorer":
        return "aggressive_growth"
    if personality == "starter":
        return "steady_growth"
    return personality


def allocation_total(allocation: InvestorAllocation) -> int:
    return allocation.vwce + allocation.cash_bonds + allocation.individual_stocks + allocation.crypto


def active_allocation(profile: InvestorProfile) -> InvestorAllocation:
    personality = normalise_personality_id(profile.personality)
    if personality != "custom":
        return PERSONALITY_ALLOCATIONS.get(personality, STEADY_GROWTH_ALLOCATION)
    return profile.custom_allocation


def _normalise_for_save(profile: InvestorProfile) -> InvestorProfile:
    personality = normalise_personality_id(profile.personality)
    if personality == "custom":
        if allocation_total(profile.custom_allocation) != 100:
            raise ValueError("Custom allocation must total 100%.")
        return InvestorProfile(
            personality=personality,
            customAllocation=profile.custom_allocation,
            updated_at=profile.updated_at,
        )

    custom_allocation = profile.custom_allocation
    if allocation_total(custom_allocation) != 100:
        custom_allocation = DEFAULT_CUSTOM_ALLOCATION
    return InvestorProfile(
        personality=personality,
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
        personality=normalise_personality_id(profile.personality),
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
    personality = normalise_personality_id(profile.personality)
    saved_profile = InvestorProfile(
        personality=personality,
        customAllocation=profile.custom_allocation,
        updated_at=profile.updated_at,
    )
    return {
        "personality": personality,
        "saved_profile": saved_profile.model_dump(mode="json", by_alias=True),
        "active_target_allocation": target.model_dump(mode="json", by_alias=True),
        "allocation_role_guide": ALLOCATION_ROLE_GUIDE,
        "target_total_percent": allocation_total(target),
        "notes": [
            "Use the active target allocation as the user's preferred risk profile.",
            "Explain allocation recommendations using the public labels in allocation_role_guide.",
            "Do not recommend reducing risk solely because an exposure is high if it is still within the saved target.",
            "Do flag concentration, stale data, duplicated risk sleeves, or reserved cash conflicts even when the broad target allows risk.",
        ],
    }
