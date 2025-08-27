import sys
import pathlib
import logging

from alembic import context
from sqlalchemy import engine_from_config, pool, types as sqltypes

# --- путь до проекта ---
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# --- импорт базовой модели и настроек ---
from app.models import Base
from app.config import settings
from app.logger import get_logger

# Поддержка pgvector
from pgvector.sqlalchemy import Vector
from alembic.autogenerate import renderers


# --- Alembic config ---
config = context.config
config.set_main_option("sqlalchemy.url", settings.get_dsn())

# --- Логирование ---
root_logger = get_logger("alembic")
root_logger.setLevel(logging.DEBUG if not settings.ollam_prod else logging.WARNING)

# --- Метаданные моделей ---
target_metadata = Base.metadata


# ---- кастомный рендер для Vector ----
@renderers.dispatch_for(sqltypes.UserDefinedType)
def render_user_defined_types(type_, autogen_context):
    """
    Универсальный хук для всех UserDefinedType.
    Проверяем, если это именно Vector/VECTOR — рендерим красиво.
    """
    if isinstance(type_, Vector) or type(type_) is Vector or type(type_).__name__ == "VECTOR":
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector({getattr(type_, 'dim', None) or 0})"
    # другие UserDefinedType не трогаем → пусть Alembic обрабатывает как обычно
    return None
# ------------------------------------


def run_migrations_offline() -> None:
    """Запуск миграций в 'offline' режиме (без подключения к БД)."""
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


def run_migrations_online() -> None:
    """Запуск миграций в 'online' режиме (с подключением к БД)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()