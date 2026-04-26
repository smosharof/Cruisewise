"""
Mock cruise inventory — 20 seeded sailings, pure in-memory search.

Production will replace _SAILINGS with a live API call. The two public
functions keep the same signatures so nothing else needs to change.

Each sailing dict schema:
  sailing_id       str
  cruise_line      str
  ship_name        str
  itinerary_summary str   — region name appears here; used for region filtering
  departure_date   date
  return_date      date
  duration_nights  int
  departure_port   str    — IATA airport / port code
  prices           dict[str, int]  — keyed by CabinCategory value, per-person USD
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import date, timedelta

from backend.schemas import MatchIntake

logger = logging.getLogger(__name__)

_SAILINGS: list[dict] = [
    # -------------------------------------------------------------------------
    # Caribbean (8 sailings)
    # -------------------------------------------------------------------------
    {
        "sailing_id": "rc-wonder-0607",
        "cruise_line": "Royal Caribbean",
        "ship_name": "Wonder of the Seas",
        "itinerary_summary": "Western Caribbean: Labadee, Falmouth, Cozumel, Perfect Day at CocoCay",
        "departure_date": date(2026, 6, 7),
        "return_date": date(2026, 6, 14),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 1099, "oceanview": 1399, "balcony": 1899, "suite": 4499},
    },
    {
        "sailing_id": "rc-icon-0712",
        "cruise_line": "Royal Caribbean",
        "ship_name": "Icon of the Seas",
        "itinerary_summary": "Eastern Caribbean: St. Maarten, San Juan, Perfect Day at CocoCay",
        "departure_date": date(2026, 7, 12),
        "return_date": date(2026, 7, 19),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 1349, "oceanview": 1649, "balcony": 2299, "suite": 5999},
    },
    {
        "sailing_id": "ccl-mardi-gras-0705",
        "cruise_line": "Carnival",
        "ship_name": "Mardi Gras",
        "itinerary_summary": "Western Caribbean: Cozumel, Mahogany Bay, Belize City",
        "departure_date": date(2026, 7, 5),
        "return_date": date(2026, 7, 12),
        "duration_nights": 7,
        "departure_port": "MCO",
        "prices": {"interior": 849, "oceanview": 1149, "balcony": 1699, "suite": 3899},
    },
    {
        "sailing_id": "ccl-celebration-0906",
        "cruise_line": "Carnival",
        "ship_name": "Carnival Celebration",
        "itinerary_summary": "Southern Caribbean: Aruba, Curaçao, Bonaire",
        "departure_date": date(2026, 9, 6),
        "return_date": date(2026, 9, 13),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 899, "oceanview": 1199, "balcony": 1749, "suite": 4099},
    },
    {
        "sailing_id": "ncl-prima-0802",
        "cruise_line": "Norwegian",
        "ship_name": "Norwegian Prima",
        "itinerary_summary": "Eastern Caribbean: St. Thomas, St. Kitts, Antigua",
        "departure_date": date(2026, 8, 2),
        "return_date": date(2026, 8, 9),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 1199, "oceanview": 1499, "balcony": 2099, "suite": 4999},
    },
    {
        "sailing_id": "ncl-encore-1101",
        "cruise_line": "Norwegian",
        "ship_name": "Norwegian Encore",
        "itinerary_summary": "Western Caribbean: Cozumel, Roatán, Costa Maya",
        "departure_date": date(2026, 11, 1),
        "return_date": date(2026, 11, 8),
        "duration_nights": 7,
        "departure_port": "MCO",
        "prices": {"interior": 999, "oceanview": 1299, "balcony": 1849, "suite": 4299},
    },
    {
        "sailing_id": "msc-seashore-0913",
        "cruise_line": "MSC",
        "ship_name": "MSC Seashore",
        "itinerary_summary": "Caribbean: Ocean Cay MSC Marine Reserve, Nassau, Nassau",
        "departure_date": date(2026, 9, 13),
        "return_date": date(2026, 9, 20),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 849, "oceanview": 1099, "balcony": 1599, "suite": 3699},
    },
    {
        "sailing_id": "msc-seascape-0208",
        "cruise_line": "MSC",
        "ship_name": "MSC Seascape",
        "itinerary_summary": "Eastern Caribbean: St. Maarten, Puerto Rico, Dominican Republic",
        "departure_date": date(2027, 2, 8),
        "return_date": date(2027, 2, 15),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 879, "oceanview": 1149, "balcony": 1649, "suite": 3799},
    },
    {
        "sailing_id": "ncl-getaway-1018",
        "cruise_line": "Norwegian",
        "ship_name": "Norwegian Getaway",
        "itinerary_summary": "Eastern Caribbean: Tortola, St. Thomas, Nassau",
        "departure_date": date(2026, 10, 18),
        "return_date": date(2026, 10, 25),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 949, "oceanview": 1249, "balcony": 1799, "suite": 4199},
    },
    {
        "sailing_id": "celebrity-equinox-1004",
        "cruise_line": "Celebrity",
        "ship_name": "Celebrity Equinox",
        "itinerary_summary": "Southern Caribbean: Aruba, Curaçao, Grand Cayman",
        "departure_date": date(2026, 10, 4),
        "return_date": date(2026, 10, 14),
        "duration_nights": 10,
        "departure_port": "FLL",
        "prices": {"interior": 1199, "oceanview": 1499, "balcony": 2199, "suite": 5299},
    },
    {
        "sailing_id": "princess-caribbean-1115",
        "cruise_line": "Princess",
        "ship_name": "Caribbean Princess",
        "itinerary_summary": "Western Caribbean: Cozumel, Grand Cayman, Roatán, Princess Cays",
        "departure_date": date(2026, 11, 15),
        "return_date": date(2026, 11, 22),
        "duration_nights": 7,
        "departure_port": "FLL",
        "prices": {"interior": 1049, "oceanview": 1349, "balcony": 1899, "suite": 4499},
    },
    {
        "sailing_id": "viking-venus-1105",
        "cruise_line": "Viking Ocean",
        "ship_name": "Viking Venus",
        "itinerary_summary": "Caribbean Passage: Fort Lauderdale, St. Barts, Barbados, Grenada, Bonaire, Aruba",
        "departure_date": date(2026, 11, 5),
        "return_date": date(2026, 11, 15),
        "duration_nights": 10,
        "departure_port": "FLL",
        "prices": {"interior": 3999, "oceanview": 4799, "balcony": 5999, "suite": 9999},
    },
    {
        "sailing_id": "dcl-wish-0711",
        "cruise_line": "Disney Cruise Line",
        "ship_name": "Disney Wish",
        "itinerary_summary": "Eastern Caribbean Magic: Nassau, Castaway Cay (Disney's private island), St. Thomas, St. Maarten",
        "departure_date": date(2026, 7, 11),
        "return_date": date(2026, 7, 18),
        "duration_nights": 7,
        "departure_port": "MCO",
        "prices": {"interior": 2499, "oceanview": 3199, "balcony": 4299, "suite": 9499},
    },
    {
        "sailing_id": "dcl-fantasy-0905",
        "cruise_line": "Disney Cruise Line",
        "ship_name": "Disney Fantasy",
        "itinerary_summary": "Western Caribbean Adventure: Key West, Grand Cayman, Cozumel, Castaway Cay",
        "departure_date": date(2026, 9, 5),
        "return_date": date(2026, 9, 12),
        "duration_nights": 7,
        "departure_port": "MCO",
        "prices": {"interior": 2299, "oceanview": 2999, "balcony": 3999, "suite": 8999},
    },
    {
        "sailing_id": "rssc-explorer-1015",
        "cruise_line": "Regent Seven Seas",
        "ship_name": "Seven Seas Explorer",
        "itinerary_summary": "Caribbean Luxury: Miami, St. Barts, Barbados, St. Lucia, Antigua, St. Maarten",
        "departure_date": date(2026, 10, 15),
        "return_date": date(2026, 10, 22),
        "duration_nights": 7,
        "departure_port": "MIA",
        "prices": {"interior": 6499, "oceanview": 7999, "balcony": 9999, "suite": 16499},
    },
    # -------------------------------------------------------------------------
    # Alaska (5 sailings)
    # -------------------------------------------------------------------------
    {
        "sailing_id": "princess-majestic-0621",
        "cruise_line": "Princess",
        "ship_name": "Majestic Princess",
        "itinerary_summary": "Alaska: Inside Passage, Juneau, Skagway, Glacier Bay",
        "departure_date": date(2026, 6, 21),
        "return_date": date(2026, 6, 28),
        "duration_nights": 7,
        "departure_port": "SEA",
        "prices": {"interior": 1149, "oceanview": 1449, "balcony": 1999, "suite": 4699},
    },
    {
        "sailing_id": "princess-crown-0719",
        "cruise_line": "Princess",
        "ship_name": "Crown Princess",
        "itinerary_summary": "Alaska: Hubbard Glacier, Sitka, Ketchikan, Victoria BC",
        "departure_date": date(2026, 7, 19),
        "return_date": date(2026, 7, 29),
        "duration_nights": 10,
        "departure_port": "SEA",
        "prices": {"interior": 1399, "oceanview": 1749, "balcony": 2399, "suite": 5499},
    },
    {
        "sailing_id": "hal-koningsdam-0816",
        "cruise_line": "Holland America",
        "ship_name": "Koningsdam",
        "itinerary_summary": "Alaska: Glacier Bay, Juneau, Skagway, Sitka, Ketchikan",
        "departure_date": date(2026, 8, 16),
        "return_date": date(2026, 8, 23),
        "duration_nights": 7,
        "departure_port": "SEA",
        "prices": {"interior": 1249, "oceanview": 1549, "balcony": 2149, "suite": 5099},
    },
    {
        "sailing_id": "ncl-bliss-0920",
        "cruise_line": "Norwegian",
        "ship_name": "Norwegian Bliss",
        "itinerary_summary": "Alaska: Juneau, Skagway, Ketchikan, Icy Strait Point",
        "departure_date": date(2026, 9, 20),
        "return_date": date(2026, 9, 27),
        "duration_nights": 7,
        "departure_port": "SEA",
        "prices": {"interior": 1099, "oceanview": 1399, "balcony": 1949, "suite": 4599},
    },
    {
        "sailing_id": "rssc-mariner-0710",
        "cruise_line": "Regent Seven Seas",
        "ship_name": "Seven Seas Mariner",
        "itinerary_summary": "Alaskan Wilderness: Vancouver, Juneau, Skagway, Glacier Bay, Ketchikan, Victoria",
        "departure_date": date(2026, 7, 10),
        "return_date": date(2026, 7, 17),
        "duration_nights": 7,
        "departure_port": "YVR",
        "prices": {"interior": 5999, "oceanview": 7499, "balcony": 9499, "suite": 15999},
    },
    # -------------------------------------------------------------------------
    # Mediterranean (6 sailings)
    # -------------------------------------------------------------------------
    {
        "sailing_id": "msc-musica-0628",
        "cruise_line": "MSC",
        "ship_name": "MSC Musica",
        "itinerary_summary": "Western Mediterranean: Genoa, Marseille, Barcelona, Valencia, Rome",
        "departure_date": date(2026, 6, 28),
        "return_date": date(2026, 7, 5),
        "duration_nights": 7,
        "departure_port": "BCN",
        "prices": {"interior": 999, "oceanview": 1299, "balcony": 1799, "suite": 4199},
    },
    {
        "sailing_id": "celebrity-beyond-0726",
        "cruise_line": "Celebrity",
        "ship_name": "Celebrity Beyond",
        "itinerary_summary": "Eastern Mediterranean: Athens, Santorini, Mykonos, Ephesus, Istanbul",
        "departure_date": date(2026, 7, 26),
        "return_date": date(2026, 8, 5),
        "duration_nights": 10,
        "departure_port": "ATH",
        "prices": {"interior": 1449, "oceanview": 1799, "balcony": 2599, "suite": 6299},
    },
    {
        "sailing_id": "celebrity-apex-0830",
        "cruise_line": "Celebrity",
        "ship_name": "Celebrity Apex",
        "itinerary_summary": "Greek Islands Mediterranean: Athens, Mykonos, Crete, Rhodes, Santorini",
        "departure_date": date(2026, 8, 30),
        "return_date": date(2026, 9, 6),
        "duration_nights": 7,
        "departure_port": "ATH",
        "prices": {"interior": 1299, "oceanview": 1649, "balcony": 2349, "suite": 5699},
    },
    {
        "sailing_id": "vv-scarlet-1011",
        "cruise_line": "Virgin Voyages",
        "ship_name": "Scarlet Lady",
        "itinerary_summary": "Mediterranean Grand Voyage: Barcelona, Marseille, Genoa, Rome, Palermo, Athens",
        "departure_date": date(2026, 10, 11),
        "return_date": date(2026, 10, 23),
        "duration_nights": 12,
        "departure_port": "BCN",
        "prices": {"interior": 1799, "oceanview": 2199, "balcony": 2799, "suite": 6999},
    },
    {
        "sailing_id": "viking-orion-0920",
        "cruise_line": "Viking Ocean",
        "ship_name": "Viking Orion",
        "itinerary_summary": "Empires of the Mediterranean: Barcelona, Marseille, Monte Carlo, Florence/Pisa, Rome (Civitavecchia)",
        "departure_date": date(2026, 9, 20),
        "return_date": date(2026, 9, 30),
        "duration_nights": 10,
        "departure_port": "BCN",
        "prices": {"interior": 4499, "oceanview": 5499, "balcony": 6999, "suite": 11999},
    },
    {
        "sailing_id": "rssc-grandeur-0901",
        "cruise_line": "Regent Seven Seas",
        "ship_name": "Seven Seas Grandeur",
        "itinerary_summary": "Mediterranean Splendor: Barcelona, Cannes, Portofino, Rome (Civitavecchia), Amalfi, Athens (Piraeus)",
        "departure_date": date(2026, 9, 1),
        "return_date": date(2026, 9, 11),
        "duration_nights": 10,
        "departure_port": "BCN",
        "prices": {"interior": 7999, "oceanview": 9499, "balcony": 11999, "suite": 18999},
    },
    # -------------------------------------------------------------------------
    # Northern Europe (3 sailings)
    # -------------------------------------------------------------------------
    {
        "sailing_id": "viking-jupiter-0704",
        "cruise_line": "Viking Ocean",
        "ship_name": "Viking Jupiter",
        "itinerary_summary": "Northern Europe: London, Amsterdam, Hamburg, Copenhagen, Oslo",
        "departure_date": date(2026, 7, 4),
        "return_date": date(2026, 7, 12),
        "duration_nights": 8,
        "departure_port": "LHR",
        "prices": {"interior": 1499, "oceanview": 1799, "balcony": 2499, "suite": 5999},
    },
    {
        "sailing_id": "viking-sky-0912",
        "cruise_line": "Viking Ocean",
        "ship_name": "Viking Sky",
        "itinerary_summary": "Northern Europe: Norwegian Fjords, Bergen, Flåm, Ålesund, Geiranger, Copenhagen",
        "departure_date": date(2026, 9, 12),
        "return_date": date(2026, 9, 26),
        "duration_nights": 14,
        "departure_port": "CPH",
        "prices": {"interior": 1999, "oceanview": 2399, "balcony": 3199, "suite": 7499},
    },
    {
        "sailing_id": "viking-jupiter-0815",
        "cruise_line": "Viking Ocean",
        "ship_name": "Viking Jupiter",
        "itinerary_summary": "Northern Europe — Norwegian Fjords & Baltic Capitals: Bergen, Flam, Copenhagen, Stockholm, Helsinki, Tallinn",
        "departure_date": date(2026, 8, 15),
        "return_date": date(2026, 8, 29),
        "duration_nights": 14,
        "departure_port": "BGO",
        "prices": {"interior": 4999, "oceanview": 5999, "balcony": 7499, "suite": 12999},
    },
    # -------------------------------------------------------------------------
    # Bahamas (3 sailings)
    # -------------------------------------------------------------------------
    {
        "sailing_id": "ccl-horizon-0605",
        "cruise_line": "Carnival",
        "ship_name": "Carnival Horizon",
        "itinerary_summary": "Bahamas: Nassau, Half Moon Cay",
        "departure_date": date(2026, 6, 5),
        "return_date": date(2026, 6, 9),
        "duration_nights": 4,
        "departure_port": "MIA",
        "prices": {"interior": 499, "oceanview": 649, "balcony": 899, "suite": 2199},
    },
    {
        "sailing_id": "rc-mariner-0612",
        "cruise_line": "Royal Caribbean",
        "ship_name": "Mariner of the Seas",
        "itinerary_summary": "Bahamas: Nassau, Perfect Day at CocoCay",
        "departure_date": date(2026, 6, 12),
        "return_date": date(2026, 6, 15),
        "duration_nights": 3,
        "departure_port": "MIA",
        "prices": {"interior": 399, "oceanview": 549, "balcony": 799, "suite": 1899},
    },
    {
        "sailing_id": "dcl-treasure-1121",
        "cruise_line": "Disney Cruise Line",
        "ship_name": "Disney Treasure",
        "itinerary_summary": "Bahamas — Bahamian Getaway: Nassau, Castaway Cay",
        "departure_date": date(2026, 11, 21),
        "return_date": date(2026, 11, 25),
        "duration_nights": 4,
        "departure_port": "MCO",
        "prices": {"interior": 1899, "oceanview": 2399, "balcony": 3199, "suite": 6999},
    },
]

_SAILING_INDEX: dict[str, dict] = {s["sailing_id"]: s for s in _SAILINGS}

# Public alias so external scripts and notebooks can read the seed list without
# crossing the underscore name-mangling line.
SAILINGS = _SAILINGS

# Public alias used by the DB-backed search_sailings as a fallback when the
# sailings table is empty (pre-first-refresh, or during local dev without
# a populated DB). Same content as _SAILINGS — DO NOT delete this list:
# it keeps the app functional before the first Apify refresh lands data.
LEGACY_SEED_DATA = _SAILINGS

_MAX_RESULTS = 5

# Maps IATA airport / port codes to city-name tokens that ILIKE-match the
# departure_port strings stored in the live sailings table. Apify scrapers
# store 'Miami, FL' / 'Fort Lauderdale' / 'Port Canaveral (Orlando), Florida'
# while users type three-letter codes. Each token is wrapped in % wildcards
# at query time, so 'Miami' matches 'Miami', 'Miami, FL', and 'Miami, Florida'.
_IATA_TO_PORT_TOKENS: dict[str, list[str]] = {
    "MIA": ["Miami"],
    "FLL": ["Fort Lauderdale"],
    "MCO": ["Port Canaveral", "Orlando"],
    "TPA": ["Tampa"],
    "GAL": ["Galveston"],
    "LAX": ["Long Beach", "Los Angeles"],
    "SFO": ["San Francisco"],
    "SEA": ["Seattle"],
    "YVR": ["Vancouver"],
    "SAN": ["San Diego"],
    # NYC area — three airports all map to the four NYC-region cruise terminals
    # (Manhattan, Brooklyn, Bayonne / Cape Liberty in NJ).
    "JFK": ["New York", "Manhattan", "Brooklyn", "Bayonne", "Cape Liberty"],
    "LGA": ["New York", "Manhattan", "Brooklyn", "Bayonne", "Cape Liberty"],
    "EWR": ["New York", "Manhattan", "Brooklyn", "Bayonne", "Cape Liberty", "Newark"],
    "NYC": ["New York", "Manhattan", "Brooklyn", "Bayonne", "Cape Liberty"],
    # Other commonly-missing US embarkation points
    "HNL": ["Honolulu", "Hawaii"],
    "ANC": ["Anchorage", "Seward", "Whittier"],
    "NOL": ["New Orleans"],
    "MSY": ["New Orleans"],
    "JAX": ["Jacksonville"],
    "BAL": ["Baltimore"],
    "PHL": ["Philadelphia"],
    "BOS": ["Boston"],
    "NFK": ["Norfolk"],
    "CHS": ["Charleston"],
    "BCN": ["Barcelona"],
    "FCO": ["Rome", "Civitavecchia"],
    "ATH": ["Athens", "Piraeus"],
    "CPH": ["Copenhagen"],
    "LHR": ["London", "Southampton"],
    "BGO": ["Bergen"],
    "SIN": ["Singapore"],
}

# Vibe affinity by cruise line — higher score = stronger match.
# Used to rank candidates after filtering so a luxury intake surfaces Regent /
# Viking Ocean ahead of cheaper Caribbean options that happen to be earlier in
# seed order. ship_researcher still produces the canonical per-sailing
# vibe_score later; this is a pre-LLM ranking heuristic for the candidate set.
VIBE_AFFINITY: dict[str, dict[str, float]] = {
    "relaxation": {
        "Princess": 0.9, "Holland America": 0.85, "Celebrity": 0.8,
        "Viking Ocean": 0.75, "Regent Seven Seas": 0.75,
        "MSC": 0.5, "Norwegian": 0.4, "Royal Caribbean": 0.35,
        "Carnival": 0.2, "Virgin Voyages": 0.4, "Disney Cruise Line": 0.3,
    },
    "luxury": {
        "Regent Seven Seas": 1.0, "Viking Ocean": 0.85, "Celebrity": 0.75,
        "Virgin Voyages": 0.7, "Princess": 0.55, "Holland America": 0.5,
        "MSC": 0.3, "Norwegian": 0.3, "Royal Caribbean": 0.25,
        "Carnival": 0.15, "Disney Cruise Line": 0.35,
    },
    "cultural": {
        "Viking Ocean": 1.0, "Regent Seven Seas": 0.8, "Holland America": 0.75,
        "Celebrity": 0.65, "Princess": 0.6, "MSC": 0.5,
        "Norwegian": 0.4, "Royal Caribbean": 0.3, "Carnival": 0.2,
        "Virgin Voyages": 0.3, "Disney Cruise Line": 0.25,
    },
    "family_fun": {
        "Disney Cruise Line": 1.0, "Royal Caribbean": 0.9, "Carnival": 0.8,
        "Norwegian": 0.7, "MSC": 0.65, "Princess": 0.45,
        "Holland America": 0.35, "Celebrity": 0.35,
        "Virgin Voyages": 0.1, "Viking Ocean": 0.1, "Regent Seven Seas": 0.2,
    },
    "party": {
        "Virgin Voyages": 0.95, "Carnival": 0.9, "Norwegian": 0.85,
        "Royal Caribbean": 0.75, "MSC": 0.65, "Celebrity": 0.45,
        "Princess": 0.3, "Holland America": 0.25, "Disney Cruise Line": 0.4,
        "Viking Ocean": 0.1, "Regent Seven Seas": 0.15,
    },
    "adventure": {
        "Viking Ocean": 0.8, "Norwegian": 0.75, "Holland America": 0.7,
        "Princess": 0.65, "Royal Caribbean": 0.6, "Celebrity": 0.55,
        "Regent Seven Seas": 0.6, "MSC": 0.45, "Carnival": 0.35,
        "Virgin Voyages": 0.4, "Disney Cruise Line": 0.3,
    },
}


def _matches_filters(sailing: dict, intake: MatchIntake) -> bool:
    """Hard filters: region, date window, duration window, port whitelist, budget.

    Region match: any preferred_region is a case-insensitive substring of
    itinerary_summary. If preferred_regions is empty, all regions qualify.
    Port match: departure_port must be in departure_ports_acceptable. Empty list
    means all ports qualify. Budget match: at least one cabin category must be
    within budget.
    """
    if intake.preferred_regions:
        summary_lower = sailing["itinerary_summary"].lower()
        if not any(r.lower() in summary_lower for r in intake.preferred_regions):
            return False

    if (
        sailing["departure_date"] < intake.earliest_departure
        or sailing["departure_date"] > intake.latest_departure
    ):
        return False

    if (
        sailing["duration_nights"] < intake.duration_nights_min
        or sailing["duration_nights"] > intake.duration_nights_max
    ):
        return False

    if intake.departure_ports_acceptable:
        if sailing["departure_port"] not in intake.departure_ports_acceptable:
            return False

    if not any(p <= intake.budget_per_person_usd for p in sailing["prices"].values()):
        return False

    return True


# Cabin-tier multipliers used to synthesize a 4-cabin price dict from the
# single starting_price_usd we get from Apify. Real cruise sites publish
# tier-specific prices, but our actors currently surface only the lead-in
# fare. Multipliers reflect typical industry markups; ship_researcher's
# _select_cabin still works against the synthesized dict unchanged.
_CABIN_MULTIPLIERS = {
    "interior": 1.0,
    "oceanview": 1.3,
    "balcony": 1.7,
    "suite": 3.5,
}


def _synthesize_prices(starting_price_usd: int) -> dict[str, int]:
    return {
        cat: round(starting_price_usd * mult)
        for cat, mult in _CABIN_MULTIPLIERS.items()
    }


def _compute_return_date(
    return_date: date | None,
    departure_date: date | None,
    duration_nights: int | None,
) -> date | None:
    """Backfill return_date from departure_date + duration_nights when null.

    Some Apify actors don't expose a return date; the column is nullable in
    the DB. Downstream agents serialize this with .isoformat(), which crashes
    on None. Compute a reasonable value here so every sailing dict that
    leaves cruise_inventory.py has a non-None return_date.
    """
    if return_date is not None:
        return return_date
    if departure_date is not None and duration_nights:
        return departure_date + timedelta(days=int(duration_nights))
    return None


def _row_to_sailing_dict(row) -> dict:
    """Convert a sailings table row to the dict shape downstream expects.

    Adds a synthesized prices dict and a sailing_id alias for backward compat
    with the seed-data shape.
    """
    raw_dest = row["destination_names"]
    if isinstance(raw_dest, str):
        try:
            destination_names = json.loads(raw_dest)
        except (TypeError, ValueError):
            destination_names = []
    else:
        destination_names = list(raw_dest or [])

    starting_price = int(row["starting_price_usd"])
    # asyncpg returns missing columns as None on legacy rows that pre-date the
    # currency migration; default to USD so downstream never sees None.
    currency = row["currency"] if "currency" in row.keys() and row["currency"] else "USD"

    duration_nights = int(row["duration_nights"])
    return {
        "sailing_id": row["id"],
        "id": row["id"],
        "cruise_line": row["cruise_line"],
        "ship_name": row["ship_name"],
        "departure_port": row["departure_port"],
        "departure_date": row["departure_date"],
        "return_date": _compute_return_date(
            row["return_date"], row["departure_date"], duration_nights
        ),
        "duration_nights": duration_nights,
        "itinerary_summary": urllib.parse.unquote(row["itinerary_summary"]),
        "destination_names": destination_names,
        "starting_price_usd": starting_price,
        "currency": currency,
        "prices": _synthesize_prices(starting_price),
        "booking_url": row["booking_url"],
        "platform": row["platform"],
    }


def _vibe_rank(matches: list[dict], primary_vibe: str) -> list[dict]:
    """Sort by VIBE_AFFINITY for the intake's primary vibe (descending)."""
    vibe_scores = VIBE_AFFINITY.get(primary_vibe, {})
    return sorted(
        matches,
        key=lambda s: vibe_scores.get(s["cruise_line"], 0.5),
        reverse=True,
    )


