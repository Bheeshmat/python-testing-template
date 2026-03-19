import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Alembic config object ──────────────────────────────────────────────────────
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Inject DATABASE_URL from environment ──────────────────────────────────────
# We never hardcode the URL in alembic.ini (it's committed to git).
# Instead we read it from the environment at runtime — same pattern as the app.
# This means the same alembic commands work for local dev, staging, and prod
# just by changing the DATABASE_URL environment variable.
database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
config.set_main_option("sqlalchemy.url", database_url)

# ── Register our models with Alembic ──────────────────────────────────────────
# target_metadata tells Alembic what the schema SHOULD look like.
# Alembic compares this against the actual DB to generate migration diffs.
#
# IMPORTANT: all model files must be imported here so SQLAlchemy's Base.metadata
# knows about every table. If you add a new model file, import it below.
from src.database import Base  # noqa: E402
from src import models  # noqa: F401, E402 — registers User, Task with Base.metadata

target_metadata = Base.metadata


# ── Offline mode ──────────────────────────────────────────────────────────────
# Generates SQL scripts without connecting to the DB.
# Useful for reviewing migrations before applying them.
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────
# Connects to the DB and applies migrations directly.
# This is the mode used in normal development and in the CI/CD pipeline.
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
