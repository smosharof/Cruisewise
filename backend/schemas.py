"""
Schemas for the cruise platform.

These define the structured-output contracts at the key handoff points:
  - MatchIntake: user's stated preferences from the intake form
  - MatchResult: the ranked recommendations the Match agent emits
  - BookingRecord: the shared record created when a user confirms a booking
  - WatchStatus: the current state of a monitored booking
  - RepriceRecommendation: what the Watch agent emits when it detects a win

Design principles:
  - Every field the LLM fills is typed and constrained (Enums / Literals / bounded ints)
  - Every field has a docstring so the LLM sees what "good" looks like
  - Nothing is Optional unless it truly is optional at that stage of the flow
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

# ============================================================================
# SHARED TYPES
# ============================================================================


class CabinCategory(StrEnum):
    INTERIOR = "interior"
    OCEANVIEW = "oceanview"
    BALCONY = "balcony"
    SUITE = "suite"


class TravelParty(StrEnum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY_WITH_KIDS = "family_with_kids"
    MULTIGEN = "multigen"
    FRIENDS = "friends"


class Vibe(StrEnum):
    """High-level vibe taxonomy used to match user intent to ship culture."""
    RELAXATION = "relaxation"          # quiet, adults-focused, spa
    ADVENTURE = "adventure"            # active excursions, expedition-style
    PARTY = "party"                    # nightlife, casino, big ships
    FAMILY_FUN = "family_fun"          # waterslides, kids clubs, characters
    LUXURY = "luxury"                  # small ships, butler service, fine dining
    CULTURAL = "cultural"              # river cruises, port-heavy itineraries


# ============================================================================
# SHARED SAILING PRIMITIVE
# ============================================================================


class Sailing(BaseModel):
    """
    Fields shared by every model that references a specific sailing.
    ShipAssessment and BookingRecord both inherit from this.
    Only the fields truly present on both are lifted here.
    """
    sailing_id: str
    cruise_line: str
    ship_name: str
    departure_date: date


# ============================================================================
# MATCH FLOW
# ============================================================================


class MatchIntake(BaseModel):
    """
    Captured from the intake form. This is USER input, not LLM output —
    but we parse it through Pydantic so downstream agents get a clean contract.
    """
    travel_party: TravelParty
    party_size: int = Field(ge=1, le=20)
    primary_vibe: Vibe
    secondary_vibes: list[Vibe] = Field(default_factory=list, max_length=2)

    budget_per_person_usd: int = Field(ge=200, le=50_000, description="Cruise fare only, excluding flights")
    flexible_dates: bool
    earliest_departure: date
    latest_departure: date

    duration_nights_min: int = Field(ge=2, le=30)
    duration_nights_max: int = Field(ge=2, le=30)

    preferred_regions: list[str] = Field(
        description="Free-form region names like 'Caribbean', 'Alaska', 'Mediterranean', 'Norwegian Fjords'"
    )
    departure_ports_acceptable: list[str] = Field(
        description="Airport or port codes the user is willing to fly/drive to"
    )

    must_haves: list[str] = Field(
        default_factory=list,
        description="Dealbreaker requirements, e.g. 'no kids', 'accessible cabin', 'solo cabin available'",
    )
    deal_breakers: list[str] = Field(
        default_factory=list,
        description="Things that must NOT be present, e.g. 'no formal nights', 'no casino'",
    )
    preferred_cruise_lines: list[str] = Field(
        default_factory=list,
        description="Cruise lines the user prefers, e.g. from loyalty status. Empty means no preference — all lines considered equally.",
    )
    relaxed_search: bool = Field(
        default=False,
        description="When True, budget/region/duration/port constraints have been relaxed to find preferred-line sailings.",
    )
    original_budget_label: str = Field(
        default="",
        description="Human-readable budget label from the original search, e.g. '$1,500–$2,500'. Used when relaxed_search is True so the LLM can acknowledge the gap.",
    )

    cruise_experience_level: Literal["first_timer", "occasional", "loyal_cruiser"]


class ShipAssessment(Sailing):
    """
    One sub-agent's research output for a single candidate sailing.
    Fans in from parallel ship_researcher calls.
    Inherits sailing_id, cruise_line, ship_name, departure_date from Sailing.
    """
    itinerary_summary: str = Field(max_length=400)
    return_date: date
    duration_nights: int
    departure_port: str

    cabin_price_usd: int = Field(ge=0, description="Lowest available price in the user's cabin category")
    currency: str = Field(default="USD", description="ISO 4217 currency code for cabin_price_usd")
    # Distinct from BookingRecord.cabin_category — this is the category being PRICED for the user
    cabin_category_priced: CabinCategory

    vibe_score: float = Field(ge=0, le=1, description="Fit score vs user's primary_vibe, 0-1")
    fit_reasoning: str = Field(max_length=600, description="Why this ship matches or doesn't")

    strengths: list[str] = Field(max_length=4)
    concerns: list[str] = Field(max_length=4, description="Legitimate downsides the user should know")

    review_sentiment_summary: str = Field(
        max_length=500,
        description="Paraphrased summary from RAG retrieval over recent reviews — NEVER quote directly",
    )

    booking_affiliate_url: HttpUrl = Field(description="Tracked affiliate link for handoff")


class MatchResult(BaseModel):
    """
    Final output of the Match agent. Returned by POST /match/results.
    This is the artifact persisted to disk as the comparison memo.
    """
    intake_id: str
    generated_at: datetime
    agent_trace_id: str = ""

    ranked_candidates: list[ShipAssessment] = Field(min_length=1, max_length=5)

    top_pick_reasoning: str = Field(
        max_length=600,
        description="Why #1 beats #2 and #3 specifically for THIS user's intake",
    )
    counter_memo: str = Field(
        max_length=350,
        description="Honest reasons the top pick might be wrong for them — builds trust",
    )

    gaps_identified: list[str] = Field(
        default_factory=list,
        description="What the agent could not confirm and the user should verify before booking",
    )

    refinement_iterations: int = Field(
        ge=1,
        description="How many refinement passes the agent ran (iterative refinement loop telemetry)",
    )


# ============================================================================
# HANDOFF
# ============================================================================


class BookingRecord(Sailing):
    """
    Created either by:
      (a) booking_confirmed() webhook after Match handoff, OR
      (b) manual paste of a confirmation email by a user who booked elsewhere.
    Both paths create the same record. This is what Watch operates on.
    Inherits sailing_id, cruise_line, ship_name, departure_date from Sailing.
    """
    booking_id: str
    user_id: str

    # Distinct from ShipAssessment.cabin_category_priced — this is the category ACTUALLY BOOKED
    cabin_category: CabinCategory
    cabin_number: str | None = Field(default=None, description="If assigned at booking time")

    price_paid_usd: int
    perks_at_booking: list[str] = Field(
        default_factory=list,
        description="e.g. 'free gratuities', 'beverage package', '$100 OBC'",
    )

    booking_source: Literal["match", "external"]
    final_payment_date: date = Field(description="Last day price protection is available")

    created_at: datetime


# ============================================================================
# WATCH FLOW
# ============================================================================


class PriceSnapshot(BaseModel):
    """One point-in-time observation of the current market price for a watched sailing."""
    booking_id: str
    checked_at: datetime
    current_price_usd: int
    current_perks: list[str]
    source: Literal["live_api", "mock"] = Field(default="mock", description="'mock' during MVP demo")


class WatchStatus(BaseModel):
    """Current state of a watch. Returned by GET /watch/status."""
    booking_id: str
    watching_since: datetime
    checks_performed: int
    latest_snapshot: PriceSnapshot
    cumulative_savings_detected_usd: int = 0
    reprice_events_count: int = 0
    active: bool


class RepriceRecommendation(BaseModel):
    """
    Emitted by the Watch agent when price_math.py detects a net-positive reprice opportunity.
    This is the structured output that drives the notification artifact (email .txt).
    """
    booking_id: str
    detected_at: datetime
    agent_trace_id: str = ""

    # The math — computed in Python (code execution), not by the LLM
    original_price_usd: int
    new_price_usd: int
    price_delta_usd: int = Field(description="Positive means savings")
    perk_delta_description: str = Field(
        max_length=300,
        description="Plain-language summary of perks gained or lost, e.g. 'Gains free gratuities worth ~$140'",
    )
    estimated_net_benefit_usd: int = Field(description="price_delta + perk_value_delta - any fees")

    recommendation: Literal["reprice", "rebook_same_cabin", "upgrade_cabin", "hold"]
    confidence: Literal["high", "medium", "low"]

    reasoning: str = Field(
        max_length=600,
        description="Why this is worth acting on (LLM-generated, grounded in the math above)",
    )

    # Artifact: the actual email body the user will forward to their travel agent
    suggested_email_subject: str = Field(max_length=120)
    suggested_email_body: str = Field(
        max_length=2000,
        description="Pre-filled, polite reprice request the user can send as-is",
    )


# ============================================================================
# ACCOUNT
# ============================================================================


class AccountSummary(BaseModel):
    """Returned by GET /account/me. Formalised once auth is wired."""
    user_id: str
    email: str
    active_watches: int
    total_bookings: int

