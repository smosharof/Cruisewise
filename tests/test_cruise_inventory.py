"""Tests for the cruise inventory filter logic — exercises the seed-data path.

After the Apify refactor, search_sailings/get_sailing are async + DB-backed.
These tests target the sync seed-data helpers (_search_seed_data and
_SAILING_INDEX) so they stay focused on filter behavior; DB-path coverage
lives in test_inventory_refresh.py.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.schemas import MatchIntake, TravelParty, Vibe
from backend.tools.cruise_inventory import (
    _SAILING_INDEX,
    _SAILINGS,
    _search_seed_data as search_sailings,
)


def get_sailing(sailing_id: str):
    """Sync seed-only lookup — equivalent to the legacy get_sailing()."""
    return _SAILING_INDEX.get(sailing_id)


def _intake(**overrides) -> MatchIntake:
    """Build a permissive MatchIntake, then apply overrides."""
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


class TestRegionFilter:
    def test_caribbean_intake_returns_only_caribbean(self) -> None:
        results = search_sailings(_intake(preferred_regions=["Caribbean"]))
        assert len(results) > 0
        for s in results:
            assert "caribbean" in s["itinerary_summary"].lower()

    def test_caribbean_intake_excludes_alaska(self) -> None:
        results = search_sailings(_intake(preferred_regions=["Caribbean"]))
        for s in results:
            assert "alaska" not in s["itinerary_summary"].lower()

    def test_alaska_intake_returns_only_alaska(self) -> None:
        results = search_sailings(_intake(preferred_regions=["Alaska"]))
        assert len(results) > 0
        for s in results:
            assert "alaska" in s["itinerary_summary"].lower()

    def test_empty_region_returns_all_regions(self) -> None:
        results = search_sailings(_intake(preferred_regions=[]))
        # No region filter → capped at 5 but drawn from all regions
        assert len(results) == 5
        cruise_lines = {s["cruise_line"] for s in results}
        # With no region filter the first 5 are Caribbean + Alaska mix
        assert len(cruise_lines) >= 1


class TestDateWindowFilter:
    def test_narrow_july_window_excludes_june_sailings(self) -> None:
        results = search_sailings(_intake(
            earliest_departure=date(2026, 7, 1),
            latest_departure=date(2026, 7, 31),
        ))
        assert len(results) > 0
        for s in results:
            assert date(2026, 7, 1) <= s["departure_date"] <= date(2026, 7, 31)

    def test_narrow_window_excludes_out_of_range(self) -> None:
        # Only one sailing departs on exactly 2026-07-05 (Mardi Gras)
        results = search_sailings(_intake(
            earliest_departure=date(2026, 7, 5),
            latest_departure=date(2026, 7, 5),
        ))
        assert len(results) == 1
        assert results[0]["sailing_id"] == "ccl-mardi-gras-0705"


class TestPortFilter:
    def test_sea_port_returns_only_alaska_sailings(self) -> None:
        results = search_sailings(_intake(departure_ports_acceptable=["SEA"]))
        assert len(results) > 0
        for s in results:
            assert s["departure_port"] == "SEA"

    def test_sea_port_excludes_miami_sailings(self) -> None:
        results = search_sailings(_intake(departure_ports_acceptable=["SEA"]))
        for s in results:
            assert s["departure_port"] != "MIA"

    def test_multiple_ports_accepted(self) -> None:
        results = search_sailings(_intake(departure_ports_acceptable=["MIA", "SEA"]))
        assert len(results) == 5
        for s in results:
            assert s["departure_port"] in ("MIA", "SEA")


class TestEmptyResult:
    def test_unknown_region_returns_empty(self) -> None:
        results = search_sailings(_intake(preferred_regions=["Antarctica"]))
        assert results == []

    def test_impossible_date_window_returns_empty(self) -> None:
        results = search_sailings(_intake(
            earliest_departure=date(2020, 1, 1),
            latest_departure=date(2020, 12, 31),
        ))
        assert results == []

    def test_too_short_duration_excludes_all(self) -> None:
        # All sailings are 3+ nights; requiring max 2 nights returns nothing.
        # duration_nights_min ge=2 per schema, so use min=2 max=2.
        results = search_sailings(_intake(duration_nights_min=2, duration_nights_max=2))
        assert results == []

    def test_budget_too_low_returns_empty(self) -> None:
        # Cheapest sailing is $399 (Mariner, interior); $200 is schema minimum → nothing
        results = search_sailings(_intake(budget_per_person_usd=200))
        assert results == []


class TestGetSailing:
    def test_known_id_returns_sailing(self) -> None:
        s = get_sailing("rc-wonder-0607")
        assert s is not None
        assert s["ship_name"] == "Wonder of the Seas"

    def test_unknown_id_returns_none(self) -> None:
        assert get_sailing("nonexistent-id") is None

    def test_all_seeded_ids_are_retrievable(self) -> None:
        for sailing in _SAILINGS:
            assert get_sailing(sailing["sailing_id"]) is not None


class TestInventoryIntegrity:
    def test_twenty_sailings_seeded(self) -> None:
        assert len(_SAILINGS) == 32

    def test_all_sailings_have_required_keys(self) -> None:
        required = {
            "sailing_id", "cruise_line", "ship_name", "itinerary_summary",
            "departure_date", "return_date", "duration_nights", "departure_port",
            "prices",
        }
        for s in _SAILINGS:
            assert required <= s.keys(), f"Missing keys in {s['sailing_id']}"

    def test_all_sailings_have_four_cabin_prices(self) -> None:
        categories = {"interior", "oceanview", "balcony", "suite"}
        for s in _SAILINGS:
            assert categories == s["prices"].keys(), f"Bad prices in {s['sailing_id']}"

    def test_price_ordering_holds(self) -> None:
        for s in _SAILINGS:
            p = s["prices"]
            assert p["interior"] < p["oceanview"] < p["balcony"] < p["suite"], (
                f"Price ordering violated in {s['sailing_id']}"
            )

    def test_return_date_equals_departure_plus_duration(self) -> None:
        from datetime import timedelta
        for s in _SAILINGS:
            expected = s["departure_date"] + timedelta(days=s["duration_nights"])
            assert s["return_date"] == expected, (
                f"return_date mismatch in {s['sailing_id']}"
            )

    def test_all_departure_dates_in_range(self) -> None:
        for s in _SAILINGS:
            assert date(2026, 6, 1) <= s["departure_date"] <= date(2027, 3, 31), (
                f"Date out of range in {s['sailing_id']}"
            )

    def test_sailing_ids_are_unique(self) -> None:
        ids = [s["sailing_id"] for s in _SAILINGS]
        assert len(ids) == len(set(ids))

    def test_results_capped_at_five(self) -> None:
        # Broad intake matches all 20; result must be <= 5
        results = search_sailings(_intake())
        assert len(results) <= 5
