"""Live smoke test for the ship_researcher sub-agent.

Gated on the presence of Google Cloud Application Default Credentials.
Does NOT mock: verifies that a real model call produces a valid ShipAssessment shape.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from backend.schemas import MatchIntake, ShipAssessment, TravelParty, Vibe
from backend.tools.cruise_inventory import _search_seed_data as search_sailings

adc_missing = not Path(
    os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
).exists()

pytestmark = pytest.mark.skipif(
    adc_missing,
    reason="ADC credentials not found — run gcloud auth application-default login",
)


def _intake() -> MatchIntake:
    return MatchIntake(
        travel_party=TravelParty.COUPLE,
        party_size=2,
        primary_vibe=Vibe.RELAXATION,
        budget_per_person_usd=2500,
        flexible_dates=True,
        earliest_departure=date(2026, 9, 1),
        latest_departure=date(2026, 11, 30),
        duration_nights_min=7,
        duration_nights_max=10,
        preferred_regions=["Caribbean"],
        departure_ports_acceptable=["MIA", "FLL"],
        cruise_experience_level="first_timer",
    )


@pytest.mark.asyncio
async def test_research_ship_returns_valid_assessment() -> None:
    from backend.agents.subagents.ship_researcher import research_ship

    intake = _intake()
    sailings = search_sailings(intake)
    assert len(sailings) > 0, "Inventory returned no sailings for this intake — fix the test fixture"

    result = await research_ship(sailings[0], intake)

    assert isinstance(result, ShipAssessment)
    assert 0.0 <= result.vibe_score <= 1.0
    assert len(result.fit_reasoning) > 0
    assert 2 <= len(result.strengths) <= 4
    assert 2 <= len(result.concerns) <= 4
    assert len(result.review_sentiment_summary) > 0
    assert str(result.booking_affiliate_url).startswith("https://partner.example.com/book")
    assert "cruisewise" in str(result.booking_affiliate_url)
    assert result.cabin_price_usd > 0
    assert result.sailing_id == sailings[0]["sailing_id"]
