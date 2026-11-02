import pytest

from backend import create_app
from backend.extensions import db


class TestConfig:
    TESTING = True
    SECRET_KEY = "unit-test-secret-key-that-is-long-enough"
    ENVIRONMENT = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}
    MAX_CONTENT_LENGTH = 1024 * 1024
    SESSION_COOKIE_NAME = "skillmentor_session"
    CSRF_COOKIE_NAME = "skillmentor_csrf"
    SESSION_COOKIE_SECURE = False
    SESSION_TTL_SECONDS = 3600
    LOGIN_MAX_ATTEMPTS = 8
    LOGIN_WINDOW_SECONDS = 900
    WEB_ORIGINS = ("http://localhost:3000",)
    MIGRATIONS_DIR = "backend/migrations"
    ADMIN_EMAILS = frozenset({"admin@example.com"})
    AI_RATE_LIMITS = {"interview": (50, 3600), "answer": (200, 3600), "transcription": (200, 3600)}


@pytest.fixture
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def signed_in(client):
    response = client.post("/api/v1/auth/register", json={
        "name": "Test Candidate",
        "email": "candidate@example.com",
        "password": "a-very-long-password",
    }, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    return client


def csrf_headers(client, origin="http://localhost:3000"):
    cookie = client.get_cookie("skillmentor_csrf")
    headers = {"Origin": origin}
    if cookie:
        headers["X-CSRF-Token"] = cookie.value
    return headers
