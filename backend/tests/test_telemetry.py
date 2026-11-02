from types import SimpleNamespace

from backend import ai_service, telemetry, voice_service
from backend.extensions import db
from backend.models import AICall
from backend.tests.conftest import csrf_headers

REVIEW = '{"strengths":["Specific"],"improvements":["Add impact"],"score":7}'


def _provider(monkeypatch, *outcomes):
    """Fake Groq: each call takes the next outcome (an exception to raise, or JSON content to return)."""
    queue = list(outcomes)

    def create(_prompt, _temperature):
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))],
                               usage=SimpleNamespace(prompt_tokens=500, completion_tokens=200))

    monkeypatch.setattr(ai_service, "AI_ENABLED", True)
    monkeypatch.setattr(ai_service, "_create_completion", create)


def _answer(client, interview_id, text="I shipped the release"):
    return client.post(f"/api/v1/interviews/{interview_id}/answers", json={"answer": text},
                       headers=csrf_headers(client))


def test_successful_and_failed_ai_calls_are_recorded(signed_in, monkeypatch, app):
    _provider(monkeypatch, REVIEW, TimeoutError("slow"))
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"},
                                  headers=csrf_headers(signed_in)).json["interview"]["id"]
    assert _answer(signed_in, interview_id).status_code == 200
    assert _answer(signed_in, interview_id).status_code == 200  # Provider fails; candidate still gets feedback.

    calls = db.session.scalars(db.select(AICall).order_by(AICall.id)).all()
    assert [(c.kind, c.status) for c in calls] == [
        ("answer_review", "ok"), ("answer_review", "error"), ("answer_review", "fallback")]
    assert (calls[0].prompt_tokens, calls[0].completion_tokens) == (500, 200)
    assert calls[0].latency_ms is not None and calls[1].error == "TimeoutError"


def test_fallback_is_not_counted_when_ai_is_not_configured(signed_in, monkeypatch, app):
    monkeypatch.setattr(ai_service, "AI_ENABLED", False)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"},
                                  headers=csrf_headers(signed_in)).json["interview"]["id"]
    assert _answer(signed_in, interview_id).status_code == 200
    assert db.session.scalar(db.select(db.func.count()).select_from(AICall)) == 0


def test_metrics_are_admin_only_and_summarize_calls(client, signed_in, app):
    for latency in (100, 200, 300, 400):
        db.session.add(AICall(kind="evaluate", provider="groq", status="ok", latency_ms=latency,
                              prompt_tokens=600, completion_tokens=250))
    db.session.add_all([AICall(kind="evaluate", provider="groq", status="error", latency_ms=25000),
                        AICall(kind="evaluate", provider="groq", status="fallback"),
                        AICall(kind="tts", provider="elevenlabs", status="ok", latency_ms=300),
                        AICall(kind="tts", provider="elevenlabs", status="cached", latency_ms=0)])
    db.session.commit()

    assert signed_in.get("/api/v1/admin/metrics").status_code == 404
    signed_in.post("/api/v1/auth/logout", headers=csrf_headers(signed_in))
    signed_in.post("/api/v1/auth/register", json={"name": "Ops", "email": "Admin@example.com",
                                                  "password": "a-very-long-password"},
                   headers={"Origin": "http://localhost:3000"})
    assert signed_in.get("/api/v1/admin/metrics?days=0").status_code == 400
    body = signed_in.get("/api/v1/admin/metrics?days=7").json
    by_kind = {item["kind"]: item for item in body["kinds"]}

    evaluate = by_kind["evaluate"]
    assert (evaluate["ok"], evaluate["errors"], evaluate["fallbacks"]) == (4, 1, 1)
    assert evaluate["success_rate"] == 0.8
    assert evaluate["latency_ms"] == {"p50": 200, "p95": 400, "max": 400}  # Failed calls excluded.
    assert (evaluate["avg_prompt_tokens"], evaluate["avg_completion_tokens"]) == (600, 250)
    assert by_kind["tts"]["cache_hit_rate"] == 0.5


def test_voice_calls_record_latency_and_cache_hits(app, monkeypatch):
    from collections import OrderedDict

    monkeypatch.setattr(voice_service, "VOICE_ENABLED", True)
    monkeypatch.setattr(voice_service, "_speech_cache", OrderedDict())
    monkeypatch.setattr(voice_service, "_send", lambda request: b"ID3audio")
    with app.test_request_context():
        voice_service.synthesize("Tell me about a hard bug.")
        voice_service.synthesize("Tell me about a hard bug.")
        telemetry.flush(app.response_class())
    statuses = [c.status for c in db.session.scalars(db.select(AICall).order_by(AICall.id))]
    assert statuses == ["ok", "cached"]


def test_flush_does_not_commit_changes_a_route_left_pending(app):
    with app.test_request_context():
        db.session.add(AICall(kind="stray", provider="none", status="ok"))  # Uncommitted route change.
        telemetry.record("evaluate", "groq", "ok", 120)
        telemetry.flush(app.response_class())
    assert [c.kind for c in db.session.scalars(db.select(AICall))] == ["evaluate"]


def test_recording_outside_a_request_is_a_no_op():
    telemetry.record("evaluate", "groq", "ok", 10)  # Scripts and benchmarks run without an app context.
