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
    final = signed_in.get(f"/api/v1/interviews/{interview_id}").json["interview"]
    assert final["status"] == "completed" and final["report"]["overall_score"] == 7.0 and len(final["turns"]) == 7


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
    monkeypatch.setattr(tech_interview.ai_service, "_call_model", lambda prompt, temperature=0.2: json.dumps({
        "score": 8, "strengths": ["Precise"], "improvements": ["Mention limits"], "model_answer": ["A", 3],
        "reaction": "Nice.", "follow_up": "What about failure modes there?"}))
    turn = tech_interview.evaluate_turn(role="Backend Engineer", level="mid", mode="practice", question="Q?", category="fundamentals",
                                        answer="Answer", is_follow_up=False, follow_up_allowed=False, position=1)
    assert turn["follow_up"] is None and turn["model_answer"] == ["A"] and turn["score"] == 8.0


def test_capabilities_report_voice_and_ai(signed_in, monkeypatch):
    monkeypatch.setattr(routes.voice_service, "VOICE_ENABLED", True)
    assert signed_in.get("/api/v1/capabilities").json["voice"] is True
