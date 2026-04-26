"""
Trigger a simulated price drop for a given booking — demo / manual QA tool.

Calls inject_mock_drop() in the price_checker worker, which writes to price_history
and runs the Watch agent pipeline (once implemented).

Usage:
  uv run python scripts/trigger_mock_drop.py <booking_id> <mock_price_usd>

Example:
  uv run python scripts/trigger_mock_drop.py abc-123 1199.00
"""

from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


async def main(booking_id: str, mock_price_usd: float) -> None:
    from backend.workers.price_checker import inject_mock_drop

    snapshot = await inject_mock_drop(
        booking_id=booking_id,
        mock_price_usd=mock_price_usd,
        mock_perks=["beverage_package", "wifi"],
    )
    logger.info("Injected snapshot: %s", snapshot.model_dump())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <booking_id> <mock_price_usd>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], float(sys.argv[2])))
