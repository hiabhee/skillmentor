"""Add role-based tech interviews, adaptive questions, and proctoring events."""

from alembic import op
import sqlalchemy as sa

revision = "20261014_0002"
down_revision = "20261002_0001"
branch_labels = None
depends_on = None

def _interview_columns():
    return [
        sa.Column("role", sa.String(80)),
        sa.Column("level", sa.String(20)),
        sa.Column("mode", sa.String(20)),
        sa.Column("voice_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("proctored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("focus", sa.Text()),
        sa.Column("plan_json", sa.Text()),
        sa.Column("report_json", sa.Text()),
    ]


def upgrade():
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("interviews")}
    with op.batch_alter_table("interviews") as batch:
        for column in _interview_columns():
            if column.name not in existing:
                batch.add_column(column)
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("intro", sa.Text()),
        sa.Column("is_follow_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("interview_id", "position", name="uq_question_interview_position"),
    )
    op.create_index("ix_interview_questions_interview_id", "interview_questions", ["interview_id"])
    op.create_table(
        "proctor_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_position", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_proctor_events_interview_id", "proctor_events", ["interview_id"])


def downgrade():
    op.drop_index("ix_proctor_events_interview_id", table_name="proctor_events")
    op.drop_table("proctor_events")
    op.drop_index("ix_interview_questions_interview_id", table_name="interview_questions")
    op.drop_table("interview_questions")
    with op.batch_alter_table("interviews") as batch:
        for column in reversed(_interview_columns()):
            batch.drop_column(column.name)
