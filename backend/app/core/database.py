"""
Database setup with SQLAlchemy async
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Convert sqlite:// to sqlite+aiosqlite://
DATABASE_URL = settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

# SQLite-specific connection args (check_same_thread is not valid for PostgreSQL)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Configure engine with proper pooling for async operations
# Key settings to prevent event loop conflicts:
# - pool_pre_ping: Test connections before use
# - pool_recycle: Refresh connections periodically
# - max_overflow: Allow temporary extra connections
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
    pool_pre_ping=True,      # Verify connections before using
    pool_recycle=3600,       # Recycle connections after 1 hour
    pool_size=5,             # Base pool size
    max_overflow=10,         # Extra connections when needed
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def create_background_session_maker():
    """
    Create a new session maker for background tasks running in separate threads.
    This prevents event loop conflicts when using asyncpg/aiosqlite.
    """
    from sqlalchemy.pool import NullPool

    bg_engine = create_async_engine(
        DATABASE_URL,
        echo=settings.DEBUG,
        connect_args=connect_args,
        pool_pre_ping=True,
        poolclass=NullPool,  # No pooling for background tasks
    )

    return async_sessionmaker(
        bg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency: get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database, create all tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
