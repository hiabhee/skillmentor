"""Flask API application factory. No HTML templates or static frontend are served here."""

import json

import click
from flask import Flask, jsonify
from flask_migrate import Migrate
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import db

migrate = Migrate()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIR"])

    from . import models  # noqa: F401 - register SQLAlchemy models before migrations.
    from .routes import api

    from . import telemetry

    app.register_blueprint(api, url_prefix="/api/v1")
    app.after_request(telemetry.flush)

    @app.cli.command("ai-metrics")
    @click.option("--days", default=7, show_default=True, type=click.IntRange(1, 365))
    def ai_metrics(days):
        """Print AI and voice call metrics for the last N days."""
        click.echo(json.dumps(telemetry.summarize(days), indent=2))

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "Resource not found."}}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"error": {"code": "method_not_allowed", "message": "Method not allowed."}}), 405

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": {"code": "request_too_large", "message": "Request body is too large."}}), 413

    @app.errorhandler(HTTPException)
    def http_error(error):
        code = error.name.lower().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": error.description}}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unhandled API error", exc_info=error)
        return jsonify({"error": {"code": "internal_error", "message": "An unexpected server error occurred."}}), 500

    return app


app = create_app()
