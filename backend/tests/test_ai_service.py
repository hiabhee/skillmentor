from types import SimpleNamespace

import pytest

from backend import ai_service


def test_model_calls_request_structured_json(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])

    monkeypatch.setattr(ai_service, "AI_ENABLED", True)
    monkeypatch.setattr(ai_service, "_client", SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    assert ai_service._call_model("review this") == '{"ok":true}'
    assert captured["model"] == ai_service.MODEL_NAME
    assert captured["messages"][1]["content"] == "review this"
    assert captured["messages"][0]["role"] == "system"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["max_completion_tokens"] == 1800


@pytest.mark.parametrize("choices", [[], [SimpleNamespace(message=SimpleNamespace(content=None))]])
def test_model_rejects_empty_provider_responses(monkeypatch, choices):
    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(choices=choices)

    monkeypatch.setattr(ai_service, "AI_ENABLED", True)
    monkeypatch.setattr(ai_service, "_client", SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    with pytest.raises(ValueError, match="empty response"):
        ai_service._call_model("review this")


def test_groq_client_uses_bounded_timeout_without_automatic_retries(monkeypatch):
    captured = {}

    def fake_groq(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(ai_service, "Groq", fake_groq)
    monkeypatch.setattr(ai_service, "GROQ_API_KEY", "test-key")
    monkeypatch.setenv("AI_REVIEW_TIMEOUT_SECONDS", "12.5")
    ai_service._create_client()
    assert captured == {"api_key": "test-key", "timeout": 12.5, "max_retries": 0}


def test_interview_review_validates_and_limits_feedback(monkeypatch):
    monkeypatch.setattr(ai_service, "_call_model", lambda *_args, **_kwargs: '{"strengths":["Evidence"],"improvements":["Add impact"],"score":8.2}')
    result = ai_service.review_interview_answer("What changed?", "I improved delivery by 20%.")
    assert result == {"strengths": ["Evidence"], "improvements": ["Add impact"], "score": 8.2, "automated": True}
    monkeypatch.setattr(ai_service, "_call_model", lambda *_args, **_kwargs: '{"strengths":["Okay"],"improvements":["No"],"score":11}')
    with pytest.raises(ValueError, match="out-of-range"):
        ai_service.review_interview_answer("Question", "Answer")


def test_code_review_never_scores_incorrect_solution_above_five(monkeypatch):
    monkeypatch.setattr(ai_service, "_call_model", lambda *_args, **_kwargs: '{"is_correct":false,"score":9,"summary":"Fails a stated edge case.","strengths":["Readable"],"improvements":["Handle empty input"],"show_solution":true}')
    problem = ai_service.curated_problem(0)
    result = ai_service.review_code_submission(problem, "print(0)")
    assert result["score"] == 5.0
    assert result["show_solution"] is True
    assert result["summary"] == "Fails a stated edge case."


def test_model_unavailability_is_explicit():
    monkeypatch_value = ai_service.AI_ENABLED
    try:
        ai_service.AI_ENABLED = False
        with pytest.raises(RuntimeError, match="not configured"):
            ai_service._call_model("ignored")
    finally:
        ai_service.AI_ENABLED = monkeypatch_value
