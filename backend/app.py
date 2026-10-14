"""Application entry point used by Flask CLI and WSGI servers."""

from . import app, create_app

__all__ = ["app", "create_app"]
