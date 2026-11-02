import json

import pytest

import backend.routes as routes
from backend import tech_interview
from backend.models import Interview, InterviewQuestion
from backend.tests.conftest import csrf_headers

PLAN = [{"question": f"Question {index}?", "category": "fundamentals" if index % 2 else "system_design"} for index in range(8)]


def _evaluation(follow_up=None, score=7.0):
    return lambda **kwargs: {"score": score, "strengths": ["Clear"], "improvements": ["Add depth"], "model_answer": ["Point"],
                             "reaction": "Thanks.", "follow_up": follow_up if kwargs["follow_up_allowed"] else None, "automated": True}


@pytest.fixture
def planned(monkeypatch):
    monkeypatch.setattr(tech_interview, "plan_interview", lambda role, level, focus, mode, key: (PLAN[:tech_interview.QUESTION_COUNT[mode]], True))
    monkeypatch.setattr(tech_interview, "evaluate_turn", _evaluation())


def _create(client, **overrides):
    body = {"type": "tech", "role": "backend", "level": "mid", "mode": "practice", **overrides}
    return client.post("/api/v1/interviews", json=body, headers=csrf_headers(client))


def test_create_validates_role_level_and_mode(signed_in, planned):
    assert _create(signed_in, role="astronaut").status_code == 400
    assert _create(signed_in, role="custom", custom_role="x").status_code == 400
    assert _create(signed_in, level="wizard").status_code == 400
    assert _create(signed_in, mode="exam").status_code == 400
    assert _create(signed_in, focus="x" * 201).status_code == 400
    assert _create(signed_in, role="custom", custom_role="Platform Engineer").status_code == 201


def test_practice_flow_with_follow_up_feedback_and_report(signed_in, planned, monkeypatch, app):
    created = _create(signed_in, focus="  APIs   and caching ")
    interview_id = created.json["interview"]["id"]
    state = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]
    assert state["type"] == "tech" and state["role"] == "Backend Engineer" and state["total_main"] == 6
    assert state["focus"] == "APIs and caching"
    assert state["current_question"]["question"] == "Question 0?"
    assert "Alex" in state["current_question"]["intro"]

    monkeypatch.setattr(tech_interview, "evaluate_turn", _evaluation(follow_up="Can you go deeper on that?"))
    headers = csrf_headers(signed_in)
    first = signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "I built APIs.", "position": 0}, headers=headers)
    assert first.status_code == 200 and first.json["feedback"]["score"] == 7.0 and first.json["reaction"] == "Thanks."
    follow = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["current_question"]
    assert follow["is_follow_up"] is True and follow["question"] == "Can you go deeper on that?" and follow["number"] == 1

    # A follow-up never gets its own follow-up, so the next turn moves to the next planned question.
    signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "More depth."}, headers=headers)
    nxt = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["current_question"]
    assert nxt["question"] == "Question 1?" and nxt["number"] == 2 and nxt["intro"].startswith("Thanks.")
    stale = signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "late", "position": 0}, headers=headers)
    assert stale.status_code == 409

    monkeypatch.setattr(tech_interview, "evaluate_turn", _evaluation())
    for _ in range(5):
        result = signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Answer"}, headers=headers)
    assert result.json["completed"] is True and result.json["closing"]
    assert signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "x"}, headers=headers).status_code == 409

    monkeypatch.setattr(tech_interview.ai_service, "AI_ENABLED", False)
    report = signed_in.post(f"/api/v1/interviews/{interview_id}/report", headers=headers)
    assert report.status_code == 200
    assert report.json["report"]["overall_score"] == 7.0 and report.json["report"]["verdict"] == "Hire"
    assert report.json["report"]["automated"] is False
    final = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]
    # The fallback report is not stored, so the next visit retries the AI summary.
    assert final["status"] == "completed" and final["report"] is None and len(final["turns"]) == 7


def test_assessment_hides_scores_until_complete_and_is_proctored(signed_in, planned):
    interview_id = _create(signed_in, mode="assessment", proctored=False).json["interview"]["id"]
    headers = csrf_headers(signed_in)
    result = signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Answer"}, headers=headers)
    assert result.json["feedback"] is None and result.json["reaction"] == "Thanks."
    state = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]
    assert state["proctored"] is True
    assert state["turns"][0]["score"] is None and state["turns"][0]["feedback"] is None
    assert state["responses"][0]["score"] is None and state["average_score"] is None
    assert signed_in.post(f"/api/v1/interviews/{interview_id}/report", headers=headers).status_code == 409
    history = signed_in.get("/api/v1/history").json["responses"]
    assert history[0]["score"] is None and history[0]["feedback"] is None and history[0]["type"] == "tech"
    recent = signed_in.get("/api/v1/dashboard").json["recent"][0]
    assert recent["average"] is None and recent["label"] == "Backend Engineer · Assessment"


