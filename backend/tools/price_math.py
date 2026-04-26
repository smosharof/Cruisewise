"""
Price math tool — pure-Python net-benefit calculator. No I/O, no LLM.

Returns a plain TypedDict so the watch_agent can assemble the full
RepriceRecommendation (which also needs LLM-generated reasoning and email body)
without this module depending on the Pydantic schema layer.
"""

from __future__ import annotations

from typing import TypedDict

from backend.schemas import PriceSnapshot

# Conservative USD estimates for common cruise perks.
# Intentionally underestimates to keep the false-positive rate low.
_PERK_VALUES: dict[str, int] = {
    "beverage_package": 90,        # per person, 7-night basis
    "gratuities": 18,              # per person per day
    "wifi": 25,                    # per device per day
    "specialty_dining": 60,        # two dinners per couple
    "shore_excursion_credit": 50,
    "onboard_credit": 1,           # 1:1 — only if you'll spend it
    "free_cabin_upgrade": 150,
}

# Minimum net benefit (whole dollars) below which we skip the reprice alert.
REPRICE_THRESHOLD_USD: int = 50


class BenefitCalc(TypedDict):
    """Pure-math output of compute_benefit. All dollar amounts are whole integers."""
    original_price_usd: int
    new_price_usd: int
    price_delta_usd: int           # positive = savings
    perk_delta_usd: int            # positive = current perks worth more
    perk_delta_description: str    # plain-language summary for the LLM to reference
    estimated_net_benefit_usd: int # price_delta + perk_delta
    worth_repricing: bool          # estimated_net_benefit >= REPRICE_THRESHOLD_USD


def perk_value(perks: list[str]) -> int:
    """Estimate total USD value of a list of perk strings."""
    return sum(_PERK_VALUES.get(p.lower().replace(" ", "_"), 0) for p in perks)


def _describe_perk_delta(gained: list[str], lost: list[str], delta_usd: int) -> str:
    """Build a plain-language perk-delta string for the email and LLM context."""
    if not gained and not lost:
        return "Perks unchanged."
    parts: list[str] = []
    if gained:
        parts.append(f"Gains: {', '.join(gained)} (~${perk_value(gained)} value)")
    if lost:
        parts.append(f"Loses: {', '.join(lost)} (~${perk_value(lost)} value)")
    sign = "+" if delta_usd >= 0 else ""
    parts.append(f"Net perk change: {sign}${delta_usd}")
    return ". ".join(parts)


def compute_benefit(
    snapshot: PriceSnapshot,
    price_paid_usd: int,
    perks_at_booking: list[str],
) -> BenefitCalc:
    """Calculate the net financial benefit of repricing to the current offer.

    price_delta   = price_paid − current_price  (positive → cheaper now)
    perk_delta    = value(current_perks) − value(original_perks)
    net_benefit   = price_delta + perk_delta

    A reprice is worth surfacing when net_benefit >= REPRICE_THRESHOLD_USD.
    """
    current_price = snapshot.current_price_usd
    price_delta = price_paid_usd - current_price

    current_perk_set = set(p.lower().replace(" ", "_") for p in snapshot.current_perks)
    original_perk_set = set(p.lower().replace(" ", "_") for p in perks_at_booking)
    gained = [p for p in snapshot.current_perks if p.lower().replace(" ", "_") in current_perk_set - original_perk_set]
    lost = [p for p in perks_at_booking if p.lower().replace(" ", "_") in original_perk_set - current_perk_set]

    perk_delta = perk_value(snapshot.current_perks) - perk_value(perks_at_booking)
    net = price_delta + perk_delta

    return BenefitCalc(
        original_price_usd=price_paid_usd,
        new_price_usd=current_price,
        price_delta_usd=price_delta,
        perk_delta_usd=perk_delta,
        perk_delta_description=_describe_perk_delta(gained, lost, perk_delta),
        estimated_net_benefit_usd=net,
        worth_repricing=net >= REPRICE_THRESHOLD_USD,
    )
