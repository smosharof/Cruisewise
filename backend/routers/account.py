from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends

from backend.auth import get_current_user_id, get_user_id_or_guest
from backend.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_guest(user_id: str) -> bool:
    return user_id == "guest" or user_id.startswith("guest-")


@router.get("/me")
async def get_me(
    user_id: str = Depends(get_user_id_or_guest),
) -> dict[str, Any]:
    """Return the current user's account summary, scoped by Authorization header.

    Counts come from real DB tables filtered by the resolved user_id:
      - active_watches: live watches whose booking belongs to this user
      - matches_run:    intakes ever submitted by this user

    Email is null for signed-in users (the frontend sources it from Firebase
    auth state directly so it always matches the live Google account); only
    the guest fallback returns a literal placeholder.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        active_watches = await conn.fetchval(
            "SELECT count(*) FROM watches w "
            "JOIN bookings b ON b.id = w.booking_id "
            "WHERE w.active = TRUE AND b.user_id = $1",
            user_id,
        )
        matches_run = await conn.fetchval(
            "SELECT count(*) FROM match_intakes WHERE user_id = $1",
            user_id,
        )

    is_guest = _is_guest(user_id)
    return {
        "email": "guestuser@domain.com" if is_guest else None,
        "user_id": user_id,
        "is_guest": is_guest,
        "active_watches": int(active_watches or 0),
        "matches_run": int(matches_run or 0),
    }


@router.post("/merge-guest")
async def merge_guest(
    body: dict[str, Any] = Body(...),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int]:
    """Re-attribute a guest's intakes and bookings to the freshly signed-in user.

    Called once at sign-in by frontend/js/auth.js. Strict auth: a valid
    Bearer token is required (get_current_user_id raises 401 otherwise) so a
    guest can never claim another guest's data.

    SQL uses ``WITH … RETURNING 1`` to make the moved-row count available
    via fetchval — ``UPDATE … RETURNING count(*)`` is invalid in PostgreSQL
    because count() is an aggregate.
    """
    if user_id is None or _is_guest(user_id):
        # No bearer token, or somehow resolved to guest — nothing to merge.
        return {"merged_bookings": 0, "merged_intakes": 0}

    guest_id = body.get("guest_id")
    if not isinstance(guest_id, str) or not guest_id.startswith("guest-"):
        return {"merged_bookings": 0, "merged_intakes": 0}

    pool = get_pool()
    async with pool.acquire() as conn:
        # asyncpg's execute() returns the PostgreSQL command tag string —
        # for UPDATE that's "UPDATE <rowcount>". Splitting on whitespace and
        # taking the last token gives the affected-row count without needing
        # a CTE/RETURNING workaround.
        result_b = await conn.execute(
            "UPDATE bookings SET user_id = $1 WHERE user_id = $2",
            user_id,
            guest_id,
        )
        merged_bookings = int(result_b.split()[-1])

        result_i = await conn.execute(
            "UPDATE match_intakes SET user_id = $1 WHERE user_id = $2",
            user_id,
            guest_id,
        )
        merged_intakes = int(result_i.split()[-1])

    logger.info(
        "merge_guest: user=%s guest=%s bookings=%s intakes=%s",
        user_id,
        guest_id,
        merged_bookings,
        merged_intakes,
    )
    return {
        "merged_bookings": merged_bookings,
        "merged_intakes": merged_intakes,
    }
