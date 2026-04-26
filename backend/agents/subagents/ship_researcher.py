"""
Ship researcher sub-agent — runs once per candidate sailing during Match fan-out.

Cabin category selection happens in Python before the agent runs (highest tier ≤ budget).
The LLM handles vibe scoring, fit reasoning, strengths/concerns, and review synthesis.
"""

from __future__ import annotations

import json
import logging
import urllib.parse

from agents import Agent, Runner

from backend.config import get_settings
from backend.llm import get_chat_model
from backend.schemas import CabinCategory, MatchIntake, ShipAssessment

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a cruise expert evaluating a specific sailing for a specific traveler.

You will receive a JSON object with:
  - sailing: the full sailing dict (id, itinerary, prices, dates, port)
  - intake: the traveler's stated preferences
  - selected_cabin_category: the highest cabin tier within budget (pre-computed in Python)
  - cabin_price_usd: the dollar price for that tier
  - budget_fits: false if even the interior cabin exceeds budget
  - affiliate_url: the booking URL to use verbatim

Your output must be a ShipAssessment. Copy the following fields verbatim from sailing:
  sailing_id, cruise_line, ship_name, departure_date, return_date, duration_nights,
  departure_port, itinerary_summary

Rules for each LLM-generated field:

VIBE_SCORE (float 0.0–1.0)
  Score how well this ship/line matches the traveler's primary_vibe using your training
  knowledge of cruise line culture. Reference cues:
  - Royal Caribbean Oasis/Icon/Wonder-class → family_fun / party (megaships, waterslides,
    25,000+ passengers, busy pools, entertainment everywhere)
  - Carnival → party / family_fun (lively atmosphere, casino-forward, younger crowd)
  - Norwegian (NCL) → party / flexibility (Freestyle dining, big entertainment, frenetic)
  - MSC → value-oriented, mixed international crowd, busy ships
  - Princess → relaxation (quieter, older demographic, enrichment, refined pacing)
  - Holland America → relaxation / cultural (mature passengers, port-intensive, no rush)
  - Celebrity → luxury-leaning (modern luxury, adults-focused, elevated dining)
  - Viking Ocean → cultural (highest cultural score of any line — no casino, no kids
    under 18 on most sailings, destination-focused programming, included shore
    excursions, lecture series onboard)
  - Virgin Voyages → party / adults-only (strict no-kids policy, nightlife, trendy bars)
  - Disney Cruise Line → family_fun (premium tier — higher price than Carnival/Royal
    Caribbean but exceptional for families with children, Disney characters, immersive
    theming, Castaway Cay private island; adults-only areas available but the ship
    culture is child-forward)
  - Regent Seven Seas → luxury (ultra-luxury, all-inclusive including shore excursions,
    gratuities, specialty dining, business-class flights on longer sailings; small
    ships ~700 passengers, butler service in all suites, no interior cabins on newer
    ships — "interior" pricing in our inventory exists for legacy compatibility but
    Regent is suite-dominant)
  A score of 1.0 means this ship is purpose-built for that vibe. 0.0 means fundamentally
  at odds with it. Partial scores should reflect genuine overlap.

FIT_REASONING (max 600 chars)
  - WRITING STYLE: Never use underscore field names (party_size, primary_vibe,
    budget_per_person_usd, travel_party, cruise_experience_level, preferred_regions)
    in your output. Use natural language. Pull values from the intake's
    natural-language fields (who, vibe, budget, regions, duration, experience).
  - MUST name specific intake values, not just concepts. Example: do not say
    "this suits couples"; say "as a couple seeking relaxation, Princess skews
    toward an older, quieter crowd that fits your vibe."
  - Reference the user's vibe, who they're traveling with, party size, budget,
    experience level, and preferred regions in your reasoning — by VALUE, not
    by field name.
  - If the budget doesn't cover the cheapest cabin, state the specific dollar
    gap ("interior at $X exceeds your $Y budget") and note this in a concern.
  - If the user has preferred cruise lines (intake.preferred_lines is a list,
    not the string "No preference") AND this sailing's cruise line is in that
    list, mention the preference naturally — e.g. note that their loyalty
    status will apply, or that they are already familiar with this line's
    experience. If this sailing is NOT on a preferred line, do not mention
    the preference at all.
  - If intake.relaxed_search is true (filters were relaxed to surface
    preferred-line sailings), acknowledge the budget gap honestly in ONE
    brief sentence. Example: "Note: this sailing exceeds your original
    budget of {intake.original_budget_label} — it appears here because
    {cruise_line} is your preferred line and no {cruise_line} sailings were
    available within your budget." Use the original_budget_label value
    verbatim. Do not pretend the relaxed budget is the user's actual cap.

