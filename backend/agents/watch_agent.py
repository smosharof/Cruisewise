"""
Watch orchestrator — runs a single check for one booking and emits a
RepriceRecommendation when the math clears the threshold.

Flow:
  1. Fetch booking from `bookings`
  2. Read the two most recent snapshots from price_history
     (baseline = older, latest = newer)
  3. price_math.compute_benefit on (latest, baseline)
  4. If estimated_net_benefit_usd < 50 → return None (deterministic, no LLM)
  5. Otherwise call reprice_writer (LLM) for reasoning + email
  6. Persist to reprice_events
  7. Return the assembled RepriceRecommendation

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

from backend.agents.subagents.reprice_writer import write_reprice
from backend.schemas import PriceSnapshot, RepriceRecommendation
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
            "SELECT id, sailing_id, cruise_line, ship_name, departure_date, "
            "cabin_category, price_paid_usd, perks_at_booking, final_payment_date "
            "FROM bookings WHERE id = $1",
            booking_uuid,
        )
        if booking_row is None:
            logger.warning("run_watch_check: booking %s not found", booking_id)
            return None

        # 2. Read the two most recent snapshots; baseline = older, latest = newer
        rows = await conn.fetch(
            "SELECT current_price_usd, current_perks, checked_at, source "
            "FROM price_history WHERE booking_id = $1 "
            "ORDER BY checked_at DESC LIMIT 2",
            booking_uuid,
        )

    if len(rows) < 2:
        logger.info(
            "run_watch_check: only %d snapshot(s) for %s, need at least 2 to compare",
            len(rows),
            booking_id,
        )
        return None

    latest_row, baseline_row = rows[0], rows[1]
    latest_perks = _normalise_perks(latest_row["current_perks"])
    baseline_price = int(baseline_row["current_price_usd"])
    baseline_perks = _normalise_perks(baseline_row["current_perks"])

    latest = PriceSnapshot(
        booking_id=booking_id,
        checked_at=latest_row["checked_at"],
        current_price_usd=int(latest_row["current_price_usd"]),
        current_perks=latest_perks,
        source=latest_row["source"],
    )

    # 3. Compute benefit. Baseline acts as the "paid" reference; latest is the
    # "current offer". The Watch agent therefore measures the most recent
    # observed delta — independent of how the snapshots were produced.
    benefit = compute_benefit(
        snapshot=latest,
        price_paid_usd=baseline_price,
        perks_at_booking=baseline_perks,
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
