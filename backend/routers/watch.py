from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.watch_agent import run_watch_check
from backend.db import get_pool
from backend.schemas import BookingRecord, PriceSnapshot, RepriceRecommendation, WatchStatus
from backend.workers.price_checker import inject_mock_drop, run_price_check

logger = logging.getLogger(__name__)
router = APIRouter()


class WatchAck(BaseModel):
    status: str
    booking_id: str


class HoldResponse(BaseModel):
    """Returned when a watch check decides not to act."""

    action: str
    reason: str


@router.post("/register", response_model=WatchAck, status_code=201)
async def register_watch(booking: BookingRecord) -> WatchAck:
    """Persist a booking, create its watch row, and take a baseline price snapshot.

    The booking_id sent by the client is used as the DB primary key; it must
    be a UUID string. The frontend generates one with crypto.randomUUID().
    """
    logger.info(
        "register_watch: booking_source=%s sailing_id=%s cruise_line=%s ship_name=%s departure_date=%s",
        booking.booking_source,
        booking.sailing_id,
        booking.cruise_line,
        booking.ship_name,
        booking.departure_date,
    )
    try:
        booking_uuid = uuid.UUID(booking.booking_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"booking_id must be a valid UUID: {booking.booking_id}"
        ) from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        # Manual ("external") bookings arrive with a synthetic sailing_id like
        # "princess-20260607-i-watch" that won't match any real sailings.id, so
        # the baseline price check can never resolve. Look up the real id by
        # (cruise_line, ship_name, departure_date) and overwrite. If nothing
        # matches we leave the synthetic id in place — the watch still
        # registers, just without a baseline snapshot.
        if booking.booking_source == "external":
            real_sailing = await conn.fetchrow(
                "SELECT id FROM sailings "
                "WHERE cruise_line = $1 AND ship_name = $2 AND departure_date = $3 "
                "LIMIT 1",
                booking.cruise_line,
                booking.ship_name,
                booking.departure_date,
            )
            if real_sailing is not None:
                booking = booking.model_copy(update={"sailing_id": real_sailing["id"]})
                logger.info(
                    "Resolved external sailing_id=%s for %s %s on %s",
                    real_sailing["id"],
                    booking.cruise_line,
                    booking.ship_name,
                    booking.departure_date,
                )
            else:
                logger.warning(
                    "No sailing found in DB for %s %s on %s — baseline check will skip",
                    booking.cruise_line,
                    booking.ship_name,
                    booking.departure_date,
                )

        # Block a second active watch on the same sailing. We don't currently
        # disambiguate by user_id because the demo doesn't persist it on
        # bookings (column stays NULL), so checking sailing_id + active is the
        # tightest signal we have. Surfaces 409 with the existing booking_id
        # so the client can deep-link to the Watch page.
        existing = await conn.fetchval(
            "SELECT w.booking_id FROM watches w "
            "JOIN bookings b ON b.id = w.booking_id "
            "WHERE b.sailing_id = $1 AND w.active = TRUE "
            "LIMIT 1",
            booking.sailing_id,
        )
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=f"already_watching:{existing}"
            )

        # Idempotent: if the same booking_id is registered twice, second time wins.
        await conn.execute(
            "INSERT INTO bookings "
            "(id, sailing_id, cruise_line, ship_name, departure_date, "
            " cabin_category, cabin_number, price_paid_usd, perks_at_booking, "
            " booking_source, final_payment_date, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12) "
            "ON CONFLICT (id) DO UPDATE SET "
            " sailing_id=EXCLUDED.sailing_id, "
            " cruise_line=EXCLUDED.cruise_line, "
            " ship_name=EXCLUDED.ship_name, "
            " departure_date=EXCLUDED.departure_date, "
            " cabin_category=EXCLUDED.cabin_category, "
            " cabin_number=EXCLUDED.cabin_number, "
            " price_paid_usd=EXCLUDED.price_paid_usd, "
            " perks_at_booking=EXCLUDED.perks_at_booking, "
            " booking_source=EXCLUDED.booking_source, "
            " final_payment_date=EXCLUDED.final_payment_date",
            booking_uuid,
            booking.sailing_id,
            booking.cruise_line,
            booking.ship_name,
            booking.departure_date,
            booking.cabin_category.value,
            booking.cabin_number,
            booking.price_paid_usd,
            json.dumps(list(booking.perks_at_booking)),
            booking.booking_source,
            booking.final_payment_date,
            booking.created_at,
        )

        # Watch is also idempotent: re-registering refreshes active=true.
        await conn.execute(
            "INSERT INTO watches (booking_id, active, watching_since) "
            "VALUES ($1, TRUE, $2) "
            "ON CONFLICT (booking_id) DO UPDATE SET active=TRUE",
            booking_uuid,
            datetime.now(tz=UTC),
        )

    # Baseline snapshot so the first user-driven check has something to compare
    # to. Non-fatal: if the sailing_id isn't in inventory (manual entry with a
    # synthetic id), the watch is already registered — the user just sees "Not
    # yet checked" until they click Check now.
    try:
        await run_price_check(booking.booking_id, pool)
    except Exception:
        logger.warning(
            "Initial price check failed for %s; watch registered without baseline",
            booking.booking_id,
            exc_info=True,
        )

    logger.info("Watch registered booking_id=%s sailing=%s", booking.booking_id, booking.sailing_id)
    return WatchAck(status="watching", booking_id=booking.booking_id)


