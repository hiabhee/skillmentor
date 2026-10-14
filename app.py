"""Compatibility WSGI entry point. The production application is the backend API."""

from backend.app import app

__all__ = ["app"]
