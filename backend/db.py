from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg

from backend.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    # Register pgvector codec so vector columns decode as Python lists.
    # The vector type lives in the schema where the extension was created
    # (default: 'public'). Using pg_catalog here would fail with "unknown type".
    async with _pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        try:
            await conn.set_type_codec(
                "vector",
                encoder=lambda v: str(v),
                decoder=lambda v: [float(x) for x in v.strip("[]").split(",")],
                schema="public",
                format="text",
            )
        except Exception as exc:
            # Non-fatal: review_chunks RAG isn't wired into the Match flow yet.
            # If pgvector isn't available, we log and continue — match flow
            # only needs match_intakes / match_results.
            logger.warning("pgvector codec registration failed: %s", exc)
    logger.info("Database pool initialised")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised — call init_pool() first")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
