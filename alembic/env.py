"""
Alembic environment.

Per Phase 3 §6.11: reads DATABASE_URL from environment (via app.core.config),
never hardcoded in alembic.ini. Uses a sync driver for migrations (asyncpg is
used only by the running app), so the URL scheme is swapped to psycopg here.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.db.base_model import Base

# Import every module's models here so they register on Base.metadata before
# `alembic revision --autogenerate` runs.
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.academic import models as academic_models  # noqa: F401
from app.modules.student import models as student_models  # noqa: F401
from app.modules.teacher import models as teacher_models  # noqa: F401
from app.modules.question_bank import models as question_bank_models  # noqa: F401
from app.modules.blueprint import models as blueprint_models  # noqa: F401
from app.modules.paper_generation import models as paper_generation_models  # noqa: F401
from app.modules.exam_management import models as exam_management_models  # noqa: F401
from app.modules.evaluation import models as evaluation_models  # noqa: F401
from app.modules.learning_profile import models as learning_profile_models  # noqa: F401
from app.modules.analytics import models as analytics_models  # noqa: F401
from app.modules.recommendation import models as recommendation_models  # noqa: F401
from app.modules.reports import models as reports_models  # noqa: F401
from app.modules.storage import models as storage_models  # noqa: F401
from app.modules.integration import models as integration_models  # noqa: F401
from app.core.notifications import models as notifications_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.db.url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
