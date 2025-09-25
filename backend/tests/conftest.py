from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# PYTHONPATH и переменные окружения
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


DEFAULT_ENV: Dict[str, str] = {
    "HF_TOKEN": "test",
    "DEVICE": "cpu",
    "OLLAMA_URL": "http://localhost:11434",
    "EMBEDDING_MODEL": "test",
    "SUMMARIZE_MODEL": "test",
    "OLLAMA_CHAT_TIMEOUT": "10",
    "OLLAMA_CONNECT_TIMEOUT": "1",
    "OLLAMA_READ_TIMEOUT": "1",
    "OLLAMA_WRITE_TIMEOUT": "1",
    "OLLAMA_KEEP_ALIVE": "1m",
    "SUMMARIZE_NUM_CTX": "1",
    "SUMMARIZE_TEMPERATURE": "0.1",
    "SUMMARIZE_TOP_P": "0.1",
    "SUMMARIZE_NUM_PREDICT_BATCH": "1",
    "SUMMARIZE_NUM_PREDICT_FINAL": "1",
    "MAX_REFS_CHARS": "1000",
    "MAX_DRAFT_CHARS": "1000",
    "MAX_FINAL_DRAFT_CHARS": "1000",
    "RAG_CHUNK_CHAR_LIMIT": "1000",
    "RAG_TOP_K": "3",
    "RAG_MIN_SCORE": "0.5",
    "VAD_AGGRESSIVENESS": "1",
    "VAD_FRAME_MS": "30",
    "VAD_MIN_SPEECH_MS": "200",
    "VAD_MIN_SILENCE_MS": "100",
    "VAD_MERGE_MAX_GAP_SEC": "0.5",
    "VAD_MAX_SEGMENT_SEC": "30",
    "SEG_OVERLAP_SEC": "0.1",
    "FIXED_WINDOW_SEC": "1.0",
    "FIXED_OVERLAP_SEC": "0.1",
    "FFMPEG_THREADS": "1",
    "FFMPEG_FILTER_THREADS": "1",
    "FFMPEG_PROBESIZE": "1M",
    "FFMPEG_ANALYZEDURATION": "1",
    "FFMPEG_USE_SOXR": "false",
    "OLLAMA_DB_HOST": "localhost",
    "OLLAMA_DB_PORT": "5432",
    "OLLAMA_DB_NAME": "test",
    "OLLAMA_DB_USER": "test",
    "OLLAMA_DB_PASSWORD": "test",
    "OLLAM_PROD": "false",
    "OLLAMA_LOG_PATH": str(REPO_ROOT / "test.log"),
    "JWT_SECRET": "secret",
    "JWT_ALGO": "HS256",
    "ACCESS_TTL_MINUTES": "15",
    "REFRESH_TTL_DAYS": "7",
    "COOKIE_DOMAIN": "",
    "COOKIE_SECURE": "false",
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Заглушка для app.services.jobs.api, чтобы не тянуть тяжёлые зависимости
# ---------------------------------------------------------------------------
jobs_module = types.ModuleType("app.services.jobs.api")
jobs_calls: Dict[str, list] = {
    "transcription": [],
    "diarization": [],
    "pipeline": [],
    "embeddings": [],
    "summary": [],
    "protokol": [],
}


async def _record(name: str, *args: Any, **kwargs: Any) -> None:
    jobs_calls[name].append({"args": args, "kwargs": kwargs})


async def process_transcription(*args: Any, **kwargs: Any) -> None:
    await _record("transcription", *args, **kwargs)


async def process_diarization(*args: Any, **kwargs: Any) -> None:
    await _record("diarization", *args, **kwargs)


async def process_pipeline(*args: Any, **kwargs: Any) -> None:
    await _record("pipeline", *args, **kwargs)


async def process_embeddings(*args: Any, **kwargs: Any) -> None:
    await _record("embeddings", *args, **kwargs)


async def process_summary(*args: Any, **kwargs: Any) -> None:
    await _record("summary", *args, **kwargs)


async def process_protokol(*args: Any, **kwargs: Any) -> None:
    await _record("protokol", *args, **kwargs)


jobs_module.process_transcription = process_transcription
jobs_module.process_diarization = process_diarization
jobs_module.process_pipeline = process_pipeline
jobs_module.process_embeddings = process_embeddings
jobs_module.process_summary = process_summary
jobs_module.process_protokol = process_protokol
jobs_module.calls = jobs_calls

sys.modules.setdefault("app.services.jobs.api", jobs_module)


# ---------------------------------------------------------------------------
# Компиляция postgres-типов для SQLite (используем в тестовой БД)
# ---------------------------------------------------------------------------
from pgvector.sqlalchemy import Vector  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kwargs):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array(element, compiler, **kwargs):
    return "TEXT"


