"""Add AI call telemetry: latency, tokens and outcome for each provider call."""

from alembic import op
import sqlalchemy as sa

revision = "20261102_0004"
down_revision = "20261015_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("error", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_calls_created_at", "ai_calls", ["created_at"])


def downgrade():
    op.drop_index("ix_ai_calls_created_at", table_name="ai_calls")
    op.drop_table("ai_calls")
