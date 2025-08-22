import asyncpg
from contextlib import asynccontextmanager
from app.config import settings

@asynccontextmanager
async def get_pool():
    pool = await asyncpg.create_pool(dsn=settings.get_dsn(), min_size=5, max_size=20)
    try:
        yield pool
    finally:
        await pool.close()