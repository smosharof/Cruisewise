from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from backend.agents.match_agent import run_match
from backend.db import acquire
from backend.errors import NoSailingsFound
from backend.schemas import MatchIntake, MatchResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/intake", response_model=MatchResult, status_code=201)
async def post_intake(intake: MatchIntake) -> MatchResult:
    """Run a match for the submitted intake and return the full result.

    Synchronous: the caller waits for run_match to complete (~15-25s with the
    early-exit gather). The intake is persisted before the agent runs and the
    result is persisted after. Both go to JSONB columns; the cast to ::jsonb
    in SQL keeps asyncpg from trying to JSON-encode the already-serialised string.
    """
    intake_id = uuid.uuid4()
    intake_id_str = str(intake_id)
    now = datetime.now(tz=UTC)

    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO match_intakes (id, intake_json, created_at) VALUES ($1, $2::jsonb, $3)",
            intake_id,
            intake.model_dump_json(),
            now,
        )

    try:
        result = await run_match(intake, intake_id_str)
    except NoSailingsFound as exc:
        logger.warning("No sailings for intake %s: %s", intake_id_str, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("run_match failed for intake %s", intake_id_str)
        raise HTTPException(
            status_code=500,
            detail="Match agent failed unexpectedly. Please try again.",
        )

    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO match_results (intake_id, result_json, generated_at) "
            "VALUES ($1, $2::jsonb, $3)",
            intake_id,
            result.model_dump_json(),
            result.generated_at,
        )

    logger.info(
        "Match complete intake_id=%s candidates=%d top=%s",
        intake_id_str,
        len(result.ranked_candidates),
        result.ranked_candidates[0].sailing_id,
    )
    return result


@router.get("/results/{intake_id}", response_model=MatchResult)
async def get_results(intake_id: str) -> MatchResult:
    """Return the most recent MatchResult for an intake, or 404.

    There can be multiple results per intake (re-runs); we return the latest.
    """
    try:
        intake_uuid = uuid.UUID(intake_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Invalid intake id: {intake_id}"
        ) from exc

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT result_json FROM match_results "
            "WHERE intake_id = $1 ORDER BY generated_at DESC LIMIT 1",
            intake_uuid,
        )

    if row is None:
        raise HTTPException(status_code=404, detail=f"No results for intake {intake_id}")

    return MatchResult.model_validate_json(row["result_json"])
