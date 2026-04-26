"""Tests for the Apify inventory refresh path.

Covers normalize_sailing happy path + skip-on-missing, the seed fallback
behavior of search_sailings when the DB returns empty, and the vibe affinity
sort applied to DB-shaped rows. No live Apify calls — run_actor is mocked
where needed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.schemas import MatchIntake, TravelParty, Vibe
from backend.tools.cruise_inventory import _row_to_sailing_dict, search_sailings
from backend.workers.inventory_refresh import normalize_sailing


# ---------------------------------------------------------------------------
# Carnival sample — exact field shape we confirmed during the dry run
# ---------------------------------------------------------------------------

_CARNIVAL_SAMPLE = {
    "cruiseId": "VAL-7N-2026-09-06",
    "shipName": "Carnival Celebration",
    "departurePort.name": "Miami, FL",
    "departureDate": "2026-09-06T17:00:00",
    "duration": 7,
    "title": "Southern Caribbean from Miami",
    "destinationNames": ["Caribbean", "Aruba", "Curacao", "Bonaire"],
    "price.amount": "899.00",
    "source_url": "https://carnival.com/cruise/VAL-7N-2026-09-06",
    "platform": "carnival",
}


def _intake(**overrides) -> MatchIntake:
    defaults: dict = {
        "travel_party": TravelParty.COUPLE,
        "party_size": 2,
        "primary_vibe": Vibe.RELAXATION,
        "budget_per_person_usd": 10_000,
        "flexible_dates": True,
        "earliest_departure": date(2026, 1, 1),
        "latest_departure": date(2027, 12, 31),
        "duration_nights_min": 2,
        "duration_nights_max": 21,
        "preferred_regions": [],
        "departure_ports_acceptable": [],
        "cruise_experience_level": "first_timer",
    }
    defaults.update(overrides)
    return MatchIntake(**defaults)


def _make_pool(rows: list | None = None, raise_on_acquire: bool = False):
    """Build a MagicMock pool whose acquire() yields a connection.

    The connection's fetch() / fetchrow() returns the rows passed in.
    """
    pool = MagicMock()
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows if rows is not None else [])
    conn.fetchrow = AsyncMock(return_value=(rows[0] if rows else None))

    @asynccontextmanager
    async def _acquire():
        if raise_on_acquire:
            raise RuntimeError("pool unavailable")
        yield conn

    pool.acquire = _acquire
    return pool


# ---------------------------------------------------------------------------
# normalize_sailing
# ---------------------------------------------------------------------------


class TestNormalizeSailing:
    def test_carnival_sample_maps_all_required_fields(self) -> None:
        out = normalize_sailing(_CARNIVAL_SAMPLE, "Carnival")
        assert out is not None
        assert out["id"] == "carnival-VAL-7N-2026-09-06"
        assert out["cruise_line"] == "Carnival"
        assert out["ship_name"] == "Carnival Celebration"
        assert out["departure_port"] == "Miami, FL"
        assert out["departure_date"] == date(2026, 9, 6)
        assert out["return_date"] is None
        assert out["duration_nights"] == 7
        assert out["itinerary_summary"] == "Southern Caribbean from Miami"
        assert out["destination_names"] == ["Caribbean", "Aruba", "Curacao", "Bonaire"]
        assert out["starting_price_usd"] == 899
        assert out["booking_url"] == "https://carnival.com/cruise/VAL-7N-2026-09-06"
        assert out["platform"] == "carnival"

    def test_missing_cruise_id_returns_none(self) -> None:
        bad = {**_CARNIVAL_SAMPLE}
        bad.pop("cruiseId")
        assert normalize_sailing(bad, "Carnival") is None

    def test_non_positive_price_returns_none(self) -> None:
        bad = {**_CARNIVAL_SAMPLE, "price.amount": "0.00"}
        assert normalize_sailing(bad, "Carnival") is None

    def test_missing_ship_name_returns_none(self) -> None:
        bad = {**_CARNIVAL_SAMPLE}
        bad.pop("shipName")
        assert normalize_sailing(bad, "Carnival") is None

    def test_alternate_field_names_work(self) -> None:
        """Other actors may flatten fields differently — normalizer is tolerant."""
        alt = {
            "cruiseId": "RC-X-100",
            "shipName": "Wonder of the Seas",
            "departure_port": "Miami, FL",
            "departureDate": "2026-09-06",
            "duration": 7,
            "title": "Western Caribbean",
            "destinations": ["Caribbean"],
            "startingPrice": 1099,
            "booking_url": "https://example.com/x",
        }
        out = normalize_sailing(alt, "Royal Caribbean")
        assert out is not None
        assert out["id"] == "royal-caribbean-RC-X-100"
        assert out["starting_price_usd"] == 1099


# ---------------------------------------------------------------------------
# search_sailings — seed fallback behavior
# ---------------------------------------------------------------------------


class TestSearchSeedFallback:
    @pytest.mark.asyncio
    async def test_empty_db_falls_back_to_seed_data(self) -> None:
        pool = _make_pool(rows=[])
        results = await search_sailings(_intake(preferred_regions=["Caribbean"]), pool)
        assert len(results) > 0
        for s in results:
            assert "caribbean" in s["itinerary_summary"].lower()

    @pytest.mark.asyncio
    async def test_db_error_falls_back_to_seed_data(self) -> None:
        pool = _make_pool(raise_on_acquire=True)
        results = await search_sailings(_intake(preferred_regions=["Caribbean"]), pool)
        # Fallback fired — got real seed-data results, not an exception
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Vibe affinity sort against DB-shaped rows
# ---------------------------------------------------------------------------


class TestVibeAffinityOnDbRows:
    @pytest.mark.asyncio
    async def test_luxury_intake_surfaces_regent_first(self) -> None:
        """DB returns rows from multiple lines; Regent should rank highest for luxury."""
        # Build records mirroring the sailings table row shape
        db_rows = [
            {
                "id": "carnival-CCL-1",
                "cruise_line": "Carnival",
                "ship_name": "Carnival Celebration",
                "departure_port": "MIA",
                "departure_date": date(2026, 9, 6),
                "return_date": date(2026, 9, 13),
                "duration_nights": 7,
                "itinerary_summary": "Southern Caribbean",
                "destination_names": ["Caribbean"],
                "starting_price_usd": 899,
                "booking_url": "https://example.com/ccl-1",
                "platform": "carnival",
            },
            {
                "id": "regent-RSSC-1",
                "cruise_line": "Regent Seven Seas",
                "ship_name": "Seven Seas Explorer",
                "departure_port": "MIA",
                "departure_date": date(2026, 10, 15),
                "return_date": date(2026, 10, 22),
                "duration_nights": 7,
                "itinerary_summary": "Caribbean Luxury",
                "destination_names": ["Caribbean"],
                "starting_price_usd": 6499,
                "booking_url": "https://example.com/rssc-1",
                "platform": "regent",
            },
        ]
        pool = _make_pool(rows=db_rows)
        results = await search_sailings(_intake(primary_vibe=Vibe.LUXURY), pool)

        assert len(results) == 2
        assert results[0]["cruise_line"] == "Regent Seven Seas"
        assert results[1]["cruise_line"] == "Carnival"

    def test_row_to_sailing_dict_synthesizes_prices(self) -> None:
        """ship_researcher's _select_cabin needs a 4-key prices dict; verify it."""
        row = {
            "id": "x",
            "cruise_line": "Carnival",
            "ship_name": "Test",
            "departure_port": "MIA",
            "departure_date": date(2026, 9, 6),
            "return_date": None,
            "duration_nights": 7,
            "itinerary_summary": "Test itinerary",
            "destination_names": ["Caribbean"],
            "starting_price_usd": 1000,
            "booking_url": "https://example.com/x",
            "platform": "test",
        }
        out = _row_to_sailing_dict(row)
        assert set(out["prices"].keys()) == {"interior", "oceanview", "balcony", "suite"}
        assert out["prices"]["interior"] == 1000
        # Multipliers ascend, so each tier must be >= the previous
        assert out["prices"]["interior"] <= out["prices"]["oceanview"]
        assert out["prices"]["oceanview"] <= out["prices"]["balcony"]
        assert out["prices"]["balcony"] <= out["prices"]["suite"]
        assert out["sailing_id"] == "x"