def test_proctor_events_are_validated_and_summarized(signed_in, planned):
    interview_id = _create(signed_in, mode="assessment").json["interview"]["id"]
    headers = csrf_headers(signed_in)
    url = f"/api/v1/interviews/{interview_id}/proctor-events"
    assert signed_in.post(url, json={"events": [{"kind": "hacking"}]}, headers=headers).status_code == 400
    assert signed_in.post(url, json={"events": [{"kind": "no_face", "duration_ms": -1}]}, headers=headers).status_code == 400
    ok = signed_in.post(url, json={"events": [{"kind": "no_face", "duration_ms": 4200, "position": 0},
                                               {"kind": "tab_hidden", "duration_ms": 1000}]}, headers=headers)
    assert ok.json == {"recorded": 2}
    integrity = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["integrity"]
    assert integrity["warnings"] == 2 and integrity["status"] == "minor"
    assert integrity["events"]["no_face"] == {"count": 1, "seconds": 4}


def test_tech_question_audio_voices_stored_interviewer_text(signed_in, planned, monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", True)
    spoken = []
    monkeypatch.setattr(routes.voice_service, "synthesize", lambda text: spoken.append(text) or b"ID3")
    interview_id = _create(signed_in).json["interview"]["id"]
    assert signed_in.get(f"/api/v1/interviews/{interview_id}/questions/0/audio").status_code == 200
    assert spoken[0].startswith("Hi, I'm Alex") and spoken[0].endswith("Question 0?")
    assert signed_in.get(f"/api/v1/interviews/{interview_id}/questions/5/audio").status_code == 404


def test_other_users_cannot_access_tech_interview(client, planned):
    def register(email):
        client.post("/api/v1/auth/register", json={"name": "U", "email": email, "password": "a-very-long-password"}, headers={"Origin": "http://localhost:3000"})
    register("owner@example.com")
    interview_id = _create(client).json["interview"]["id"]
    register("intruder@example.com")
    headers = csrf_headers(client)
    assert client.get(f"/api/v1/interviews/{interview_id}").status_code == 404
    assert client.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "x"}, headers=headers).status_code == 404
    assert client.post(f"/api/v1/interviews/{interview_id}/proctor-events", json={"events": []}, headers=headers).status_code == 404


def test_ai_fallbacks_keep_the_interview_running(monkeypatch):
    monkeypatch.setattr(tech_interview.ai_service, "AI_ENABLED", False)
    plan, generated = tech_interview.plan_interview("Frontend Engineer", "senior", "", "assessment", "frontend")
    assert generated is False and len(plan) == 8
    assert len({item["question"] for item in plan}) == 8
    assert all(item["category"] in tech_interview.CATEGORIES for item in plan)
    custom_plan, _ = tech_interview.plan_interview("Game Developer", "junior", "", "practice", "custom")
    assert len(custom_plan) == 6
    turn = tech_interview.evaluate_turn(role="Frontend Engineer", level="senior", mode="assessment", question="Q?",
                                        category="fundamentals", answer="(skipped)", is_follow_up=False,
                                        follow_up_allowed=True, position=0)
    assert turn["follow_up"] is None and turn["reaction"] and 1 <= turn["score"] <= 10


def test_model_output_is_validated(monkeypatch):
    monkeypatch.setattr(tech_interview.ai_service, "_call_model", lambda prompt, temperature=0.2, kind="other": json.dumps({
        "score": 8, "strengths": ["Precise"], "improvements": ["Mention limits"], "model_answer": ["A", 3],
        "reaction": "Nice.", "follow_up": "What about failure modes there?"}))
    turn = tech_interview.evaluate_turn(role="Backend Engineer", level="mid", mode="practice", question="Q?", category="fundamentals",
                                        answer="Answer", is_follow_up=False, follow_up_allowed=False, position=1)
    assert turn["follow_up"] is None and turn["model_answer"] == ["A"] and turn["score"] == 8.0


