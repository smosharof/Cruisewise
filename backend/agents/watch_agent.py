"""
Watch orchestrator — runs a single check for one booking and emits a
RepriceRecommendation when the math clears the threshold.

Flow:
  1. Fetch booking from `bookings` (price_paid_usd + perks_at_booking are
     the fixed reference — what the user actually paid at booking time)
  2. Read the single most recent snapshot from price_history (current price)
  3. price_math.compute_benefit on (latest snapshot, price_paid_usd)
  4. If estimated_net_benefit_usd < 50 → return None (deterministic, no LLM)
  5. Otherwise call reprice_writer (LLM) for reasoning + email
  6. Persist to reprice_events
  7. Return the assembled RepriceRecommendation

The baseline is the booked price, NOT the previous snapshot. Comparing
snapshots against each other meant repeated mock drops would each be
measured against the prior drop, producing tiny incremental deltas and
making the threshold gate unreachable after the first event.

Why we don't call run_price_check inside this function: in the mock demo,
run_price_check returns the static inventory list price, which would
overwrite a fresh inject_mock_drop snapshot and erase the drop the user
wants to act on. In production, a Cloud Scheduler job would call
run_price_check on its own cadence; this function only analyses what's
already in price_history.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import asyncpg
from firebase_admin import auth as firebase_auth

from backend.agents.subagents.reprice_writer import write_reprice
from backend.schemas import PriceSnapshot, RepriceRecommendation
from backend.tools.email_sender import send_reprice_email
from backend.tools.price_math import REPRICE_THRESHOLD_USD, compute_benefit

logger = logging.getLogger(__name__)


async def run_watch_check(
    booking_id: str, pool: asyncpg.Pool
) -> RepriceRecommendation | None:
    """Run a single watch check. Returns a recommendation or None.

    None means either:
      - booking missing
      - no baseline snapshot (this is the first check)
      - net benefit below threshold
    """
    booking_uuid = uuid.UUID(booking_id)

    async with pool.acquire() as conn:
        booking_row = await conn.fetchrow(
            "SELECT id, user_id, sailing_id, cruise_line, ship_name, departure_date, "
            "cabin_category, price_paid_usd, perks_at_booking, final_payment_date "
            "FROM bookings WHERE id = $1",
            booking_uuid,
        )
        if booking_row is None:
            logger.warning("run_watch_check: booking %s not found", booking_id)
            return None

        # 2. Read the single most recent snapshot — the current observed price.
        latest_row = await conn.fetchrow(
            "SELECT current_price_usd, current_perks, checked_at, source "
            "FROM price_history WHERE booking_id = $1 "
            "ORDER BY checked_at DESC LIMIT 1",
            booking_uuid,
        )

    if latest_row is None:
        logger.info(
            "run_watch_check: no snapshots yet for %s, nothing to compare",
            booking_id,
        )
        return None

    latest_perks = _normalise_perks(latest_row["current_perks"])

    latest = PriceSnapshot(
        booking_id=booking_id,
        checked_at=latest_row["checked_at"],
        current_price_usd=int(latest_row["current_price_usd"]),
        current_perks=latest_perks,
        source=latest_row["source"],
    )

    # 3. Compute benefit against the booked price + perks (the fixed reference,
    # not the previous snapshot). This guarantees that repeated mock drops or
    # repeated checks at the same fare always report the true total savings
    # vs what the user paid.
    booked_perks = _normalise_perks(booking_row["perks_at_booking"])
    benefit = compute_benefit(
        snapshot=latest,
        price_paid_usd=int(booking_row["price_paid_usd"]),
        perks_at_booking=booked_perks,
    )

    # 4. Threshold gate — pure Python, no LLM call below threshold
    if benefit["estimated_net_benefit_usd"] < REPRICE_THRESHOLD_USD:
        logger.info(
            "run_watch_check: net=$%d below threshold ($%d), hold",
            benefit["estimated_net_benefit_usd"],
            REPRICE_THRESHOLD_USD,
        )
        return None

    # 5. Hand to the LLM for reasoning + email
    booking_for_llm = {
        "booking_id": booking_id,
        "sailing_id": booking_row["sailing_id"],
        "cruise_line": booking_row["cruise_line"],
        "ship_name": booking_row["ship_name"],
        "departure_date": booking_row["departure_date"].isoformat(),
        "cabin_category": booking_row["cabin_category"],
        "price_paid_usd": int(booking_row["price_paid_usd"]),
        "perks_at_booking": _normalise_perks(booking_row["perks_at_booking"]),
        "final_payment_date": booking_row["final_payment_date"].isoformat(),
    }
    writer_output = await write_reprice(booking_for_llm, benefit)

    # 6. Assemble the RepriceRecommendation
    detected_at = datetime.now(tz=UTC)
    recommendation = RepriceRecommendation(
        booking_id=booking_id,
        detected_at=detected_at,
        agent_trace_id="",
        original_price_usd=benefit["original_price_usd"],
        new_price_usd=benefit["new_price_usd"],
        price_delta_usd=benefit["price_delta_usd"],
        perk_delta_description=benefit["perk_delta_description"],
        estimated_net_benefit_usd=benefit["estimated_net_benefit_usd"],
        recommendation=writer_output.recommendation,
        confidence=writer_output.confidence,
        reasoning=writer_output.reasoning,
        suggested_email_subject=writer_output.suggested_email_subject,
        suggested_email_body=writer_output.suggested_email_body,
    )

    # 7. Persist to reprice_events and bump the watch counter
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO reprice_events "
            "(booking_id, detected_at, recommendation_json) "
            "VALUES ($1, $2, $3::jsonb)",
            booking_uuid,
            detected_at,
            recommendation.model_dump_json(),
        )
        await conn.execute(
            "UPDATE watches SET reprice_events_count = reprice_events_count + 1 "
            "WHERE booking_id = $1",
            booking_uuid,
        )

    logger.info(
        "run_watch_check: reprice booking=%s savings=$%d rec=%s confidence=%s",
        booking_id,
        benefit["estimated_net_benefit_usd"],
        recommendation.recommendation,
        recommendation.confidence,
    )

    # 8. Fire-and-forget Resend email when the agent's recommendation is to
    # reprice. Skipped for guest/demo users (no Firebase identity to look up)
    # and for any errors in the lookup or send. Non-fatal: the reprice
    # recommendation is still returned to the caller either way.
    if recommendation.recommendation == "reprice":
        try:
            user_id = booking_row["user_id"]
            if (
                user_id
                and not user_id.startswith("guest-")
                and user_id not in ("guest", "demo-user")
            ):
                fb_user = firebase_auth.get_user(user_id)
                to_email = fb_user.email if fb_user else None
                if to_email:
                    send_reprice_email(
                        to_email=to_email,
                        ship_name=booking_row["ship_name"],
                        cruise_line=booking_row["cruise_line"],
                        departure_date=booking_row["departure_date"].isoformat(),
                        cabin_category=booking_row["cabin_category"],
                        price_paid=int(booking_row["price_paid_usd"]),
                        current_price=int(latest_row["current_price_usd"]),
                        savings=int(recommendation.estimated_net_benefit_usd),
                        email_subject=recommendation.suggested_email_subject,
                        email_body=recommendation.suggested_email_body,
                    )
        except Exception as e:
            logger.warning("Could not send reprice email for %s: %s", booking_id, e)

    return recommendation


# Kept for compatibility with the original stub signature; new code calls
# run_watch_check directly so it can fan out a fresh price check itself.
async def evaluate_snapshot(
    snapshot: PriceSnapshot, booking_id: str
) -> RepriceRecommendation | None:
    raise NotImplementedError(
        "evaluate_snapshot is superseded by run_watch_check(booking_id, pool)"
    )


def _normalise_perks(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw or [])
