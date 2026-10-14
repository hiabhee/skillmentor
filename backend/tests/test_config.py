import pytest

from backend.config import Config


def production_config(monkeypatch, url):
    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "SECRET_KEY", "a-production-secret-that-is-at-least-32-chars")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", url)


def test_production_rejects_missing_or_short_session_secrets(monkeypatch):
    production_config(monkeypatch, "postgresql+psycopg://app:secret@db.internal/skillmentor")
    monkeypatch.setattr(Config, "SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        Config.validate()


def test_production_rejects_sqlite(monkeypatch):
    production_config(monkeypatch, "sqlite:////tmp/production.db")
    with pytest.raises(RuntimeError, match="must point to PostgreSQL"):
        Config.validate()


def test_production_accepts_a_valid_postgres_url(monkeypatch):
    production_config(monkeypatch, "postgresql+psycopg://app:secret@db.internal/skillmentor")
    Config.validate()
