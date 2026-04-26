"""Smoke tests — all Pydantic schema models must import and construct without error."""

from __future__ import annotations

from datetime import UTC, date, datetime

from backend.schemas import (
    BookingRecord,
    CabinCategory,
    MatchIntake,
    MatchResult,
    PriceSnapshot,
    RepriceRecommendation,
    Sailing,
    ShipAssessment,
    TravelParty,
    Vibe,
)


def _sailing() -> Sailing:
    return Sailing(
        sailing_id="s1",
        cruise_line="Royal Caribbean",
        ship_name="Symphony of the Seas",
        departure_date=date(2025, 11, 1),
    )


def _ship_assessment() -> ShipAssessment:
    return ShipAssessment(
        sailing_id="s1",
        cruise_line="Royal Caribbean",
        ship_name="Symphony of the Seas",
        departure_date=date(2025, 11, 1),
        return_date=date(2025, 11, 8),
        duration_nights=7,
        departure_port="Miami",
        itinerary_summary="Western Caribbean: Labadee, Falmouth, Cozumel",
        cabin_price_usd=999,
        cabin_category_priced=CabinCategory.INTERIOR,
        vibe_score=0.85,
        fit_reasoning="Strong family-fun vibe matches primary intent.",
        strengths=["waterslides", "kids club"],
        concerns=["can feel crowded"],
        review_sentiment_summary="Guests highlight the entertainment variety and dining options.",
        booking_affiliate_url="https://example.com/affiliate/s1",
    )


def _booking_record() -> BookingRecord:
    return BookingRecord(
        sailing_id="s1",
        cruise_line="Royal Caribbean",
        ship_name="Symphony of the Seas",
        departure_date=date(2025, 11, 1),
        booking_id="b1",
        user_id="u1",
        cabin_category=CabinCategory.INTERIOR,
        price_paid_usd=1200,
        booking_source="match",
        final_payment_date=date(2025, 9, 1),
        created_at=datetime.now(tz=UTC),
    )


def test_sailing_is_base_of_ship_assessment() -> None:
    a = _ship_assessment()
    assert isinstance(a, Sailing)
    assert a.ship_name == "Symphony of the Seas"


def test_sailing_is_base_of_booking_record() -> None:
    b = _booking_record()
    assert isinstance(b, Sailing)
    assert b.sailing_id == "s1"


def test_cabin_category_distinction() -> None:
    a = _ship_assessment()
    b = _booking_record()
    # ShipAssessment uses cabin_category_priced; BookingRecord uses cabin_category
    assert hasattr(a, "cabin_category_priced")
    assert hasattr(b, "cabin_category")
    assert not hasattr(a, "cabin_category")
    assert not hasattr(b, "cabin_category_priced")


def test_match_intake_defaults() -> None:
    intake = MatchIntake(
        travel_party=TravelParty.COUPLE,
        party_size=2,
        primary_vibe=Vibe.RELAXATION,
        budget_per_person_usd=2000,
        flexible_dates=True,
        earliest_departure=date(2025, 11, 1),
        latest_departure=date(2025, 12, 31),
        duration_nights_min=5,
        duration_nights_max=14,
        preferred_regions=["Caribbean"],
        departure_ports_acceptable=["MIA"],
        cruise_experience_level="first_timer",
    )
    assert intake.secondary_vibes == []
    assert intake.must_haves == []


def test_match_result_has_trace_id() -> None:
    result = MatchResult(
        intake_id="i1",
        generated_at=datetime.now(tz=UTC),
        ranked_candidates=[_ship_assessment()],
        top_pick_reasoning="Best fit for the stated vibe.",
        counter_memo="May feel too large for a first timer.",
        refinement_iterations=2,
    )
    assert result.agent_trace_id == ""


def test_price_snapshot_int_price() -> None:
    snap = PriceSnapshot(
        booking_id="b1",
        checked_at=datetime.now(tz=UTC),
        current_price_usd=1099,
        current_perks=["beverage_package"],
    )
    assert isinstance(snap.current_price_usd, int)


def test_reprice_recommendation_has_trace_id() -> None:
    rec = RepriceRecommendation(
        booking_id="b1",
        detected_at=datetime.now(tz=UTC),
        original_price_usd=1200,
        new_price_usd=999,
        price_delta_usd=201,
        perk_delta_description="Perks unchanged.",
        estimated_net_benefit_usd=201,
        recommendation="reprice",
        confidence="high",
        reasoning="Clear savings with no perk trade-off.",
        suggested_email_subject="Reprice request — Symphony Nov 1",
        suggested_email_body="Dear agent, please reprice my booking.",
    )
    assert rec.agent_trace_id == ""
    assert rec.price_delta_usd == 201


