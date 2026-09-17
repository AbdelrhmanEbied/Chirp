"""Shared Alembic environment.

Each service owns its own migration history against its own database. This
helper keeps every service's `migrations/env.py` down to a few lines so the
boilerplate lives in one place and behaves identically everywhere.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import MetaData, create_engine, pool


def run_migrations(metadata: MetaData, *, env_var: str = "DATABASE_URL") -> None:
    """Run migrations in 'offline' or 'online' mode, as Alembic requests.

    The async driver URL used by the application is rewritten to the sync
    driver here: migrations are a short-lived batch job and running them
    synchronously avoids an event loop inside Alembic for no benefit.
    """
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(f"{env_var} must be set to run migrations.")
    sync_url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")

    if context.is_offline_mode():
        context.configure(
            url=sync_url,
            target_metadata=metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(sync_url, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