def test_capabilities_report_voice_and_ai(signed_in, monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", True)
    assert signed_in.get("/api/v1/capabilities").json["voice"] is True


def test_in_progress_assessment_scores_do_not_leak_through_aggregates(signed_in, planned):
    headers = csrf_headers(signed_in)
    practice = _create(signed_in).json["interview"]["id"]
    signed_in.post(f"/api/v1/interviews/{practice}/turns", json={"answer": "Practice answer"}, headers=headers)
    before = (signed_in.get("/api/v1/dashboard").json["summary"]["average_score"], signed_in.get("/api/v1/analytics").json)
    assessment = _create(signed_in, mode="assessment").json["interview"]["id"]
    tech_interview_evaluate = tech_interview.evaluate_turn
    tech_interview.evaluate_turn = _evaluation(score=9.5)
    try:
        signed_in.post(f"/api/v1/interviews/{assessment}/turns", json={"answer": "Hidden answer"}, headers=headers)
    finally:
        tech_interview.evaluate_turn = tech_interview_evaluate
    assert signed_in.get("/api/v1/dashboard").json["summary"]["average_score"] == before[0] == 7.0
    assert signed_in.get("/api/v1/analytics").json == before[1]
    strong = [item for item in signed_in.get("/api/v1/achievements").json["achievements"] if item["id"] == "strong_answer"][0]
    assert strong["unlocked"] is False


def test_paid_ai_actions_are_rate_limited_per_user(signed_in, planned, app):
    app.config["AI_RATE_LIMITS"] = {"interview": (2, 3600), "answer": (1, 3600), "transcription": (1, 3600)}
    assert _create(signed_in).status_code == 201
    interview_id = _create(signed_in).json["interview"]["id"]
    limited = _create(signed_in)
    assert limited.status_code == 429 and limited.json["error"]["code"] == "rate_limited"
    headers = csrf_headers(signed_in)
    assert signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "One"}, headers=headers).status_code == 200
    assert signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Two"}, headers=headers).status_code == 429
    # A rejected request does not change the interview.
    assert len(signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["turns"]) == 1


def test_rate_limit_window_resets(signed_in, planned, app):
    from datetime import timedelta
    from backend.extensions import db
    from backend.models import RateLimitBucket
    app.config["AI_RATE_LIMITS"] = {"interview": (1, 3600), "answer": (5, 3600), "transcription": (5, 3600)}
    assert _create(signed_in).status_code == 201
    assert _create(signed_in).status_code == 429
    with app.app_context():
        for bucket in RateLimitBucket.query.all():
            bucket.window_started_at -= timedelta(hours=2)
        db.session.commit()
    assert _create(signed_in).status_code == 201


def test_late_assessment_answers_are_recorded(signed_in, planned, app):
    from datetime import timedelta
    from backend.extensions import db
    headers = csrf_headers(signed_in)
    interview_id = _create(signed_in, mode="assessment").json["interview"]["id"]
    signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "On time"}, headers=headers)
    with app.app_context():
        question = InterviewQuestion.query.filter_by(interview_id=interview_id, position=1).one()
        question.asked_at -= timedelta(seconds=routes.ASSESSMENT_ANSWER_SECONDS + routes.ASSESSMENT_GRACE_SECONDS + 30)
        db.session.commit()
    signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Late"}, headers=headers)
    integrity = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["integrity"]
    assert integrity["events"]["late_answer"]["count"] == 1
    assert 25 <= integrity["events"]["late_answer"]["seconds"] <= 35


def test_fallback_report_is_not_cached_so_it_retries(signed_in, planned, monkeypatch):
    headers = csrf_headers(signed_in)
    interview_id = _create(signed_in).json["interview"]["id"]
    for _ in range(6):
        signed_in.post(f"/api/v1/interviews/{interview_id}/turns", json={"answer": "Answer"}, headers=headers)
    monkeypatch.setattr(tech_interview.ai_service, "_call_model", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("busy")))
    first = signed_in.post(f"/api/v1/interviews/{interview_id}/report", headers=headers).json["report"]
    assert first["automated"] is False
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["report"] is None
    monkeypatch.setattr(tech_interview.ai_service, "_call_model", lambda *args, **kwargs: json.dumps(
        {"summary": "Solid answers.", "strengths": ["Clear"], "improvements": ["Depth"], "next_steps": ["Practice"]}))
    second = signed_in.post(f"/api/v1/interviews/{interview_id}/report", headers=headers).json["report"]
    assert second["automated"] is True
    assert signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]["report"]["summary"] == "Solid answers."