@router.get("/status/{booking_id}", response_model=WatchStatus)
async def get_watch_status(booking_id: str) -> WatchStatus:
    """Return the latest WatchStatus for a booking, or 404."""
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Invalid booking_id: {booking_id}") from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        watch = await conn.fetchrow(
            "SELECT watching_since, checks_performed, reprice_events_count, active "
            "FROM watches WHERE booking_id = $1",
            booking_uuid,
        )
        if watch is None:
            raise HTTPException(status_code=404, detail=f"No watch for booking {booking_id}")

        snap = await conn.fetchrow(
            "SELECT current_price_usd, current_perks, checked_at, source "
            "FROM price_history WHERE booking_id = $1 "
            "ORDER BY checked_at DESC LIMIT 1",
            booking_uuid,
        )
        if snap is None:
            raise HTTPException(
                status_code=404, detail=f"No price snapshots yet for booking {booking_id}"
            )

        # cumulative_savings = price_paid - latest snapshot price (clipped to >= 0)
        booking = await conn.fetchrow(
            "SELECT price_paid_usd FROM bookings WHERE id = $1",
            booking_uuid,
        )

    perks = _coerce_perks(snap["current_perks"])
    cumulative = max(int(booking["price_paid_usd"]) - int(snap["current_price_usd"]), 0)

    return WatchStatus(
        booking_id=booking_id,
        watching_since=watch["watching_since"],
        checks_performed=int(watch["checks_performed"]),
        latest_snapshot=PriceSnapshot(
            booking_id=booking_id,
            checked_at=snap["checked_at"],
            current_price_usd=int(snap["current_price_usd"]),
            current_perks=perks,
            source=snap["source"],
        ),
        cumulative_savings_detected_usd=cumulative,
        reprice_events_count=int(watch["reprice_events_count"]),
        active=bool(watch["active"]),
    )


@router.get("/list")
async def list_watches() -> list[dict[str, Any]]:
    """Return all active watches with their latest price snapshot.

    The bookings table's primary key column is `id` (not `booking_id`), so the
    join projects `w.booking_id` as the canonical id.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                w.booking_id,
                w.active,
                w.watching_since,
                w.checks_performed,
                w.reprice_events_count,
                b.sailing_id,
                b.cruise_line,
                b.ship_name,
                b.departure_date,
                b.cabin_category,
                b.price_paid_usd,
                b.final_payment_date,
                ph.current_price_usd AS latest_price,
                ph.checked_at AS last_checked
            FROM watches w
            JOIN bookings b ON b.id = w.booking_id
            LEFT JOIN LATERAL (
                SELECT current_price_usd, checked_at
                FROM price_history
                WHERE booking_id = w.booking_id
                ORDER BY checked_at DESC
                LIMIT 1
            ) ph ON TRUE
            WHERE w.active = TRUE
            ORDER BY w.watching_since DESC
            """
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["booking_id"] = str(d["booking_id"])
        out.append(d)
    return out


@router.post("/check/{booking_id}")
async def check_now(booking_id: str) -> Any:
    """Trigger a watch check immediately. Returns the recommendation if any,
    or {action: 'hold', reason: ...} if below threshold."""
    pool = get_pool()
    try:
        recommendation = await run_watch_check(booking_id, pool)
    except Exception:
        logger.exception("run_watch_check failed for %s", booking_id)
        raise HTTPException(status_code=500, detail="Watch check failed unexpectedly")

    if recommendation is None:
        return HoldResponse(
            action="hold",
            reason="Net benefit below $50 threshold or insufficient price history",
        )

    # FastAPI handles the dump for response_model-less endpoints via the model_dump
    return recommendation


@router.post("/demo-drop/{booking_id}")
async def demo_drop(booking_id: str) -> dict[str, Any]:
    """DEMO ONLY — inject a simulated price drop into price_history.

    Not exposed in production. Picks a random drop in [$50, $700] each call so
    successive demos exercise the hold path (sub-threshold) as well as the
    reprice path. Returns the drop amount alongside the new snapshot.
    """
    pool = get_pool()
    drop_amount = random.randint(50, 700)
    snapshot = await inject_mock_drop(booking_id, pool, drop_amount_usd=drop_amount)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")
    return {"drop_amount_usd": drop_amount, "snapshot": snapshot}


@router.get("/ships/{cruise_line}")
async def get_ships(cruise_line: str) -> list[str]:
    """Return distinct ship names for a cruise line, sorted alphabetically.

    Drives the dynamic Ship dropdown on the manual register form.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ship_name FROM sailings "
            "WHERE cruise_line = $1 "
            "ORDER BY ship_name",
            cruise_line,
        )
    return [r["ship_name"] for r in rows]


@router.delete("/{booking_id}")
async def remove_watch(booking_id: str) -> dict[str, bool]:
    """Deactivate a watch. Keeps the booking and price history; only flips
    watches.active to FALSE so /list (which filters active=TRUE) drops it."""
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Invalid booking_id: {booking_id}"
        ) from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE watches SET active = FALSE WHERE booking_id = $1",
            booking_uuid,
        )
    return {"ok": True}


# We have to keep this import-but-don't-fail handle in case the type contract
# moves around as we wire the demo. Currently unused.
_RECOMMENDATION_HINT = RepriceRecommendation


def _coerce_perks(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)
