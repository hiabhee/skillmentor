from backend import create_app
from backend.extensions import db
from backend.tests.conftest import TestConfig

SECRET = "a-proxy-secret-that-is-at-least-32-characters"


class SecretConfig(TestConfig):
    API_PROXY_SECRET = SECRET


def _client():
    app = create_app(SecretConfig)
    with app.app_context():
        db.create_all()
    return app, app.test_client()


def test_requests_without_the_proxy_secret_are_refused():
    app, client = _client()
    origin = {"Origin": "http://localhost:3000"}
    assert client.post("/api/v1/auth/demo", headers=origin).status_code == 403
    assert client.post("/api/v1/auth/demo", headers={**origin, "X-Proxy-Secret": "wrong"}).status_code == 403
    assert client.get("/api/v1/auth/me", headers={"X-Proxy-Secret": "wrong"}).json["error"]["code"] == "forbidden"
    assert client.post("/api/v1/auth/demo", headers={**origin, "X-Proxy-Secret": SECRET}).status_code == 200
    with app.app_context():
        db.drop_all()


def test_health_checks_stay_open_for_the_platform():
    app, client = _client()
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200
    with app.app_context():
        db.drop_all()
