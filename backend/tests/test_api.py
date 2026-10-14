import json

import pytest

from backend.extensions import db
from backend.models import AuthSession, Interview, Response, User
from backend.tests.conftest import csrf_headers
import backend.routes as routes


def test_liveness_and_readiness(client):
    assert client.get("/api/v1/health/live").json == {"status": "ok"}
    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json["database"] == "ok"


def test_register_normalizes_email_and_sets_opaque_cookies(client, app):
    response = client.post("/api/v1/auth/register", json={
        "name": "  Rowan  ", "email": " Rowan@Example.com ", "password": "long-enough-password",
    }, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.json["user"]["email"] == "rowan@example.com"
    assert client.get_cookie("skillmentor_session").http_only is True
    with app.app_context():
        user = User.query.one()
        auth = AuthSession.query.one()
        assert user.password != "long-enough-password"
        assert auth.token_hash != client.get_cookie("skillmentor_session").value


def test_registration_validation_and_duplicate_email(client):
    too_short = client.post("/api/v1/auth/register", json={"name": "x", "email": "a@b.co", "password": "short"}, headers={"Origin": "http://localhost:3000"})
    assert too_short.status_code == 400
    first = client.post("/api/v1/auth/register", json={"name": "Test", "email": "a@b.co", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    duplicate = client.post("/api/v1/auth/register", json={"name": "Test", "email": "A@B.CO", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json["error"]["code"] == "email_exists"


def test_allowed_origin_and_csrf_are_required_for_mutations(signed_in):
    denied_origin = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers={"Origin": "https://evil.example"})
    missing_csrf = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers={"Origin": "http://localhost:3000"})
    assert denied_origin.status_code == 403
    assert denied_origin.json["error"]["code"] == "origin_not_allowed"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json["error"]["code"] == "csrf_failed"


def test_login_rate_limit_and_logout_revocation(client, app):
    client.post("/api/v1/auth/register", json={"name": "Test", "email": "person@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    for _ in range(8):
        failed = client.post("/api/v1/auth/login", json={"email": "PERSON@example.com", "password": "bad"}, headers={"Origin": "http://localhost:3000"})
        assert failed.status_code == 401
    limited = client.post("/api/v1/auth/login", json={"email": "person@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    assert limited.status_code == 429
    with app.app_context():
        assert AuthSession.query.one().revoked_at is not None


def test_login_and_me_returns_only_safe_user_fields(client):
    client.post("/api/v1/auth/register", json={"name": "Test", "email": "person@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    signed = client.post("/api/v1/auth/login", json={"email": "person@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    me = client.get("/api/v1/auth/me")
    assert signed.status_code == 200
    assert me.status_code == 200
    assert "password" not in me.json["user"]


def test_expired_or_missing_session_is_unauthorized(client):
    assert client.get("/api/v1/dashboard").status_code == 401


def test_interview_answers_complete_in_order_and_aggregate(signed_in, monkeypatch, app):
    monkeypatch.setattr(routes, "review_interview_answer", lambda question, answer: {
        "strengths": ["Specific context"], "improvements": ["Add the impact"], "score": 8.0, "automated": True,
    })
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    interview_id = created.json["interview"]["id"]
    assert created.status_code == 201
    for index in range(10):
        response = signed_in.post(f"/api/v1/interviews/{interview_id}/answers", json={"answer": f"Example {index}"}, headers=headers)
        assert response.status_code == 200
        assert response.json["completed"] is (index == 9)
        if index < 9:
            assert response.json["next_question"]["position"] == index + 1
    detail = signed_in.get(f"/api/v1/interviews/{interview_id}")
    assert detail.json["interview"]["status"] == "completed"
    assert len(detail.json["interview"]["responses"]) == 10
    assert detail.json["interview"]["average_score"] == 8
    repeated = signed_in.post(f"/api/v1/interviews/{interview_id}/answers", json={"answer": "late"}, headers=headers)
    assert repeated.status_code == 409
    with app.app_context():
        assert Response.query.filter_by(interview_id=interview_id).count() == 10


def test_answer_requires_text_or_explicit_skip(signed_in):
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    answer = signed_in.post(f"/api/v1/interviews/{created.json['interview']['id']}/answers", json={"answer": "  "}, headers=headers)
    skipped = signed_in.post(f"/api/v1/interviews/{created.json['interview']['id']}/answers", json={"skip": True}, headers=headers)
    assert answer.status_code == 400
    assert skipped.status_code == 200


def test_response_length_limit(signed_in):
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    too_long = signed_in.post(f"/api/v1/interviews/{created.json['interview']['id']}/answers", json={"answer": "x" * 20001}, headers=headers)
    assert too_long.status_code == 413


def test_coding_challenges_hide_solution_and_submissions_are_ordered(signed_in, monkeypatch, app):
    monkeypatch.setattr(routes, "review_code_submission", lambda problem, code: {
        "is_correct": False, "score": 4.0, "summary": "The edge case fails.", "strengths": [],
        "improvements": ["Handle duplicate values."], "show_solution": False, "automated": True,
    })
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "coding"}, headers=headers)
    interview_id = created.json["interview"]["id"]
    challenge = created.json["challenge"]
    assert "solution_code" not in challenge
    assert "test_cases" not in challenge
    skipped = signed_in.post(f"/api/v1/interviews/{interview_id}/submissions", json={"position": 1, "code": "print(1)"}, headers=headers)
    assert skipped.status_code == 409
    for position in range(3):
        submitted = signed_in.post(f"/api/v1/interviews/{interview_id}/submissions", json={"position": position, "code": "print(1)"}, headers=headers)
        assert submitted.status_code == 200
        assert submitted.json["completed"] is (position == 2)
    detail = signed_in.get(f"/api/v1/interviews/{interview_id}")
    assert detail.json["interview"]["status"] == "completed"
    assert len(detail.json["interview"]["responses"]) == 3
    repeated = signed_in.post(f"/api/v1/interviews/{interview_id}/submissions", json={"position": 0, "code": "again"}, headers=headers)
    assert repeated.status_code == 409
    assert repeated.json["error"]["code"] == "submission_exists"
    with app.app_context():
        stored = Response.query.filter_by(interview_id=interview_id).first()
        assert json.loads(stored.feedback)["score"] == 4.0


def test_ai_failure_saves_answer_with_transparent_fallback(signed_in, monkeypatch, app):
    def fail(*_args):
        raise TimeoutError("provider timed out")
    monkeypatch.setattr(routes, "review_interview_answer", fail)
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    result = signed_in.post(f"/api/v1/interviews/{created.json['interview']['id']}/answers", json={"answer": "I led a team project and improved delivery by 20 percent."}, headers=headers)
    assert result.status_code == 200
    assert result.json["feedback"]["automated"] is False
    with app.app_context():
        assert Response.query.count() == 1


def test_user_cannot_read_or_mutate_another_users_interview(client):
    client.post("/api/v1/auth/register", json={"name": "First", "email": "first@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    headers = csrf_headers(client)
    created = client.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    interview_id = created.json["interview"]["id"]
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    client.post("/api/v1/auth/register", json={"name": "Second", "email": "second@example.com", "password": "long-enough-password"}, headers={"Origin": "http://localhost:3000"})
    assert client.get(f"/api/v1/interviews/{interview_id}").status_code == 404
    attempt = client.post(f"/api/v1/interviews/{interview_id}/answers", json={"answer": "not mine"}, headers=csrf_headers(client))
    assert attempt.status_code == 404


def test_history_analytics_profile_and_achievements(signed_in, monkeypatch):
    monkeypatch.setattr(routes, "review_interview_answer", lambda question, answer: {
        "strengths": ["Clear"], "improvements": ["Add detail"], "score": 8.5, "automated": True,
    })
    headers = csrf_headers(signed_in)
    created = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers)
    response = signed_in.post(f"/api/v1/interviews/{created.json['interview']['id']}/answers", json={"answer": "I built a useful feature."}, headers=headers)
    assert response.status_code == 200
    history = signed_in.get("/api/v1/history")
    analytics = signed_in.get("/api/v1/analytics")
    awards = signed_in.get("/api/v1/achievements")
    assert history.json["responses"][0]["question"] == "Tell me about yourself."
    assert analytics.json["average_score"] == 8.5
    assert awards.status_code == 200
    profile = signed_in.put("/api/v1/profile", json={"name": "Rowan Candidate", "bio": "Building useful things."}, headers=headers)
    assert profile.json["user"]["name"] == "Rowan Candidate"
    item_id = history.json["responses"][0]["id"]
    assert signed_in.delete(f"/api/v1/history/{item_id}", headers=headers).status_code == 200
    assert signed_in.get("/api/v1/history").json["responses"] == []


@pytest.mark.parametrize("body", [[], None, {"name": [], "email": "x@example.com", "password": "long-enough-password"}])
def test_invalid_payloads_return_json_errors(client, body):
    response = client.post("/api/v1/auth/register", json=body, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 400
    assert "error" in response.json


def test_unknown_api_route_has_json_error(client):
    response = client.get("/api/v1/no-such-route")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"


def _voice_on(monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", True)


def test_question_audio_is_synthesized_only_for_fixed_questions(signed_in, monkeypatch):
    _voice_on(monkeypatch)
    spoken = []
    monkeypatch.setattr(routes.voice_service, "synthesize", lambda text: spoken.append(text) or b"ID3audio")
    headers = csrf_headers(signed_in)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["voice_enabled"] is True
    result = signed_in.get(f"/api/v1/interviews/{interview_id}/questions/0/audio")
    assert result.status_code == 200
    assert result.mimetype == "audio/mpeg"
    assert result.data == b"ID3audio"
    assert spoken == [routes.ROUND1_QUESTIONS[0]]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}/questions/10/audio").status_code == 404


def test_voice_endpoints_report_unconfigured_provider(signed_in, monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", False)
    headers = csrf_headers(signed_in)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["voice_enabled"] is False
    assert signed_in.get(f"/api/v1/interviews/{interview_id}/questions/0/audio").status_code == 503


def test_transcription_returns_text_and_validates_upload(signed_in, monkeypatch):
    import io
    _voice_on(monkeypatch)
    calls = []
    monkeypatch.setattr(routes.voice_service, "transcribe", lambda audio, name, kind: calls.append((audio, kind)) or "I led the release.")
    headers = csrf_headers(signed_in)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    url = f"/api/v1/interviews/{interview_id}/transcriptions"
    ok = signed_in.post(url, data={"audio": (io.BytesIO(b"webm-bytes"), "answer.webm", "audio/webm;codecs=opus")}, headers=headers, content_type="multipart/form-data")
    assert ok.status_code == 200
    assert ok.json == {"transcript": "I led the release."}
    assert calls == [(b"webm-bytes", "audio/webm")]
    assert signed_in.post(url, data={}, headers=headers, content_type="multipart/form-data").status_code == 400
    bad = signed_in.post(url, data={"audio": (io.BytesIO(b"x"), "a.txt", "text/plain")}, headers=headers, content_type="multipart/form-data")
    assert bad.status_code == 415
    no_csrf = signed_in.post(url, data={"audio": (io.BytesIO(b"x"), "a.webm", "audio/webm")}, headers={"Origin": "http://localhost:3000"}, content_type="multipart/form-data")
    assert no_csrf.status_code == 403


def test_transcription_accepts_audio_larger_than_json_limit(signed_in, monkeypatch):
    import io
    _voice_on(monkeypatch)
    monkeypatch.setattr(routes.voice_service, "transcribe", lambda audio, name, kind: str(len(audio)))
    headers = csrf_headers(signed_in)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    clip = b"0" * (3 * 1024 * 1024)
    result = signed_in.post(f"/api/v1/interviews/{interview_id}/transcriptions", data={"audio": (io.BytesIO(clip), "a.webm", "audio/webm")}, headers=headers, content_type="multipart/form-data")
    assert result.status_code == 200
    assert result.json["transcript"] == str(len(clip))


def test_transcription_provider_failure_is_reported(signed_in, monkeypatch):
    import io
    _voice_on(monkeypatch)
    def fail(*_args):
        raise routes.voice_service.VoiceError("down")
    monkeypatch.setattr(routes.voice_service, "transcribe", fail)
    headers = csrf_headers(signed_in)
    interview_id = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    result = signed_in.post(f"/api/v1/interviews/{interview_id}/transcriptions", data={"audio": (io.BytesIO(b"x"), "a.webm", "audio/webm")}, headers=headers, content_type="multipart/form-data")
    assert result.status_code == 502
    assert result.json["error"]["code"] == "transcription_failed"
