import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Make backend package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from backend.database.models import Base
from backend.utils.config import DATABASE_URL

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use sync psycopg2 URL for Alembic (swap asyncpg driver)
sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
# configparser treats % as interpolation syntax — escape it
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))


def run_migrations_offline():
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
