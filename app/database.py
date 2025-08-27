# app/database.py
import asyncpg
from pathlib import Path
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

# Глобальный пул (создаётся один раз)
pool: asyncpg.Pool | None = None

async def init_pool() -> None:
    """Создаёт пул и применяет миграции при первом запуске."""
    global pool
    if pool is None:
        log.debug("Создаём asyncpg‑pool")
        pool = await asyncpg.create_pool(
            dsn=settings.get_dsn(),
            min_size=5,
            max_size=20,
        )
        log.debug("Пул создан")
        await _ensure_tables(pool)

async def close_pool() -> None:
    global pool
    if pool:
        log.debug("Закрываем пул")
        await pool.close()
        pool = None
        log.debug("Пул закрыт")

# ---------- helpers ---------------------------------------------------------

async def get_pool() -> asyncpg.Pool:
    """Возвращаем уже инициализированный пул.  
    При первом вызове будет выброшено исключение – это удобно при отладке."""
    global pool
    if pool is None:
        raise RuntimeError("Pool has not been initialized")
    return pool

# ---------- миграции -------------------------------------------------------
async def _ensure_tables(pool: asyncpg.Pool) -> None:
    required_tables = {"mfg_transcript", "mfg_segment", "mfg_embedding"}
    async with pool.acquire() as conn:
        existing = await conn.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            """
        )
        existing_names = {row["tablename"] for row in existing}
        missing = required_tables - existing_names
        if not missing:
            log.debug("Все таблицы уже есть")
            return
        log.warning(f"Таблицы отсутствуют: {missing}. Создаём их.")
        migration_sql_path = Path(__file__).parent.parent / "migrations" / "init.sql"
        if not migration_sql_path.exists():
            log.error(f"Файл миграции {migration_sql_path} не найден")
            return
        migration_sql = migration_sql_path.read_text(encoding="utf-8")
        try:
            await conn.execute(migration_sql)
            log.info(f"Созданы таблицы: {', '.join(missing)}")
        except Exception as exc:
            log.exception("Не удалось применить миграцию")
            raise
