import json
from collections import OrderedDict

import backend.voice_service as voice


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_transcribe_sends_multipart_with_key_and_model(monkeypatch):
    monkeypatch.setattr(voice, "VOICE_ENABLED", True)
    monkeypatch.setattr(voice, "API_KEY", "test-key")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"], seen["key"], seen["type"], seen["body"] = request.full_url, request.get_header("Xi-api-key"), request.get_header("Content-type"), request.data
        return FakeResponse(json.dumps({"text": "  Hello there  "}).encode())

    monkeypatch.setattr(voice.urllib.request, "urlopen", fake_urlopen)
    assert voice.transcribe(b"AUDIO", "answer.webm", "audio/webm") == "Hello there"
    assert seen["url"].endswith("/v1/speech-to-text")
    assert seen["key"] == "test-key"
    assert seen["type"].startswith("multipart/form-data; boundary=")
    assert voice.STT_MODEL.encode() in seen["body"] and b"AUDIO" in seen["body"]


def test_synthesize_caches_fixed_question_audio(monkeypatch):
    monkeypatch.setattr(voice, "VOICE_ENABLED", True)
    monkeypatch.setattr(voice, "_speech_cache", OrderedDict())
    calls = []
    monkeypatch.setattr(voice.urllib.request, "urlopen", lambda request, timeout: calls.append(request) or FakeResponse(b"MP3"))
    assert voice.synthesize("Tell me about yourself.") == b"MP3"
    assert voice.synthesize("Tell me about yourself.") == b"MP3"
    assert len(calls) == 1
    assert json.loads(calls[0].data)["text"] == "Tell me about yourself."


def test_speech_cache_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(voice, "VOICE_ENABLED", True)
    monkeypatch.setattr(voice, "_speech_cache", OrderedDict())
    monkeypatch.setattr(voice, "SPEECH_CACHE_ENTRIES", 2)
    calls = []
    monkeypatch.setattr(voice.urllib.request, "urlopen", lambda request, timeout: calls.append(json.loads(request.data)["text"]) or FakeResponse(b"MP3"))
    voice.synthesize("one"); voice.synthesize("two"); voice.synthesize("one"); voice.synthesize("three")
    voice.synthesize("one")
    voice.synthesize("two")
    assert calls == ["one", "two", "three", "two"]
    assert len(voice._speech_cache) == 2
