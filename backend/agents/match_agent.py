"""
Match orchestrator — routes a MatchIntake through candidate retrieval, parallel
ship research, and final memo synthesis, then returns a ranked MatchResult.

Flow:
  1. cruise_inventory.search_sailings(intake) → list[dict] candidates
  2. asyncio.gather(*[_safe_research(s, intake) for s in candidates])
  3. Filter None (timeout/error survivors), sort by vibe_score desc
  4. synthesize_memo(intake, ranked) → top_pick_reasoning + counter_memo
  5. Return MatchResult

Every sub-agent call is bounded by a wall-clock timeout (Vertex AI calls have
been observed to hang) so one slow ship_researcher cannot stall the whole flow.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from backend.agents.subagents.ship_researcher import research_ship
from backend.agents.subagents.synthesizer import synthesize_memo
from backend.db import get_pool
from backend.errors import NoSailingsFound
from backend.schemas import MatchIntake, MatchResult, ShipAssessment
from backend.tools.cruise_inventory import search_sailings

logger = logging.getLogger(__name__)

_PER_SUBAGENT_TIMEOUT_S = 60.0
_GATHER_TIMEOUT_S = 60.0
_MIN_RESULTS_FOR_EARLY_EXIT = 3


async def _safe_research(sailing: dict, intake: MatchIntake) -> ShipAssessment | None:
    """Wrap research_ship with a wall-clock timeout and exception swallow.

    Returns None on timeout or failure so the gather doesn't blow up the
    whole fan-out for one bad sub-agent. Caller filters None values.
    """
    try:
        return await asyncio.wait_for(
            research_ship(sailing, intake),
            timeout=_PER_SUBAGENT_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Timeout for sailing %s (>%ss)",
            sailing["sailing_id"],
            _PER_SUBAGENT_TIMEOUT_S,
        )
        return None
    except asyncio.CancelledError:
        # Expected when _gather_with_early_exit cancels in-flight tasks.
        raise
    except Exception as exc:
        logger.warning("Failed for sailing %s: %s", sailing["sailing_id"], exc)
        return None


async def _gather_with_early_exit(
    sailings: list[dict],
    intake: MatchIntake,
    min_results: int = _MIN_RESULTS_FOR_EARLY_EXIT,
    timeout: float = _GATHER_TIMEOUT_S,
) -> list[ShipAssessment]:
    """Fan out _safe_research and return as soon as min_results survivors land.

    Cancels in-flight tasks once the threshold is hit so the orchestrator
    isn't gated on the slowest sub-agent. If the outer timeout fires, returns
    whatever survivors we already have rather than raising.
    """
    tasks = [asyncio.create_task(_safe_research(s, intake)) for s in sailings]
    survivors: list[ShipAssessment] = []
    try:
        async with asyncio.timeout(timeout):
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result is not None:
                    survivors.append(result)
                if len(survivors) >= min_results:
                    break
    except TimeoutError:
        logger.warning(
            "Gather timed out after %ss with %d/%d survivors",
            timeout,
            len(survivors),
            len(sailings),
        )
    finally:
        for t in tasks:
            t.cancel()
    return survivors


async def run_match(intake: MatchIntake, intake_id: str) -> MatchResult:
    """Orchestrate the full Match flow for one intake."""
    # 1. Retrieve candidates from inventory (DB-backed; falls back to seed data
    # when the sailings table is empty)
    pool = get_pool()
    candidates = await search_sailings(intake, pool)
    if not candidates:
        raise NoSailingsFound(
            f"No sailings matched intake {intake_id} "
            f"(regions={intake.preferred_regions}, ports={intake.departure_ports_acceptable})"
        )
    logger.info("run_match %s: %d candidates from inventory", intake_id, len(candidates))

    # 2. Fan out to ship_researcher in parallel, exiting early once we have enough
    survivors = await _gather_with_early_exit(candidates, intake)

    # 3. Validate we have at least one survivor
    if not survivors:
        raise NoSailingsFound(
            f"All ship_researcher calls failed or timed out for intake {intake_id}"
        )
    logger.info(
        "run_match %s: %d/%d sub-agents survived",
        intake_id,
        len(survivors),
        len(candidates),
    )

    # 4. Sort by vibe_score desc, with cheaper cabin as tie-breaker.
    # The double-negation works because reverse=True flips both: we want
    # vibe_score DESC (high first) and cabin_price_usd ASC (low first).
    ranked = sorted(
        survivors,
        key=lambda a: (a.vibe_score, -a.cabin_price_usd),
        reverse=True,
    )

    # 5. Synthesize the comparison memo from the top candidates
    memo = await synthesize_memo(intake, ranked)

    # TODO: add iterative refinement loop (re-run synthesis if vibe_score spread
    # is too narrow or top_pick lacks differentiation). refinement_iterations=1
    # is the single-pass baseline; the loop will increment this.
    return MatchResult(
        intake_id=intake_id,
        generated_at=datetime.now(tz=UTC),
        ranked_candidates=ranked,
        top_pick_reasoning=memo.top_pick_reasoning,
        counter_memo=memo.counter_memo,
        gaps_identified=[],
        refinement_iterations=1,
    )
