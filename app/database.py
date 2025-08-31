from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

Base = declarative_base()


engine = create_async_engine(
    settings.get_dsn(),  
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool
)

async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
