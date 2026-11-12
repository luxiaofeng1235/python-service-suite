"""
Alembic migration environment.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Column, MetaData, String, Table, engine_from_config, inspect, pool, text
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.database import Base
from app.models import (
    AdminToken,  # noqa: F401
    AiChatLog,  # noqa: F401
    AiToWork,  # noqa: F401
    Attachment,  # noqa: F401
    AuthAdmin,  # noqa: F401
    CasbinRule,  # noqa: F401
    ChatMessage,  # noqa: F401
    ChatSession,  # noqa: F401
    CmsArticle,  # noqa: F401
    CmsTag,  # noqa: F401
    GoodsBrand,  # noqa: F401
    GoodsCategory,  # noqa: F401
    GoodsProduct,  # noqa: F401
    GoodsSku,  # noqa: F401
    HoroscopeCache,  # noqa: F401
    LotteryConfig,  # noqa: F401
    Permission,  # noqa: F401
    Role,  # noqa: F401
    User,  # noqa: F401
    UserAstrologyProfile,  # noqa: F401
    UserToken,  # noqa: F401
    VerificationCode,  # noqa: F401
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url(url: str) -> str:
    """Convert async SQLAlchemy URL to a sync URL for Alembic."""
    return url.replace("+aiomysql", "+pymysql").replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    context.configure(
        url=_sync_database_url(settings.DATABASE_URL),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live database connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_database_url(settings.DATABASE_URL)

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _prepare_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


def _prepare_version_table(connection: Connection) -> None:
    """Keep deployed revision IDs and allow the existing 37-character ID."""
    version_table = Table(
        "alembic_version", MetaData(),
        Column("version_num", String(64), primary_key=True, nullable=False),
    )
    version_table.create(connection, checkfirst=True)
    column = inspect(connection).get_columns("alembic_version")[0]
    if (getattr(column["type"], "length", None) or 64) < 64:
        # MySQL 会限制 VARCHAR 长度；SQLite 不限制，无需重建版本表。
        if connection.dialect.name == "mysql":
            connection.execute(text("ALTER TABLE alembic_version MODIFY version_num VARCHAR(64) NOT NULL"))
        elif connection.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"))
    connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
