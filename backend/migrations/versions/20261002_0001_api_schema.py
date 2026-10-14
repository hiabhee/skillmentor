"""Create API session tables and extend the legacy interview schema."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0001"
down_revision = None
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    tables = _tables()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(320), nullable=False, unique=True),
            sa.Column("password", sa.String(255), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("full_name", sa.String(160)),
            sa.Column("bio", sa.Text()),
            sa.Column("profile_photo_path", sa.String(500)),
        )
        tables.add("users")
    if "interviews" not in tables:
        op.create_table(
            "interviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("interview_type", sa.String(32), nullable=False),
            sa.Column("difficulty", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        )
        tables.add("interviews")
    elif "status" not in _columns("interviews"):
        op.add_column("interviews", sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"))

    if "responses" not in tables:
        op.create_table(
            "responses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("interview_id", sa.Integer(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("feedback", sa.Text()),
            sa.Column("score", sa.Float()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("question_position", sa.Integer()),
        )
        tables.add("responses")
    elif "question_position" not in _columns("responses"):
        op.add_column("responses", sa.Column("question_position", sa.Integer(), nullable=True))

    if "coding_challenges" not in tables:
        op.create_table(
            "coding_challenges",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("interview_id", sa.Integer(), sa.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("challenge_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("interview_id", "position", name="uq_challenge_interview_position"),
        )
        tables.add("coding_challenges")

    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("token_hash", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("csrf_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime()),
        )
        tables.add("auth_sessions")
    if "login_attempts" not in tables:
        op.create_table(
            "login_attempts",
            sa.Column("identity_hash", sa.String(64), primary_key=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("window_started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("blocked_until", sa.DateTime()),
        )

    indexes = {
        "interviews": [("ix_interviews_user_id", ["user_id"], False)],
        "responses": [
            ("ix_responses_user_id", ["user_id"], False),
            ("ix_responses_interview_id", ["interview_id"], False),
            ("uq_response_interview_position", ["interview_id", "question_position"], True),
        ],
        "coding_challenges": [
            ("ix_coding_challenges_interview_id", ["interview_id"], False),
            ("uq_challenge_interview_position", ["interview_id", "position"], True),
        ],
        "auth_sessions": [
            ("ix_auth_sessions_user_id", ["user_id"], False),
            ("ix_auth_sessions_expires_at", ["expires_at"], False),
        ],
        "login_attempts": [],
    }
    for table, definitions in indexes.items():
        existing = _indexes(table)
        for name, columns, unique in definitions:
            if name not in existing:
                op.create_index(name, table, columns, unique=unique)

    # Preserve the order of old responses so a partially completed session continues correctly.
    connection = op.get_bind()
    interviews = connection.execute(sa.text("SELECT id, interview_type FROM interviews ORDER BY id")).all()
    for interview_id, interview_type in interviews:
        rows = connection.execute(
            sa.text("SELECT id, question_position FROM responses WHERE interview_id=:id ORDER BY created_at, id"),
            {"id": interview_id},
        ).all()
        for position, row in enumerate(rows):
            if row.question_position is None:
                connection.execute(sa.text("UPDATE responses SET question_position=:position WHERE id=:id"),
                                   {"position": position, "id": row.id})
        needed = 10 if interview_type == "round1" else 3 if interview_type == "round2_ai" else None
        if needed is not None and len(rows) >= needed:
            connection.execute(sa.text("UPDATE interviews SET status='completed' WHERE id=:id"), {"id": interview_id})


def downgrade():
    # Keep user and practice history tables intact during rollback.
    for name, table in [
        ("uq_response_interview_position", "responses"),
        ("ix_responses_user_id", "responses"),
        ("ix_responses_interview_id", "responses"),
        ("ix_interviews_user_id", "interviews"),
        ("ix_coding_challenges_interview_id", "coding_challenges"),
        ("uq_challenge_interview_position", "coding_challenges"),
        ("ix_auth_sessions_user_id", "auth_sessions"),
        ("ix_auth_sessions_expires_at", "auth_sessions"),
    ]:
        if table in _tables() and name in _indexes(table):
            op.drop_index(name, table_name=table)
    tables = _tables()
    if "auth_sessions" in tables:
        op.drop_table("auth_sessions")
    if "login_attempts" in tables:
        op.drop_table("login_attempts")
    if "responses" in _tables() and "question_position" in _columns("responses"):
        with op.batch_alter_table("responses") as batch:
            batch.drop_column("question_position")
    if "interviews" in _tables() and "status" in _columns("interviews"):
        with op.batch_alter_table("interviews") as batch:
            batch.drop_column("status")
