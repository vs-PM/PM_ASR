import asyncpg
import os
from contextlib import asynccontextmanager

DB_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://vvs:password43_vvs@postgres:5432/llm"
)

@asynccontextmanager
async def get_pool():
    pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=5, max_size=20)
    try:
        yield pool
    finally:
        await pool.close()