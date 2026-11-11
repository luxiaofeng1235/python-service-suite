"""
============================================
Astrology Agent Schema - Profiles, conversations and horoscope cache
============================================
Add four business tables while reusing the existing integer users.id.
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20261111_0002"
down_revision: str | None = "20261111_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create astrology profiles and Agent conversation storage."""
    op.create_table(
        "user_astrology_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, comment="Profile ID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Existing users.id; one profile per user"),
        sa.Column("birthday", sa.Date(), nullable=True, comment="Birth date in the Gregorian calendar"),
        sa.Column("birth_time", sa.Time(), nullable=True, comment="Local birth time; null when unknown"),
        sa.Column("birth_timezone", sa.String(64), nullable=True, comment="IANA birth timezone, e.g. Asia/Shanghai"),
        sa.Column("birth_place", sa.String(255), nullable=True, comment="Birthplace name"),
        sa.Column("birth_latitude", sa.Numeric(10, 7), nullable=True, comment="Birthplace latitude in degrees"),
        sa.Column("birth_longitude", sa.Numeric(10, 7), nullable=True, comment="Birthplace longitude in degrees"),
        sa.Column("constellation", sa.String(20), nullable=True, comment="Default zodiac sign, e.g. aries or pisces"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="Updated time"),
        sa.CheckConstraint("birth_latitude BETWEEN -90 AND 90", name="ck_astrology_birth_latitude"),
        sa.CheckConstraint("birth_longitude BETWEEN -180 AND 180", name="ck_astrology_birth_longitude"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        comment="User astrology profiles",
    )
    op.create_index("ix_user_astrology_profiles_user_id", "user_astrology_profiles", ["user_id"], unique=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True, comment="Session UUID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Existing users.id"),
        sa.Column("title", sa.String(100), nullable=False, server_default="新对话", comment="Conversation title"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="Updated time"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        comment="Agent chat sessions",
    )
    op.create_index("idx_chat_sessions_user_updated", "chat_sessions", ["user_id", "updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="Message ID"),
        sa.Column("session_id", sa.String(36), nullable=False, comment="Related chat_sessions.id"),
        sa.Column("role", sa.String(20), nullable=False, comment="Message role: system, user, assistant, tool"),
        sa.Column("content", sa.Text(), nullable=True, comment="Message text or serialized JSON; null for tool-only calls"),
        sa.Column("tool_name", sa.String(64), nullable=True, comment="Tool function name"),
        sa.Column("tool_calls", sa.JSON(none_as_null=True), nullable=True, comment="Assistant tool calls with IDs, function names and arguments"),
        sa.Column("tool_call_id", sa.String(128), nullable=True, comment="Tool result correlation ID"),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default=sa.text("1"), comment="0=generating 1=completed 2=failed 3=interrupted"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="Updated time"),
        sa.CheckConstraint("role IN ('system', 'user', 'assistant', 'tool')", name="ck_chat_messages_role"),
        sa.CheckConstraint("status IN (0, 1, 2, 3)", name="ck_chat_messages_status"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        comment="Agent chat messages and tool calls",
    )
    op.create_index("idx_chat_messages_session_id", "chat_messages", ["session_id", "id"])

    op.create_table(
        "horoscope_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="Cache ID"),
        sa.Column("constellation", sa.String(20), nullable=False, comment="Zodiac sign, e.g. aries or pisces"),
        sa.Column("fortune_date", sa.Date(), nullable=False, comment="Fortune date in the configured business timezone"),
        sa.Column("aspect", sa.String(30), nullable=False, server_default="all", comment="Fortune aspect: all, love, career, wealth"),
        sa.Column("score", sa.Integer(), nullable=True, comment="Fortune score from 0 to 100"),
        sa.Column("raw_data", sa.JSON(), nullable=False, comment="Structured horoscope content"),
        sa.Column("source", sa.String(100), nullable=True, comment="Data provider or generation source"),
        sa.Column("expires_at", sa.DateTime(), nullable=True, comment="Optional cache expiry time"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), comment="Created time"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), comment="Updated time"),
        sa.UniqueConstraint("constellation", "fortune_date", "aspect", name="uk_constellation_date_aspect"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_horoscope_cache_score"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
        comment="Shared daily horoscope cache",
    )


def downgrade() -> None:
    """Remove only the four tables introduced by this revision."""
    op.drop_table("horoscope_cache")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("user_astrology_profiles")
