"""The server, not the browser, owns setup choices, drafts and the assessment answer clock."""

import json
from datetime import timedelta

import pytest

import backend.routes as routes
from backend import ai_service, tech_interview
from backend.extensions import db
from backend.models import InterviewQuestion
from backend.tests.conftest import csrf_headers

PLAN = [{"question": f"Question {index}?", "category": "fundamentals"} for index in range(8)]


@pytest.fixture
def planned(monkeypatch):
    monkeypatch.setattr(tech_interview, "plan_interview", lambda role, level, focus, mode, key: (PLAN[:tech_interview.QUESTION_COUNT[mode]], True))
    monkeypatch.setattr(tech_interview, "evaluate_turn", lambda **kwargs: {
        "score": 7.0, "strengths": ["Clear"], "improvements": ["Depth"], "model_answer": [], "reaction": "Thanks.",
        "follow_up": None, "automated": True})


def _create(client, **overrides):
    body = {"type": "tech", "role": "backend", "level": "mid", "mode": "practice", **overrides}
    return client.post("/api/v1/interviews", json=body, headers=csrf_headers(client))


def test_options_expose_server_rules_and_default_preferences(signed_in):
    body = signed_in.get("/api/v1/interview-options").json
    assert body["modes"]["practice"] == {"questions": 6, "minutes": 15, "answer_seconds": 0, "camera_required": False}
    assert body["modes"]["assessment"]["questions"] == 8
    assert body["modes"]["assessment"]["answer_seconds"] == routes.ASSESSMENT_ANSWER_SECONDS
    assert body["max_focus"] == 3
    assert body["preferences"] == routes.PREF_DEFAULTS


def test_preferences_persist_and_are_validated(signed_in, client):
    headers = csrf_headers(signed_in)
    saved = signed_in.put("/api/v1/preferences", json={"role": "frontend", "level": "senior", "focus": ["React", " TypeScript "],
                                                       "autoplay": False}, headers=headers)
    assert saved.status_code == 200
    prefs = signed_in.get("/api/v1/interview-options").json["preferences"]
    assert (prefs["role"], prefs["level"], prefs["focus"], prefs["autoplay"]) == ("frontend", "senior", ["React", "TypeScript"], False)
    assert prefs["mode"] == "practice"  # Untouched fields keep their saved or default value.

    for bad in ({"role": "astronaut"}, {"level": ["mid"]}, {"focus": ["a", "b", "c", "d"]}, {"voice_only": "yes"}):
        response = signed_in.put("/api/v1/preferences", json=bad, headers=headers)
        assert response.status_code == 400, bad
    assert signed_in.get("/api/v1/interview-options").json["preferences"]["role"] == "frontend"


def test_starting_an_interview_remembers_the_setup(signed_in, planned):
    assert _create(signed_in, role="custom", custom_role="Platform Engineer", level="staff", mode="assessment",
                   focus="Kubernetes, Observability", voice_only=False, proctored=True).status_code == 201
    prefs = signed_in.get("/api/v1/interview-options").json["preferences"]
    assert prefs["role"] == "custom" and prefs["custom_role"] == "Platform Engineer"
    assert (prefs["level"], prefs["mode"], prefs["voice_only"]) == ("staff", "assessment", False)
    assert prefs["focus"] == ["Kubernetes", "Observability"]
    assert prefs["camera"] is True  # Assessments force the camera, so they never overwrite the practice choice.


