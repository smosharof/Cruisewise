"""
Populates the sailings table from Apify cruise line scrapers.

Run once manually to seed, or scheduled via Cloud Scheduler for periodic refresh.
Each scraper is called in parallel via asyncio.gather.
Results are normalized to the sailings table schema and upserted.

Usage:
    uv run python -m backend.workers.inventory_refresh

    # Or with explicit token for local testing:
    APIFY_API_TOKEN=apify_api_... uv run python -m backend.workers.inventory_refresh
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Any

import asyncpg

from backend.config import get_settings
from backend.tools.apify_client import run_actor

logger = logging.getLogger(__name__)


# Each entry: actor_id, canonical cruise_line we use everywhere, and the input
# blob the actor expects. Norwegian and Princess slugs are uncertain — if Apify
# returns 404, run_actor logs a warning and returns []. No code change needed.
SCRAPER_CONFIGS: list[dict[str, Any]] = [
    {
        "actor_id": "sercul/royal-caribbean",
        "cruise_line": "Royal Caribbean",
        "input": {"market": "en_US", "maxItems": 500},
    },
    {
        "actor_id": "sercul/carnival-cruises",
        "cruise_line": "Carnival",
        "input": {"region": "en_US", "maxRows": 500},
    },
    {
        "actor_id": "sercul/celebrity-cruises",
        "cruise_line": "Celebrity",
        "input": {"market": "en_US", "maxItems": 500},
    },
    {
        "actor_id": "sercul/hal-cruises-scraper",
        "cruise_line": "Holland America",
        "input": {"market": "en_US", "maxItems": 500},
    },
    {
        "actor_id": "sercul/msc-cruises-scraper",
        "cruise_line": "MSC",
        "input": {"market": "en_US", "maxItems": 500},
    },
    {
        "actor_id": "sercul/disney-cruises-scraper",
        "cruise_line": "Disney Cruise Line",
        "input": {"market": "en_US", "maxItems": 500},
    },
    {
        "actor_id": "sercul/norwegian-cruise-scraper",
        "cruise_line": "Norwegian",
        # NCL's actor uses `region` and `maxRows` (not `market` / `maxItems`);
        # without `region` it defaults to ncl-it_IT and returns EUR prices.
        # Verified valid region values include en_US, en_GB, de_DE, nl_NL, it_IT.
        "input": {"region": "en_US", "maxRows": 500},
        "suffix": "us",
    },
    # Norwegian — UK market (GBP, European itineraries)
    {
        "actor_id": "sercul/norwegian-cruise-scraper",
        "cruise_line": "Norwegian",
        "input": {"region": "en_GB", "maxRows": 300},
        "suffix": "gb",
    },
    {
        "actor_id": "sercul/princess-cruise-scraper",
        "cruise_line": "Princess",
        "input": {"market": "en_US", "maxItems": 500},
    },
    # International market variants — same actors, different locale → GBP/AUD
    # prices and European/Asia-Pacific itineraries.
    {
        "actor_id": "sercul/royal-caribbean",
        "cruise_line": "Royal Caribbean",
        "input": {"market": "en_GB", "maxItems": 200},
    },
    {
        "actor_id": "sercul/celebrity-cruises",
        "cruise_line": "Celebrity",
        "input": {"market": "en_GB", "maxItems": 200},
    },
    {
        "actor_id": "sercul/msc-cruises-scraper",
        "cruise_line": "MSC",
        "input": {"market": "en_GB", "maxItems": 200},
    },
    {
        "actor_id": "sercul/hal-cruises-scraper",
        "cruise_line": "Holland America",
        "input": {"market": "en_AU", "maxItems": 200},
    },
]


def _slugify(name: str) -> str:
    """Lowercase, replace spaces with hyphens, strip non-alphanumeric except hyphens."""
    return re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))


def _get(raw: dict, *keys: str, default: Any = None) -> Any:
    """Return the first non-None value among the given keys.

    Apify scrapers vary in field names between cruise lines. Carnival uses
    'departurePort.name' (literal dot in key); other actors may flatten to
    'departure_port' or nest under 'departurePort'. This helper tries each
    variant in order so the normalizer is forgiving.
    """
    for k in keys:
        if k in raw and raw[k] is not None:
            return raw[k]
        # Fallback: dotted key used as a path, e.g. "departurePort.name"
        if "." in k:
            head, tail = k.split(".", 1)
            sub = raw.get(head)
            if isinstance(sub, dict):
                inner = _get(sub, tail, default=None)
                if inner is not None:
                    return inner
    return default


def _coerce_date(value: Any) -> date | None:
    """Accept ISO string (with or without time), datetime, or date."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _coerce_int_price(value: Any) -> int | None:
    """Accept int, float, or numeric string. Return None if not parseable."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _clean_ship_name(name: str) -> str:
    """Fix known upstream actor name mangling.

    NCL's actor returns 'Norwegian Pride_amer' instead of 'Norwegian Pride of
    America' (an underscore truncation in their source HTML). Add new entries
    here as we encounter more actor-side mangling.
    """
    replacements = {
        "Pride_amer": "Pride of America",
        "pride_amer": "Pride of America",
    }
    for mangled, clean in replacements.items():
        if mangled in name:
            return name.replace(mangled, clean)
    return name


def normalize_sailing(
    raw: dict, cruise_line: str, market_suffix: str | None = None
) -> dict | None:
    """Map a raw Apify record to our DB row shape.

    Returns None for any record that fails validation (missing required fields,
    price <= 0). Logs a warning and skips — never raises.

    `market_suffix` (optional) is appended to the id slug so the same cruiseId
    scraped from different market locales (us / gb / au / de) doesn't collide
    on the primary key. When omitted, the id reverts to the legacy
    `{slug}-{cruiseId}` form.

    Required fields after normalization: id, ship_name, departure_port,
    departure_date, duration_nights, itinerary_summary, starting_price_usd,
    booking_url. Also cruise_line, platform, currency — filled here.
    """
    cruise_id = _get(raw, "cruiseId", "cruise_id", "id")
    if not cruise_id:
        logger.warning("normalize_sailing: missing cruiseId, skipping")
        return None

    ship_name = _get(raw, "shipName", "ship_name", "ship")
    if isinstance(ship_name, str):
        ship_name = _clean_ship_name(ship_name)
    departure_port = _get(
        raw,
        "departurePort.name",
        "departure_port",
        "departurePort",
        "embarkationPort",
    )
    if isinstance(departure_port, dict):
        departure_port = departure_port.get("name") or departure_port.get("code")

    departure_date = _coerce_date(
        _get(raw, "departureDate", "departure_date", "sailDate")
    )
    return_date = _coerce_date(
        _get(raw, "returnDate", "return_date", "disembarkationDate")
    )

    duration = _get(raw, "duration", "duration_nights", "nights")
    try:
        duration_nights = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_nights = None

    itinerary_summary = _get(raw, "title", "itinerary_summary", "name", "cruiseTitle")

    destination_names = _get(raw, "destinationNames", "destinations", "ports", default=[])
    if not isinstance(destination_names, list):
        destination_names = []

    starting_price_usd = _coerce_int_price(
        _get(raw, "price.amount", "startingPrice", "starting_price_usd", "price")
    )

    # Currency uses the same dot-notation pattern Apify uses for prices.
    # Default to USD when the actor doesn't expose currency (most US-market
    # actors don't include it; international markets always do).
    currency = _get(raw, "price.currency", "currency", default="USD")
    if not isinstance(currency, str) or not currency:
        currency = "USD"
    currency = currency.upper()

    booking_url = _get(raw, "source_url", "url", "bookingUrl", "booking_url")
    platform = _get(raw, "platform", default=cruise_line.lower())

    # Some actors (Norwegian, possibly others) don't expose a booking URL on
    # the listing record. Synthesize a placeholder so the row passes the
    # NOT NULL constraint and the affiliate handoff still has something
    # addressable to render. Real URLs replace this on next refresh if the
    # actor adds the field.
    if not booking_url:
        booking_url = (
            f"https://partner.example.com/book"
            f"?line={_slugify(cruise_line)}&sailing={cruise_id}&ref=cruisewise"
        )

    # Hard validation — every required field must be present and sane
    missing = [
        name for name, value in [
            ("ship_name", ship_name),
            ("departure_port", departure_port),
            ("departure_date", departure_date),
            ("duration_nights", duration_nights),
            ("itinerary_summary", itinerary_summary),
            ("starting_price_usd", starting_price_usd),
            ("booking_url", booking_url),
        ]
        if not value
    ]
    if missing:
        logger.warning(
            "normalize_sailing[%s/%s]: missing %s, skipping",
            cruise_line,
            cruise_id,
            ",".join(missing),
        )
        return None

    if starting_price_usd <= 0:
        logger.warning(
            "normalize_sailing[%s/%s]: non-positive price %s, skipping",
            cruise_line,
            cruise_id,
            starting_price_usd,
        )
        return None

    sailing_id = f"{_slugify(cruise_line)}-{cruise_id}"
    if market_suffix:
        sailing_id = f"{sailing_id}-{market_suffix}"

    return {
        "id": sailing_id,
        "cruise_line": cruise_line,
        "ship_name": ship_name,
        "departure_port": departure_port,
        "departure_date": departure_date,
        "return_date": return_date,
        "duration_nights": duration_nights,
        "itinerary_summary": itinerary_summary,
        "destination_names": destination_names,
        "starting_price_usd": starting_price_usd,
        "currency": currency,
        "booking_url": booking_url,
        "platform": platform,
    }


async def upsert_sailings(pool: asyncpg.Pool, records: list[dict]) -> int:
    """Insert or update sailings. Returns count of upserted rows."""
    if not records:
        return 0

    rows = [
        (
            r["id"],
            r["cruise_line"],
            r["ship_name"],
            r["departure_port"],
            r["departure_date"],
            r["return_date"],
            r["duration_nights"],
            r["itinerary_summary"],
            json.dumps(r["destination_names"]),
            r["starting_price_usd"],
            r.get("currency", "USD"),
            r["booking_url"],
            r["platform"],
        )
        for r in records
    ]

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO sailings (
                id, cruise_line, ship_name, departure_port, departure_date,
                return_date, duration_nights, itinerary_summary, destination_names,
                starting_price_usd, currency, booking_url, platform, scraped_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,NOW())
            ON CONFLICT (id) DO UPDATE SET
                starting_price_usd = EXCLUDED.starting_price_usd,
                currency = EXCLUDED.currency,
                booking_url = EXCLUDED.booking_url,
                scraped_at = NOW()
            """,
            rows,
        )
    return len(records)


