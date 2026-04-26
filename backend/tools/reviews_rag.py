"""
Reviews RAG tool — retrieves review chunks from pgvector for a given ship.

Two retrieval methods are exposed:
  - retrieve_by_embedding: semantic similarity via pgvector HNSW index (primary)
  - retrieve_by_ship: keyword filter over ship_name (fallback / hybrid)

Both return plain strings ready to stuff into a prompt context window.
"""

from __future__ import annotations

import logging

from backend.db import acquire

logger = logging.getLogger(__name__)

_RETRIEVAL_LIMIT = 8


async def retrieve_by_embedding(query_embedding: list[float], ship_name: str) -> list[str]:
    """Semantic retrieval: top-k review chunks by cosine distance to query_embedding."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT chunk_text
            FROM review_chunks
            WHERE ship_name = $1
            ORDER BY embedding <=> $2::vector
            LIMIT $3
            """,
            ship_name,
            query_embedding,
            _RETRIEVAL_LIMIT,
        )
    return [row["chunk_text"] for row in rows]


async def retrieve_by_ship(ship_name: str) -> list[str]:
    """Keyword retrieval: most recent chunks for a ship, no embedding required.

    Used when no query embedding is available (e.g. cold-start, fallback).
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT chunk_text
            FROM review_chunks
            WHERE ship_name ILIKE $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            f"%{ship_name}%",
            _RETRIEVAL_LIMIT,
        )
    return [row["chunk_text"] for row in rows]