@compiles(Vector, "sqlite")
def _compile_vector(element, compiler, **kwargs):
    return "BLOB"


@compiles(BigInteger, "sqlite")
def _compile_bigint(element, compiler, **kwargs):
    return "INTEGER"


# ---------------------------------------------------------------------------
# Общие фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:  # type: ignore[override]
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def db_engine(event_loop: asyncio.AbstractEventLoop, tmp_path_factory: pytest.TempPathFactory) -> Tuple[AsyncEngine, sessionmaker]:
    from app.db import models  # noqa: E402
    from app.db import session as session_module  # noqa: E402

    db_path = tmp_path_factory.mktemp("db") / "test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)

    event_loop.run_until_complete(prepare())

    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session_module.async_engine = engine
    session_module.async_session = SessionLocal

    # Обновляем кэшированные ссылки на сессию/движок в уже импортированных модулях
    try:
        from app.api.v1 import files as files_api  # noqa: E402
        files_api.async_session = SessionLocal
    except ModuleNotFoundError:
        pass
    try:
        from app.api.v1 import admin as admin_api  # noqa: E402
        admin_api.async_session = SessionLocal
    except ModuleNotFoundError:
        pass
    try:
        from app.api.v1 import transcripts as transcripts_api  # noqa: E402
        transcripts_api.async_session = SessionLocal
    except ModuleNotFoundError:
        pass
    try:
        from app.services import audit as audit_service  # noqa: E402
        audit_service.async_session = SessionLocal
    except ModuleNotFoundError:
        pass
    try:
        from app.api.v1 import health as health_api  # noqa: E402
        health_api.async_engine = engine
    except ModuleNotFoundError:
        pass
    try:
        from app.api.v1 import auth as auth_api  # noqa: E402
        auth_api.async_session = SessionLocal
    except ModuleNotFoundError:
        pass
    return engine, SessionLocal


@pytest.fixture(autouse=True)
def seed_database(db_engine: Tuple[AsyncEngine, sessionmaker], event_loop: asyncio.AbstractEventLoop):
    from app.db import models  # noqa: E402
    from app.core.security import hash_password  # noqa: E402

    engine, SessionLocal = db_engine

    async def reset() -> Tuple[models.MfgUser, models.MfgUser]:
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)

        async with SessionLocal() as session:
            user = models.MfgUser(
                id=1,
                login="user@example.com",
                password_hash=hash_password("password"),
                role=models.UserRole.user,
                is_active=True,
            )
            admin = models.MfgUser(
                id=2,
                login="admin@example.com",
                password_hash=hash_password("password"),
                role=models.UserRole.admin,
                is_active=True,
            )
            session.add_all([user, admin])
            await session.commit()
            await session.refresh(user)
            await session.refresh(admin)
            return user, admin

    users = event_loop.run_until_complete(reset())
    return users


@pytest.fixture(autouse=True)
def clear_job_calls() -> None:
    for records in jobs_calls.values():
        records.clear()


@pytest.fixture(scope="session")
def session_maker(db_engine: Tuple[AsyncEngine, sessionmaker]) -> sessionmaker:
    return db_engine[1]


@pytest.fixture
def run_async(event_loop: asyncio.AbstractEventLoop):
    def runner(coro):
        return event_loop.run_until_complete(coro)

    return runner


@pytest.fixture
def client(
    db_engine: Tuple[AsyncEngine, sessionmaker],
    seed_database: Tuple[Any, Any],
    tmp_path: Path,
):
    from fastapi.testclient import TestClient  # noqa: E402
    from main import app  # noqa: E402
    from app.core.auth import require_admin, require_user  # noqa: E402
    from app.core.config import settings  # noqa: E402
    from app.db.session import get_session  # noqa: E402

    _, SessionLocal = db_engine
    user, admin = seed_database

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir = str(upload_dir)

    async def override_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: admin

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_client(
    db_engine: Tuple[AsyncEngine, sessionmaker],
    seed_database: Tuple[Any, Any],
    tmp_path: Path,
):
    from fastapi.testclient import TestClient  # noqa: E402
    from main import app  # noqa: E402
    from app.core.config import settings  # noqa: E402
    from app.db.session import get_session  # noqa: E402

    _, SessionLocal = db_engine

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir = str(upload_dir)

    async def override_session():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def jobs_call_log() -> Dict[str, list]:
    return jobs_calls

