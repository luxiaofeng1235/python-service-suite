"""
============================================
Agent Session Execution - Business isolation and execution leases
============================================
Tags sessions by Agent and prevents overlapping runs without long database transactions.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0003"
down_revision: str | None = "20261111_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add session routing and crash-recoverable run ownership."""
    op.add_column("chat_sessions", sa.Column("agent", sa.String(50), nullable=False, server_default="astrology", comment="Agent identifier, e.g. astrology or divination"))
    op.add_column("chat_sessions", sa.Column("active_run_id", sa.String(36), nullable=True, comment="Current execution lease UUID"))
    op.add_column("chat_sessions", sa.Column("run_expires_at", sa.DateTime(), nullable=True, comment="Execution lease expiry time"))
    op.create_index("idx_chat_sessions_user_agent_updated", "chat_sessions", ["user_id", "agent", "updated_at"])


def downgrade() -> None:
    """Remove execution coordination while preserving conversations."""
    op.drop_index("idx_chat_sessions_user_agent_updated", table_name="chat_sessions")
    op.drop_column("chat_sessions", "run_expires_at")
    op.drop_column("chat_sessions", "active_run_id")
    op.drop_column("chat_sessions", "agent")
