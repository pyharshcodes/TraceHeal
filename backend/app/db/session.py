from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Base Model for all DB models
Base = declarative_base()

# Configure Async Engine
is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args=connect_args,
)


# SQLite PRAGMAs for high-concurrency WAL mode and Foreign Key enforcement
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


# Async session maker
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

AsyncSessionLocal = async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


get_db = get_db_session


def _migrate_sqlite_schema(sync_conn):
    """Safely adds newly defined columns to existing SQLite tables."""
    try:
        # Check hypotheses columns
        res = sync_conn.exec_driver_sql("PRAGMA table_info(hypotheses);").fetchall()
        hypo_cols = [row[1] for row in res]
        if hypo_cols and "reproduction_recipe_json" not in hypo_cols:
            sync_conn.exec_driver_sql("ALTER TABLE hypotheses ADD COLUMN reproduction_recipe_json TEXT;")

        # Check remediations columns
        res2 = sync_conn.exec_driver_sql("PRAGMA table_info(remediations);").fetchall()
        rem_cols = [row[1] for row in res2]
        if rem_cols and "validation_status" not in rem_cols:
            sync_conn.exec_driver_sql("ALTER TABLE remediations ADD COLUMN validation_status VARCHAR(32) DEFAULT 'PENDING';")
        if rem_cols and "validation_details_json" not in rem_cols:
            sync_conn.exec_driver_sql("ALTER TABLE remediations ADD COLUMN validation_details_json TEXT;")

        # Check incidents columns
        res3 = sync_conn.exec_driver_sql("PRAGMA table_info(incidents);").fetchall()
        inc_cols = [row[1] for row in res3]
        if inc_cols and "postmortem_markdown" not in inc_cols:
            sync_conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN postmortem_markdown TEXT;")
        if inc_cols and "pull_request_json" not in inc_cols:
            sync_conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN pull_request_json TEXT;")
        if inc_cols and "resolved_at" not in inc_cols:
            sync_conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN resolved_at DATETIME;")
        if inc_cols and "closed_at" not in inc_cols:
            sync_conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN closed_at DATETIME;")
    except Exception:
        pass


async def init_db():
    """Initializes all database tables defined in models."""
    async with engine.begin() as conn:
        # Import models here to ensure they are registered with Base.metadata
        from backend.app.db import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        if is_sqlite:
            await conn.run_sync(_migrate_sqlite_schema)
    logger.info("Database initialized successfully with WAL mode.")


async def close_db():
    """Closes all database connections."""
    await engine.dispose()
    logger.info("Database connections closed.")
