"""Admin / demo router.

Exposes cross-user data and a price-drop trigger. There is intentionally NO
auth on these endpoints — they are reached only via the unlisted /admin.html
page. Before this ships beyond demo day, gate everything in this file behind
``Depends(get_current_user_id)`` plus an allowlisted-UID check.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from backend.agents.watch_agent import run_watch_check
from backend.db import get_pool
from backend.workers.price_checker import inject_mock_drop

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/watches")
async def list_all_watches(pool=Depends(get_pool)) -> list[dict[str, Any]]:
    """Return active watches for real authenticated users only.

    Filters out demo placeholders, guest UUIDs (``guest-…``), the literal
    ``"guest"`` fallback, and NULL — so the admin page only surfaces watches
    that belong to a Firebase-signed-in account.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                w.booking_id,
                w.watching_since,
                w.checks_performed,
                b.sailing_id,
                b.cruise_line,
                b.ship_name,
                b.departure_date,
                b.cabin_category,
                b.price_paid_usd,
                b.user_id,
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
              AND b.user_id IS NOT NULL
              AND b.user_id != 'demo-user'
              AND b.user_id NOT LIKE 'guest-%'
              AND b.user_id != 'guest'
            ORDER BY w.watching_since DESC
            """
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["booking_id"] = str(d["booking_id"])
        out.append(d)
    return out


@router.post("/trigger-drop/{booking_id}")
async def trigger_drop(
    booking_id: str,
    body: dict[str, Any],
    pool=Depends(get_pool),
) -> dict[str, Any]:
    """Inject a price drop and run the watch check agent."""
    drop_amount = body.get("drop_amount_usd", 300)
    drop_amount = max(50, min(700, int(drop_amount)))

    # Step 1: inject the drop snapshot
    await inject_mock_drop(booking_id, pool, drop_amount_usd=drop_amount)

    # Step 2: run the watch AGENT (compares snapshots, generates reprice email).
    # NOT run_price_check (which would overwrite with current DB price).
    result = await run_watch_check(booking_id, pool)

    savings = drop_amount
    if result and hasattr(result, "net_benefit_usd"):
        savings = result.net_benefit_usd

    return {"ok": True, "drop_amount_usd": drop_amount, "savings": savings}