def test_voice_only_is_refused_when_voice_is_not_configured(signed_in, planned, monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", False)
    interview_id = _create(signed_in, voice_only=True).json["interview"]["id"]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["voice_only"] is False
    # The candidate's choice is still remembered for when voice becomes available.
    assert signed_in.get("/api/v1/interview-options").json["preferences"]["voice_only"] is True


def test_drafts_survive_reload_and_clear_on_submit(signed_in, planned):
    headers = csrf_headers(signed_in)
    interview_id = _create(signed_in).json["interview"]["id"]
    url = f"/api/v1/interviews/{interview_id}"
    assert signed_in.put(f"{url}/draft", json={"position": 0, "text": "Half an answer"}, headers=headers).status_code == 200
    assert signed_in.put(f"{url}/draft", json={"position": 0, "text": "Half an answer, edited"}, headers=headers).status_code == 200
    assert signed_in.get(url).json["interview"]["draft"] == {"position": 0, "text": "Half an answer, edited"}

    assert signed_in.put(f"{url}/draft", json={"position": 3, "text": "Wrong question"}, headers=headers).status_code == 409
    assert signed_in.put(f"{url}/draft", json={"position": "0", "text": "x"}, headers=headers).status_code == 400

    signed_in.post(f"{url}/turns", json={"answer": "Final answer", "position": 0}, headers=headers)
    assert signed_in.get(url).json["interview"]["draft"] is None
    assert signed_in.put(f"{url}/draft", json={"position": 0, "text": "Late edit"}, headers=headers).status_code == 409


def test_clearing_a_draft_deletes_it(signed_in, planned):
    headers = csrf_headers(signed_in)
    url = f"/api/v1/interviews/{_create(signed_in).json['interview']['id']}"
    signed_in.put(f"{url}/draft", json={"position": 0, "text": "Something"}, headers=headers)
    signed_in.put(f"{url}/draft", json={"position": 0, "text": "   "}, headers=headers)
    assert signed_in.get(url).json["interview"]["draft"] is None


def test_round1_and_coding_drafts_use_their_open_position(signed_in, monkeypatch):
    monkeypatch.setattr(ai_service, "AI_ENABLED", False)
    headers = csrf_headers(signed_in)
    round1 = signed_in.post("/api/v1/interviews", json={"type": "round1"}, headers=headers).json["interview"]["id"]
    assert signed_in.put(f"/api/v1/interviews/{round1}/draft", json={"position": 0, "text": "About me"}, headers=headers).status_code == 200
    signed_in.post(f"/api/v1/interviews/{round1}/answers", json={"answer": "About me"}, headers=headers)
    assert signed_in.get(f"/api/v1/interviews/{round1}").json["interview"]["draft"] is None

    coding = signed_in.post("/api/v1/interviews", json={"type": "coding"}, headers=headers).json["interview"]["id"]
    code = "def solve(nums):\n    return sorted(nums)\n"
    assert signed_in.put(f"/api/v1/interviews/{coding}/draft", json={"position": 0, "text": code}, headers=headers).status_code == 200
    assert signed_in.get(f"/api/v1/interviews/{coding}").json["interview"]["draft"]["text"] == code


def test_assessment_clock_starts_on_join_and_survives_reload(signed_in, planned, app):
    headers = csrf_headers(signed_in)
    interview_id = _create(signed_in, mode="assessment").json["interview"]["id"]
    url = f"/api/v1/interviews/{interview_id}"
    question = signed_in.get(url).json["interview"]["current_question"]
    assert question["started"] is False and question["seconds_left"] == routes.ASSESSMENT_ANSWER_SECONDS

    assert signed_in.post(f"{url}/join", headers=headers).status_code == 200
    with app.app_context():
        asked = InterviewQuestion.query.filter_by(interview_id=interview_id, position=0).one()
        asked.asked_at -= timedelta(seconds=100)
        db.session.commit()
    signed_in.post(f"{url}/join", headers=headers)  # Rejoining after a reload must not restart the clock.
    left = signed_in.get(url).json["interview"]["current_question"]["seconds_left"]
    assert routes.ASSESSMENT_ANSWER_SECONDS - 102 <= left <= routes.ASSESSMENT_ANSWER_SECONDS - 99


def test_first_assessment_answer_is_checked_for_lateness(signed_in, planned, app):
    headers = csrf_headers(signed_in)
    interview_id = _create(signed_in, mode="assessment").json["interview"]["id"]
    signed_in.post(f"/api/v1/interviews/{interview_id}/join", headers=headers)
    with app.app_context():
        asked = InterviewQuestion.query.filter_by(interview_id=interview_id, position=0).one()
        asked.asked_at -= timedelta(seconds=routes.ASSESSMENT_ANSWER_SECONDS + routes.ASSESSMENT_GRACE_SECONDS + 20)
        db.session.commit()
    signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Slow"}, headers=headers)
    integrity = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["integrity"]
    assert integrity["events"]["late_answer"]["count"] == 1


def test_practice_questions_have_no_clock(signed_in, planned):
    interview_id = _create(signed_in).json["interview"]["id"]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["current_question"]["seconds_left"] is None


def test_model_list_markers_are_stripped_and_strong_answers_need_no_improvements(monkeypatch):
    monkeypatch.setattr(ai_service, "AI_ENABLED", True)
    monkeypatch.setattr(ai_service, "_call_model", lambda *args, **kwargs: json.dumps({
        "score": 9, "strengths": ["- Precise numbers"], "improvements": [],
        "model_answer": ["- Measure first", "2. Cache hot reads", "• Invalidate on write"], "reaction": "Great.", "follow_up": None}))
    result = tech_interview.evaluate_turn(role="Backend Engineer", level="mid", mode="practice", question="Q?",
                                         category="fundamentals", answer="A strong answer", is_follow_up=False,
                                         follow_up_allowed=False, position=0)
    assert result["automated"] is True
    assert result["strengths"] == ["Precise numbers"] and result["improvements"] == []
    assert result["model_answer"] == ["Measure first", "Cache hot reads", "Invalidate on write"]
