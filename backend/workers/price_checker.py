"""
Mock price checker — single-booking price snapshot writer.

In production this runs as a Cloud Scheduler → Cloud Run Job that polls all
active watches and writes to price_history. For the MVP demo, the routes
call run_price_check directly when the user clicks "Check now", and
inject_mock_drop simulates a drop on demand.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import asyncpg

from backend.schemas import CabinCategory, PriceSnapshot
from backend.tools.cruise_inventory import get_sailing

logger = logging.getLogger(__name__)


async def run_price_check(booking_id: str, pool: asyncpg.Pool) -> PriceSnapshot | None:
    """Fetch current mock price for a watched booking and persist to price_history.

    Mock = the inventory's current price for the booking's cabin_category.
    Returns None if the booking or sailing is missing.
    """
    booking_uuid = uuid.UUID(booking_id)

    async with pool.acquire() as conn:
        booking = await conn.fetchrow(
            "SELECT sailing_id, cabin_category, perks_at_booking "
            "FROM bookings WHERE id = $1",
            booking_uuid,
        )
        if booking is None:
            logger.warning("run_price_check: booking %s not found", booking_id)
            return None

        sailing = await get_sailing(booking["sailing_id"], pool)
        if sailing is None:
            logger.warning(
                "run_price_check: sailing %s not in inventory", booking["sailing_id"]
            )
            return None

        cabin_cat: str = booking["cabin_category"]
        current_price = sailing["prices"].get(cabin_cat)
        if current_price is None:
            logger.warning(
                "run_price_check: cabin category %s missing for sailing %s",
                cabin_cat,
                booking["sailing_id"],
            )
            return None

        # Carry the original perks forward — mock inventory doesn't track perk drift
        raw_perks = booking["perks_at_booking"]
        if isinstance(raw_perks, str):
            current_perks = json.loads(raw_perks)
        else:
            current_perks = list(raw_perks or [])

        snapshot = PriceSnapshot(
            booking_id=booking_id,
            checked_at=datetime.now(tz=UTC),
            current_price_usd=int(current_price),
            current_perks=current_perks,
            source="mock",
        )

        await conn.execute(
            "INSERT INTO price_history "
            "(booking_id, checked_at, current_price_usd, current_perks, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            booking_uuid,
            snapshot.checked_at,
            snapshot.current_price_usd,
            json.dumps(snapshot.current_perks),
            snapshot.source,
        )

        # Increment checks_performed on the watch row
        await conn.execute(
            "UPDATE watches SET checks_performed = checks_performed + 1 "
            "WHERE booking_id = $1",
            booking_uuid,
        )

    logger.info(
        "Price check booking=%s price=$%d (cabin=%s)",
        booking_id,
        snapshot.current_price_usd,
        cabin_cat,
    )
    return snapshot


async def inject_mock_drop(
    booking_id: str, pool: asyncpg.Pool, drop_amount_usd: int = 300
) -> PriceSnapshot | None:
    """Simulate a price drop for demo purposes.

    Writes a low-price snapshot to price_history at (price_paid - drop_amount_usd).
    The next watch check will see this as the latest snapshot, with the prior
    snapshot (run_price_check on register) as the original baseline.
    """
    booking_uuid = uuid.UUID(booking_id)

    async with pool.acquire() as conn:
        booking = await conn.fetchrow(
            "SELECT price_paid_usd, perks_at_booking FROM bookings WHERE id = $1",
            booking_uuid,
        )
        if booking is None:
            logger.warning("inject_mock_drop: booking %s not found", booking_id)
            return None

        new_price = max(int(booking["price_paid_usd"]) - drop_amount_usd, 0)
        raw_perks = booking["perks_at_booking"]
        if isinstance(raw_perks, str):
            current_perks = json.loads(raw_perks)
        else:
            current_perks = list(raw_perks or [])

        snapshot = PriceSnapshot(
            booking_id=booking_id,
            checked_at=datetime.now(tz=UTC),
            current_price_usd=new_price,
            current_perks=current_perks,
            source="mock",
        )

        await conn.execute(
            "INSERT INTO price_history "
            "(booking_id, checked_at, current_price_usd, current_perks, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            booking_uuid,
            snapshot.checked_at,
            snapshot.current_price_usd,
            json.dumps(snapshot.current_perks),
            snapshot.source,
        )

    logger.info(
        "Mock drop injected booking=%s new_price=$%d (drop=$%d)",
        booking_id,
        new_price,
        drop_amount_usd,
    )
    return snapshot


# Re-export for type hint discoverability
__all__ = ["run_price_check", "inject_mock_drop", "CabinCategory"]
