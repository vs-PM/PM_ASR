# app/services/jobs/locks.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.logger import get_logger
from app.db.session import async_engine

log = get_logger(__name__)

LOCK_NAMESPACE = 424242  # 任意 стабильный int

def _lock_key(transcript_id: int) -> int:
    # Ключ: (namespace << 32) ^ (tid & 0xffffffff) — умещается в signed BIGINT
    return ((LOCK_NAMESPACE & 0xffffffff) << 32) ^ (int(transcript_id) & 0xffffffff)

@asynccontextmanager
async def pg_advisory_lock(transcript_id: int) -> AsyncIterator[bool]:
    key = _lock_key(transcript_id)
    conn: AsyncConnection | None = None
    try:
        conn = await async_engine.connect()
        # Пытаемся взять без блокировки — если не удалось, сразу выходим
        res = await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
        acquired = bool(res.scalar())
        if not acquired:
            yield False
            return
        yield True
    except Exception:
        log.exception("pg_advisory_lock error (tid=%s)", transcript_id)
        yield False
    finally:
        if conn is not None:
            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            except Exception:
                log.warning("Unlock failed (tid=%s)", transcript_id)
            await conn.close()
