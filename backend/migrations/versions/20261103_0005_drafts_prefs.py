"""Store interview preferences, answer drafts and when each question was asked on the server."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_0005"
down_revision = "20261102_0004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("interview_prefs", sa.Text()))
    with op.batch_alter_table("interview_questions") as batch:
        batch.add_column(sa.Column("asked_at", sa.DateTime()))
    # Questions already in progress count from when they were created, as before.
    op.execute("UPDATE interview_questions SET asked_at = created_at")
    op.create_table(
        "answer_drafts",
        sa.Column("interview_id", sa.Integer(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("answer_drafts")
    with op.batch_alter_table("interview_questions") as batch:
        batch.drop_column("asked_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("interview_prefs")
