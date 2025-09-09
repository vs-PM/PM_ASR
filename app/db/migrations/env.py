import sys
import pathlib
import logging
import asyncio

from alembic import context
from sqlalchemy import pool, types as sqltypes
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic.autogenerate import renderers

# --- путь до проекта ---
CURRENT_FILE = pathlib.Path(__file__).resolve()
# /.../PM_ASR/app/db/migrations/env.py
# parents: [migrations, db, app, PM_ASR, ...]
for up in range(3, len(CURRENT_FILE.parents)):
    candidate = CURRENT_FILE.parents[up]
    if (candidate / "app").is_dir():
        PROJECT_ROOT = candidate
        break
else:
    # Fallback: на случай необычной структуры
    PROJECT_ROOT = CURRENT_FILE.parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- импорт базовой модели и настроек ---
from app.db.models import Base
from app.core.config import settings
from app.core.logger import get_logger

# Поддержка pgvector
from pgvector.sqlalchemy import Vector

# --- Alembic config ---
config = context.config
config.set_main_option("sqlalchemy.url", settings.get_dsn())

# --- Логирование ---
root_logger = get_logger("alembic")
root_logger.setLevel(logging.DEBUG if not getattr(settings, "ollam_prod", False) else logging.WARNING)

# --- Метаданные моделей ---
target_metadata = Base.metadata

# ---- кастомный рендер для Vector ----
@renderers.dispatch_for(sqltypes.UserDefinedType)
def render_user_defined_types(type_, autogen_context):
    """
    Универсальный хук для UserDefinedType (например, Vector).
    Добавляет импорт автоматически и рендерит тип.
    """
    if isinstance(type_, Vector) or type(type_).__name__ == "VECTOR":
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector({getattr(type_, 'dim', None) or 0})"
    return None


def run_migrations_offline() -> None:
    """Миграции в offline режиме (без подключения к БД)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    """Общая настройка контекста для online/async."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Миграции в online режиме (async)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
