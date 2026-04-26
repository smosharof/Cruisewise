from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from backend.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me")
async def get_me() -> dict[str, Any]:
    """Return the current user's account summary.

    Auth is not yet wired — email is hardcoded for the demo. Counts come from
    real DB tables: active watches and total match intakes ever submitted.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        active_watches = await conn.fetchval(
            "SELECT count(*) FROM watches WHERE active = TRUE"
        )
        matches_run = await conn.fetchval(
            "SELECT count(*) FROM match_intakes"
        )
    return {
        "email": "albert.einstein@netscape.com",
        "active_watches": int(active_watches or 0),
        "matches_run": int(matches_run or 0),
    }