STRENGTHS (list, 2–4 items)
  - Specific to THIS itinerary and THIS traveler's intake, not generic ship facts
  - Good: "Eastern Caribbean stops at St. Maarten and St. Kitts offer calm snorkeling
    beaches ideal for a relaxation-seeking couple"
  - Bad: "Beautiful ship with many amenities"

CONCERNS (list, 2–4 items)
  - Must be genuine downsides the traveler should weigh, not disguised compliments
  - FORBIDDEN phrases: "so popular you'll want to book early", "too many options",
    "you might not want to leave"
  - REQUIRED to name real issues where they apply:
    * Carnival/RC Icon-class: high passenger density, busy pool decks, long lines at sea days
    * Port-heavy Caribbean itineraries: tender ports can add 45-90 min transit
    * Family ships during school breaks: heavy family atmosphere even for couples
    * Party/casino-heavy lines for relaxation seekers: ambient noise, late-night crowds
    * First-timers on megaships: navigation overwhelming, hard to find quiet space
    * MSC: inconsistent English-language service reported on some sailings
  - Name the actual problem plainly in 1 sentence

REVIEW_SENTIMENT_SUMMARY
  - Maximum 280 characters. Two sentences maximum. Paraphrase only — no quotes.
  - Paraphrase what travelers typically say about this ship from your training knowledge
  - Never use quotation marks or attribute a quote to any person
  - Factual and specific. Stop at 280 chars.

BOOKING_AFFILIATE_URL
  - Copy the affiliate_url value exactly as provided. Do not alter any part of the URL.