def _apply_line_preference(
    rows: list[dict],
    primary_vibe: str,
    preferred_lines: list[str],
) -> list[dict]:
    """Boost rows from preferred cruise lines in the sort order.

    Preferred lines get a 0.15 additive boost on top of their VIBE_AFFINITY
    score for sorting purposes only — the stored vibe_score on each
    ShipAssessment is not modified. This is a soft preference: preferred
    lines rank higher when scores are close, but a much better vibe match
    from another line will still win.

    No-op when preferred_lines is empty (the common case — most users have
    no loyalty preference).
    """
    if not preferred_lines:
        return rows
    preferred_lower = {line.lower() for line in preferred_lines}
    vibe_scores = VIBE_AFFINITY.get(primary_vibe, {})

    def sort_key(row: dict) -> float:
        base = vibe_scores.get(row["cruise_line"], 0.5)
        boost = 0.15 if row["cruise_line"].lower() in preferred_lower else 0.0
        return base + boost

    return sorted(rows, key=sort_key, reverse=True)


def _dedupe_by_ship(rows: list[dict], limit: int = _MAX_RESULTS) -> list[dict]:
    """Keep the first occurrence of each ship_name, up to limit results.

    Apify returns multiple sailings per ship (different dates / itineraries).
    For Match results we want variety — at most one card per ship — so the
    user sees N different ships, not N copies of the same ship. The caller
    must pass rows in the desired priority order (highest vibe affinity first)
    so the cheapest / earliest / best-matching sailing for each ship is the
    one we surface.
    """
    seen_ships: set[str] = set()
    deduplicated: list[dict] = []
    for row in rows:
        ship = row["ship_name"]
        if ship in seen_ships:
            continue
        seen_ships.add(ship)
        deduplicated.append(row)
        if len(deduplicated) == limit:
            break
    return deduplicated


