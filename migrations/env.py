"""Alembic environment for asynchronous SQLAlchemy migrations."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

import pulsewatch.db.models  # noqa: F401 - registers models on Base.metadata
from pulsewatch.core.config import get_settings
from pulsewatch.db.base import Base

target_metadata = Base.metadata


def get_url() -> str:
    """Use the dedicated migration role when configured, else the app role."""
    settings = get_settings()
    configured = settings.migration_database_url or settings.database_url
    return configured.get_secret_value()


def run_migrations_offline() -> None:
    """Generate SQL without connecting to a database."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open an async connection and run migrations on it."""
    connectable = create_async_engine(get_url(), poolclass=pool.NullPool)
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured PostgreSQL database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