cabin_category_priced: use selected_cabin_category (provided)
cabin_price_usd: use cabin_price_usd (provided)
"""


_PARTY_LABELS = {
    "solo": "a solo traveler",
    "couple": "a couple",
    "family_with_kids": "a family with kids",
    "multigen": "a multi-generational group",
    "friends": "a friends group",
}
_VIBE_LABELS = {
    "relaxation": "relaxation",
    "adventure": "adventure",
    "party": "party",
    "family_fun": "family fun",
    "luxury": "luxury",
    "cultural": "cultural",
}
_EXPERIENCE_LABELS = {
    "first_timer": "first-time cruiser",
    "occasional": "occasional cruiser",
    "loyal_cruiser": "seasoned cruiser",
}


def _humanize_intake(intake: MatchIntake) -> dict:
    """Project the intake onto natural-language fields the LLM can quote.

    The raw intake schema uses underscored Pythonic names (party_size,
    primary_vibe, budget_per_person_usd) that the model would otherwise
    parrot back into user-facing copy. Mapping to friendly labels here
    keeps the system prompt directive ('no underscore field names') easy
    to follow.
    """
    budget = intake.budget_per_person_usd
    if budget <= 1500:
        budget_label = "under $1,500"
    elif budget <= 2500:
        budget_label = "$1,500–$2,500"
    elif budget <= 4000:
        budget_label = "$2,500–$4,000"
    else:
        budget_label = "$4,000+"

    # When the frontend's "Show preferred-line sailings only" CTA fires, every
    # filter is relaxed and budget jumps to a sentinel ($50k). We don't want
    # the LLM to parrot back "$4,000+" as if that were the user's actual cap;
    # instead we hand it the original budget plus an explicit note that the
    # current sailing may exceed it.
    if intake.relaxed_search and intake.original_budget_label:
        budget_context = (
            f"Original budget was {intake.original_budget_label} — filters were "
            "relaxed to find preferred cruise line sailings. This sailing may "
            "exceed the original budget."
        )
    else:
        budget_context = budget_label

    return {
        "who": _PARTY_LABELS.get(intake.travel_party.value, intake.travel_party.value),
        "party_size": intake.party_size,
        "vibe": _VIBE_LABELS.get(intake.primary_vibe.value, intake.primary_vibe.value),
        "budget": budget_context,
        "regions": list(intake.preferred_regions),
        "duration": f"{intake.duration_nights_min}–{intake.duration_nights_max} nights",
        "experience": _EXPERIENCE_LABELS.get(
            intake.cruise_experience_level, intake.cruise_experience_level
        ),
        "must_haves": list(intake.must_haves),
        "deal_breakers": list(intake.deal_breakers),
        "preferred_lines": (
            list(intake.preferred_cruise_lines)
            if intake.preferred_cruise_lines
            else "No preference"
        ),
        "relaxed_search": intake.relaxed_search,
        "original_budget_label": intake.original_budget_label,
    }


def _select_cabin(prices: dict, budget: int) -> tuple[CabinCategory, int, bool]:
    """Pick the highest cabin category whose price is ≤ budget.

    Returns (category, price, budget_fits). If nothing fits, returns interior
    with budget_fits=False so the agent can note the gap in its reasoning.
    """
    for cat in (CabinCategory.SUITE, CabinCategory.BALCONY, CabinCategory.OCEANVIEW, CabinCategory.INTERIOR):
        if prices[cat.value] <= budget:
            return cat, prices[cat.value], True
    return CabinCategory.INTERIOR, prices[CabinCategory.INTERIOR.value], False


async def research_ship(sailing: dict, intake: MatchIntake) -> ShipAssessment:
    """Produce a ShipAssessment for one candidate sailing.

    Cabin selection is done in Python before the agent runs so the LLM never
    does arithmetic. The agent receives the pre-computed cabin tier and price.
    """
    settings = get_settings()

    cabin_cat, cabin_price, budget_fits = _select_cabin(
        sailing["prices"], intake.budget_per_person_usd
    )
    # Prefer the real cruise-line booking URL from Apify; fall back only when
    # the actor didn't expose one. The fallback hits the same partner stub the
    # frontend already understands, so the affiliate handoff path is preserved.
    affiliate_url = sailing.get("booking_url") or (
        f"https://partner.example.com/book"
        f"?sailing={sailing.get('id') or sailing.get('sailing_id', '')}&ref=cruisewise"
    )

    # Serialize dates to ISO strings so json.dumps doesn't choke. return_date
    # may legitimately be missing from some Apify actors; cruise_inventory
    # backfills it but we keep a None guard here so a stray null can't crash
    # the agent at the boundary.
    sailing_serializable = {
        **sailing,
        "departure_date": sailing["departure_date"].isoformat(),
        "return_date": (
            sailing["return_date"].isoformat() if sailing.get("return_date") else None
        ),
    }

    user_message = json.dumps(
        {
            "sailing": sailing_serializable,
            "intake": _humanize_intake(intake),
            "selected_cabin_category": cabin_cat.value,
            "cabin_price_usd": cabin_price,
            "budget_fits": budget_fits,
            "affiliate_url": affiliate_url,
        },
        indent=2,
        ensure_ascii=False,  # Pass literal Unicode (Roatán) to the LLM, not á
    )

    agent = Agent(
        name="ship_researcher",
        instructions=_SYSTEM_PROMPT,
        model=get_chat_model(settings.llm_model),
        output_type=ShipAssessment,
    )

    logger.debug(
        "ship_researcher starting: sailing=%s cabin=%s price=%d",
        sailing["sailing_id"],
        cabin_cat.value,
        cabin_price,
    )

    result = await Runner.run(agent, user_message)
    assessment = result.final_output_as(ShipAssessment)

    # Defensive decode: Gemini occasionally URL-encodes non-ASCII characters
    # (Roat%C3%A1n instead of Roatán) when copying the itinerary verbatim.
    assessment.itinerary_summary = urllib.parse.unquote(assessment.itinerary_summary)

    # Currency is metadata about the price, not something the LLM should
    # decide. Pull it from the sailing dict directly so GBP/EUR/AUD records
    # render with the right symbol on the frontend.
    assessment.currency = sailing.get("currency", "USD")

    logger.info(
        "ship_researcher done: sailing=%s vibe_score=%.2f cabin=%s",
        assessment.sailing_id,
        assessment.vibe_score,
        assessment.cabin_category_priced,
    )
    return assessment