def _market_suffix_from_input(input_data: dict) -> str | None:
    """Extract a short market suffix ('us', 'gb', 'au', 'de') from actor input.

    Looks at common keys (`market`, `region`) for an `xx_YY` locale and uses
    the trailing region. Returns None if nothing matches, so unmarked configs
    keep their legacy id form.
    """
    for key in ("market", "region"):
        val = input_data.get(key)
        if isinstance(val, str) and "_" in val:
            return val.split("_", 1)[1].lower()
    return None


async def _run_one(
    config: dict, api_token: str, pool: asyncpg.Pool
) -> tuple[str, int, list[str]]:
    """Run a single scraper end-to-end. Returns (actor_id, count, errors)."""
    actor_id = config["actor_id"]
    cruise_line = config["cruise_line"]
    market_suffix = _market_suffix_from_input(config["input"])
    errors: list[str] = []

    raw_results = await run_actor(actor_id, config["input"], api_token)
    if not raw_results:
        return actor_id, 0, errors

    normalized: list[dict] = []
    for raw in raw_results:
        n = normalize_sailing(raw, cruise_line, market_suffix)
        if n is not None:
            normalized.append(n)

    if not normalized:
        errors.append(f"{actor_id}: 0 records survived normalization")
        return actor_id, 0, errors

    try:
        count = await upsert_sailings(pool, normalized)
    except Exception as exc:
        errors.append(f"{actor_id}: upsert failed: {exc}")
        return actor_id, 0, errors

    return actor_id, count, errors


async def run_refresh(pool: asyncpg.Pool | None = None) -> dict:
    """Run all scrapers in parallel and upsert results.

    Returns summary: {actor_id: count, ..., "total": N, "errors": [...]}
    A single scraper failure does not abort the others — gather collects
    exceptions per task.
    """
    settings = get_settings()
    api_token = settings.apify_api_token
    if not api_token:
        logger.warning("run_refresh: APIFY_API_TOKEN not set, no scrapers will run")
        return {"total": 0, "errors": ["APIFY_API_TOKEN not set"]}

    if pool is None:
        pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=4)
        owns_pool = True
    else:
        owns_pool = False

    try:
        results = await asyncio.gather(
            *[_run_one(c, api_token, pool) for c in SCRAPER_CONFIGS],
            return_exceptions=True,
        )
    finally:
        if owns_pool:
            await pool.close()

    summary: dict = {"total": 0, "errors": []}
    for r in results:
        if isinstance(r, BaseException):
            summary["errors"].append(f"unhandled exception: {r}")
            continue
        actor_id, count, errors = r
        summary[actor_id] = count
        summary["total"] += count
        summary["errors"].extend(errors)

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    summary = asyncio.run(run_refresh())
    print(json.dumps(summary, indent=2))
