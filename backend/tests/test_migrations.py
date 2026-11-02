import sqlite3
from pathlib import Path

from flask_migrate import upgrade

from backend import create_app
from backend.tests.conftest import TestConfig


def test_legacy_upgrade_preserves_users_and_orders_responses(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, full_name TEXT, bio TEXT, profile_photo_path TEXT
        );
        CREATE TABLE interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            interview_type TEXT NOT NULL, difficulty TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, interview_id INTEGER NOT NULL,
            question TEXT NOT NULL, answer TEXT NOT NULL, feedback TEXT, score REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE coding_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT, interview_id INTEGER NOT NULL, position INTEGER NOT NULL,
            challenge_json TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(interview_id, position)
        );
        INSERT INTO users(id, email, password, name) VALUES (7, 'legacy@example.com', 'old-hash', 'Legacy Candidate');
        INSERT INTO interviews(id, user_id, interview_type, difficulty) VALUES (12, 7, 'round1', 'personal');
        INSERT INTO responses(id, user_id, interview_id, question, answer, score, created_at)
            VALUES (31, 7, 12, 'Tell me about yourself.', 'A', 7, '2026-01-01 10:00:00');
        INSERT INTO responses(id, user_id, interview_id, question, answer, score, created_at)
            VALUES (32, 7, 12, 'What are your hobbies?', 'B', 8, '2026-01-01 10:01:00');
    """)
    connection.commit()
    connection.close()

    class MigrationConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database}"
        MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migrations")

    app = create_app(MigrationConfig)
    with app.app_context():
        upgrade(directory=MigrationConfig.MIGRATIONS_DIR)
        upgrade(directory=MigrationConfig.MIGRATIONS_DIR)

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT email FROM users WHERE id=7").fetchone() == ("legacy@example.com",)
    assert connection.execute("SELECT status FROM interviews WHERE id=12").fetchone() == ("in_progress",)
    assert connection.execute("SELECT id, question_position FROM responses WHERE interview_id=12 ORDER BY id").fetchall() == [(31, 0), (32, 1)]
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("20261103_0005",)
    assert connection.execute("SELECT voice_only, proctored FROM interviews WHERE id=12").fetchone() == (0, 0)
    tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"interview_questions", "proctor_events", "rate_limit_buckets", "ai_calls", "answer_drafts"} <= tables
    connection.close()
