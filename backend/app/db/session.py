from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)


async_engine = create_async_engine(
    settings.get_dsn(),  
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool
)

async_session = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
