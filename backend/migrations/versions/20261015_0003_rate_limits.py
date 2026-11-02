"""Add per-user rate-limit buckets for paid AI requests."""

from alembic import op
import sqlalchemy as sa

revision = "20261015_0003"
down_revision = "20261014_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("rate_limit_buckets")
