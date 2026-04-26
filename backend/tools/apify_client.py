"""
Thin wrapper around the Apify HTTP API for running cruise scrapers.

Each sercul/* actor takes an input JSON and returns a dataset of sailing records.
We call the synchronous run-and-get-dataset endpoint so we get results in one
HTTP call without polling.

Actor IDs (stable, from apify.com actor pages):
  Royal Caribbean:  sercul/royal-caribbean
  Carnival:         sercul/carnival-cruises
  Celebrity:        sercul/celebrity-cruises
  Holland America:  sercul/hal-cruises-scraper
  MSC:              sercul/msc-cruises-scraper
  Disney:           sercul/disney-cruises-scraper
  Norwegian:        sercul/norwegian-cruise-scraper
  Princess:         sercul/princess-cruise-scraper
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Apify expects "user~actor" in the URL path; some clients allow "user/actor"
# and apify normalises it. We accept either input form and convert.
_APIFY_BASE = "https://api.apify.com/v2"


def _normalise_actor_id(actor_id: str) -> str:
    """Apify URL paths use 'user~actor', not 'user/actor'."""
    return actor_id.replace("/", "~")


async def run_actor(
    actor_id: str,
    input_data: dict,
    api_token: str,
    timeout_secs: int = 300,
) -> list[dict]:
    """Run an Apify actor synchronously and return the dataset items.

    Uses the run-sync-get-dataset-items endpoint:
    POST https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={token}

    Returns list of result dicts, or empty list on failure (logs the error).
    Never raises — a failed scraper should not take down the whole refresh.
    """
    if not api_token:
        logger.warning("run_actor[%s]: APIFY_API_TOKEN not set; skipping", actor_id)
        return []

    url = (
        f"{_APIFY_BASE}/acts/{_normalise_actor_id(actor_id)}"
        f"/run-sync-get-dataset-items"
    )
    params = {"token": api_token}

    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout_secs) as client:
            resp = await client.post(url, params=params, json=input_data)
    except httpx.TimeoutException:
        logger.warning(
            "run_actor[%s] timed out after %ss", actor_id, timeout_secs
        )
        return []
    except httpx.HTTPError as exc:
        logger.warning("run_actor[%s] HTTP error: %s", actor_id, exc)
        return []

    elapsed = time.time() - started

    if resp.status_code == 404:
        logger.warning(
            "run_actor[%s]: actor not found (404) — slug may be wrong; skipping",
            actor_id,
        )
        return []
    if resp.status_code >= 400:
        logger.warning(
            "run_actor[%s]: HTTP %d in %.1fs — body=%s",
            actor_id,
            resp.status_code,
            elapsed,
            resp.text[:200],
        )
        return []

    try:
        data = resp.json()
    except ValueError:
        logger.warning(
            "run_actor[%s]: non-JSON response (HTTP %d, %.1fs)",
            actor_id,
            resp.status_code,
            elapsed,
        )
        return []

    if not isinstance(data, list):
        logger.warning(
            "run_actor[%s]: expected list response, got %s",
            actor_id,
            type(data).__name__,
        )
        return []

    logger.info(
        "run_actor[%s]: %d items in %.1fs",
        actor_id,
        len(data),
        elapsed,
    )
    return data
