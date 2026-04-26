"""
One-time seed script to populate the sailings table from Apify.

Usage:
    APIFY_API_TOKEN=apify_api_... uv run python scripts/seed_inventory.py

Expects:
  - Local Postgres running at DATABASE_URL
  - Valid APIFY_API_TOKEN in environment

Prints a summary of results per scraper when done.
"""

from __future__ import annotations

import asyncio
import json
import logging

from backend.workers.inventory_refresh import run_refresh


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    summary = asyncio.run(run_refresh())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