def _seed_to_public_shape(seed: dict) -> dict:
    """Project a seed-list record onto the same key set DB rows produce.

    The two shapes diverged after the Apify refactor: DB rows expose
    starting_price_usd / booking_url / destination_names / platform / id,
    while the seed list still uses prices dict / booking_affiliate_url /
    sailing_id. Callers must not have to branch on which path produced the
    result, so we normalize seed records to match DB row output here.
    """
    starting_price = int(seed["prices"]["interior"])
    # Derive destination_names from the itinerary_summary's leading region
    # phrase (the seed list uses 'Region: ports...' format consistently).
    summary = seed["itinerary_summary"]
    head = summary.split(":", 1)[0].strip() if ":" in summary else summary
    destination_names = [head] if head else []
    booking_url = seed.get("booking_url") or seed.get("booking_affiliate_url") or (
        f"https://partner.example.com/book"
        f"?sailing={seed['sailing_id']}&ref=cruisewise"
    )
    duration_nights = int(seed["duration_nights"])
    return {
        "sailing_id": seed["sailing_id"],
        "id": seed["sailing_id"],
        "cruise_line": seed["cruise_line"],
        "ship_name": seed["ship_name"],
        "departure_port": seed["departure_port"],
        "departure_date": seed["departure_date"],
        "return_date": _compute_return_date(
            seed.get("return_date"), seed["departure_date"], duration_nights
        ),
        "duration_nights": duration_nights,
        "itinerary_summary": urllib.parse.unquote(seed["itinerary_summary"]),
        "destination_names": destination_names,
        "starting_price_usd": starting_price,
        "currency": seed.get("currency", "USD"),
        "prices": dict(seed["prices"]),
        "booking_url": booking_url,
        "platform": seed.get("platform", seed["cruise_line"].lower()),
    }


