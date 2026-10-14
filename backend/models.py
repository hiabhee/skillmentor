from datetime import datetime, timezone

from .extensions import db


def utcnow():
    # Use timezone-aware UTC in PostgreSQL and normalize on SQLite reads.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), nullable=False, unique=True, index=True)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    full_name = db.Column(db.String(160))
    bio = db.Column(db.Text)
    profile_photo_path = db.Column(db.String(500))


class Interview(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_type = db.Column(db.String(32), nullable=False)
    difficulty = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    status = db.Column(db.String(20), nullable=False, default="in_progress", server_default="in_progress")
    # Tech interview settings; legacy personal and coding sessions leave these empty.
    role = db.Column(db.String(80))
    level = db.Column(db.String(20))
    mode = db.Column(db.String(20))
    voice_only = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    proctored = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    focus = db.Column(db.Text)
    plan_json = db.Column(db.Text)
    report_json = db.Column(db.Text)


class Response(db.Model):
    __tablename__ = "responses"
    __table_args__ = (
        db.UniqueConstraint("interview_id", "question_position", name="uq_response_interview_position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    feedback = db.Column(db.Text)
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    question_position = db.Column(db.Integer)


class InterviewQuestion(db.Model):
    """A question the interviewer has asked, including adaptive follow-ups."""

    __tablename__ = "interview_questions"
    __table_args__ = (
        db.UniqueConstraint("interview_id", "position", name="uq_question_interview_position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    question = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False)
    intro = db.Column(db.Text)
    is_follow_up = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ProctorEvent(db.Model):
    __tablename__ = "proctor_events"

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)
    duration_ms = db.Column(db.Integer, nullable=False, default=0)
    question_position = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class CodingChallenge(db.Model):
    __tablename__ = "coding_challenges"
    __table_args__ = (
        db.UniqueConstraint("interview_id", "position", name="uq_challenge_interview_position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    challenge_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"

    token_hash = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime)


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    identity_hash = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    blocked_until = db.Column(db.DateTime)
