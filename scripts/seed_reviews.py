"""
Seed ~200 review chunks into the review_chunks pgvector table.

Stub: no actual reviews or embeddings yet. Wire up:
  1. A source of real cruise reviews (CSV, web scrape, synthetic generation)
  2. OpenAI embeddings API (text-embedding-3-small, 1536 dims)
  3. Batch INSERT into review_chunks with the generated vectors

Usage (once implemented):
  uv run python scripts/seed_reviews.py
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def seed() -> None:
    raise NotImplementedError("seed_reviews not yet implemented")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