def _search_seed_data(intake: MatchIntake) -> list[dict]:
    """Filter LEGACY_SEED_DATA and vibe-rank. Used as fallback when DB is empty.

    Output shape matches the DB-backed search: every record carries
    starting_price_usd, booking_url, destination_names, etc. — callers
    cannot tell which path produced the result.
    """
    matches = [s for s in LEGACY_SEED_DATA if _matches_filters(s, intake)]
    ranked = _vibe_rank(matches, intake.primary_vibe.value)
    boosted = _apply_line_preference(
        ranked, intake.primary_vibe.value, intake.preferred_cruise_lines
    )
    deduped = _dedupe_by_ship(boosted, limit=_MAX_RESULTS)
    return [_seed_to_public_shape(s) for s in deduped]


async def search_sailings(intake: MatchIntake, pool) -> list[dict]:
    """Query sailings table with filters from intake. Returns up to 5 results.

    Hard filters (SQL): departure_date window, duration_nights window,
    starting_price_usd <= budget, port whitelist, region match against
    destination_names via the GIN ?| operator. Soft ranking (Python):
    VIBE_AFFINITY by cruise_line for intake.primary_vibe.

    Falls back to LEGACY_SEED_DATA filtering when the DB returns zero rows
    (e.g. before the first Apify refresh, or when running locally without
    a populated table). Logs a warning when the fallback fires.
    """
    sql = [
        "SELECT id, cruise_line, ship_name, departure_port, departure_date,",
        "       return_date, duration_nights, itinerary_summary,",
        "       destination_names, starting_price_usd, currency,",
        "       booking_url, platform",
        "FROM sailings",
        "WHERE departure_date BETWEEN $1 AND $2",
        "  AND duration_nights BETWEEN $3 AND $4",
        "  AND starting_price_usd <= $5",
    ]
    args: list = [
        intake.earliest_departure,
        intake.latest_departure,
        intake.duration_nights_min,
        intake.duration_nights_max,
        intake.budget_per_person_usd,
    ]

    if intake.preferred_regions:
        args.append(list(intake.preferred_regions))
        # Substring match: a user saying 'Caribbean' should hit
        # 'Eastern Caribbean' / 'Western Caribbean'; 'Bahamas' should hit
        # 'The Bahamas'. Exact-containment via ?| was missing every real row.
        sql.append(
            f"  AND EXISTS ("
            f"      SELECT 1 FROM jsonb_array_elements_text(destination_names) AS dn"
            f"      WHERE dn ILIKE ANY ("
            f"          SELECT '%' || r || '%' FROM unnest(${len(args)}::text[]) AS r"
            f"      )"
            f"  )"
        )

    if intake.departure_ports_acceptable:
        # Live DB values are a mix of city names ('Miami, FL', 'Fort Lauderdale')
        # AND literal IATA codes ('HNL', 'SYD', 'BNE') depending on which actor
        # produced them. Always include both the original code AND its
        # city-name expansion so an intake of 'HNL' matches both
        # 'HNL' and 'Honolulu' / 'Hawaii'. Unknown codes fall through as
        # substrings of the original value, so 'Miami' or 'Barcelona' work directly.
        expanded: list[str] = []
        for code in intake.departure_ports_acceptable:
            up = code.upper()
            tokens = list(_IATA_TO_PORT_TOKENS.get(up, []))
            # Prepend the original token so the literal IATA code matches too
            if code not in tokens:
                tokens.insert(0, code)
            expanded.extend(tokens)
        args.append(expanded)
        sql.append(
            f"  AND departure_port ILIKE ANY ("
            f"      SELECT '%' || tok || '%' FROM unnest(${len(args)}::text[]) AS tok"
            f"  )"
        )

    query = "\n".join(sql)

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
    except Exception as exc:
        logger.warning(
            "search_sailings DB query failed (%s); falling back to seed data", exc
        )
        return _search_seed_data(intake)

    if not rows:
        logger.warning(
            "search_sailings: 0 DB rows for intake "
            "(regions=%s ports=%s); falling back to seed data",
            intake.preferred_regions,
            intake.departure_ports_acceptable,
        )
        return _search_seed_data(intake)

    sailings = [_row_to_sailing_dict(r) for r in rows]
    ranked = _vibe_rank(sailings, intake.primary_vibe.value)
    boosted = _apply_line_preference(
        ranked, intake.primary_vibe.value, intake.preferred_cruise_lines
    )
    return _dedupe_by_ship(boosted, limit=_MAX_RESULTS)


async def get_sailing(sailing_id: str, pool) -> dict | None:
    """Fetch a sailing by id from DB; falls back to legacy seed index on miss."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, cruise_line, ship_name, departure_port, departure_date,"
                "       return_date, duration_nights, itinerary_summary,"
                "       destination_names, starting_price_usd, currency,"
                "       booking_url, platform"
                " FROM sailings WHERE id = $1",
                sailing_id,
            )
    except Exception as exc:
        logger.warning(
            "get_sailing DB query failed (%s); falling back to seed index", exc
        )
        return _SAILING_INDEX.get(sailing_id)

    if row is None:
        return _SAILING_INDEX.get(sailing_id)

    return _row_to_sailing_dict(row)
