"""
Alembic migration environment
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.database import Base
from app.models import models  # Import all models to register them

config = context.config

# Convert async database URLs to sync for migrations
db_url = settings.DATABASE_URL
if "postgresql+asyncpg://" in db_url:
    # Convert asyncpg to psycopg2 for sync migrations
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
elif "sqlite+aiosqlite://" in db_url:
    # Convert aiosqlite to pysqlite for sync migrations
    db_url = db_url.replace("sqlite+aiosqlite://", "sqlite://")
elif "sqlite:///" in db_url and "sqlite+aiosqlite:///" not in db_url:
    # Keep sqlite:// as is for sync migrations
    pass

config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
