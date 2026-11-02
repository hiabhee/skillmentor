import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env", override=False)


def _database_url():
    value = os.getenv("DATABASE_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    if value:
        return value
    return "sqlite:///" + str(ROOT_DIR / "interview.db")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    ENVIRONMENT = os.getenv("APP_ENV", "development").lower()
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite:"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"check_same_thread": False, "timeout": 30}
    MAX_CONTENT_LENGTH = 1024 * 1024
    SESSION_COOKIE_NAME = "skillmentor_session"
    CSRF_COOKIE_NAME = "skillmentor_csrf"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_PATH = "/"
    SESSION_TTL_SECONDS = 60 * 60 * 12
    LOGIN_MAX_ATTEMPTS = 8
    LOGIN_WINDOW_SECONDS = 15 * 60
    AI_REVIEW_TIMEOUT_SECONDS = 25
    # (requests, window in seconds) for each user; the demo account shares one budget.
    AI_RATE_LIMITS = {"interview": (12, 3600), "answer": (150, 3600), "transcription": (150, 3600)}
    WEB_ORIGINS = tuple(
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "WEB_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if origin.strip()
    )
    # Shared secret the web app's /api/v1 proxy sends in X-Proxy-Secret. When set, the API only answers
    # requests that carry it, so a publicly reachable API (e.g. frontend on Vercel) can't be called directly.
    API_PROXY_SECRET = os.getenv("API_PROXY_SECRET", "").strip()
    # Accounts that may read /api/v1/admin/metrics (comma-separated emails).
    ADMIN_EMAILS = frozenset(
        email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()
    )
    MIGRATIONS_DIR = str(ROOT_DIR / "backend" / "migrations")
    JSON_SORT_KEYS = False

    @classmethod
    def validate(cls):
        if cls.ENVIRONMENT == "production":
            secret = cls.SECRET_KEY
            if len(secret) < 32:
                raise RuntimeError("SECRET_KEY must be configured with at least 32 characters in production")
            if len(cls.API_PROXY_SECRET) < 32:
                raise RuntimeError("API_PROXY_SECRET must be configured with at least 32 characters in production")
            if cls.SQLALCHEMY_DATABASE_URI.startswith("sqlite:"):
                raise RuntimeError("DATABASE_URL must point to PostgreSQL in production")
            parsed = urlsplit(cls.SQLALCHEMY_DATABASE_URI)
            if not parsed.hostname:
                raise RuntimeError("DATABASE_URL is invalid")


Config.validate()
