"""ElevenLabs speech boundary: question text to speech and answer audio to text.

The API key stays on the server. Callers only ever send fixed question positions
for synthesis, so the endpoint cannot be used to voice arbitrary text.
"""

import json
import os
import secrets
import threading
import urllib.error
import urllib.request

API_BASE = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io").rstrip("/")
# The project's .env uses ELEVAN_LAB_API_KEY; the conventional name is accepted too.
API_KEY = (os.getenv("ELEVAN_LAB_API_KEY") or os.getenv("ELEVENLABS_API_KEY") or "").strip()
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
VOICE_ENABLED = bool(API_KEY)

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac"}

_speech_cache = {}
_cache_lock = threading.Lock()


class VoiceError(RuntimeError):
    pass


def _timeout():
    try:
        value = float(os.getenv("VOICE_TIMEOUT_SECONDS", "20"))
    except (TypeError, ValueError):
        return 20.0
    return value if value > 0 else 20.0


def _send(request):
    if not VOICE_ENABLED:
        raise VoiceError("Voice is not configured")
    request.add_header("xi-api-key", API_KEY)
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise VoiceError(f"ElevenLabs returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise VoiceError("ElevenLabs could not be reached") from error


def synthesize(text):
    """Return MP3 bytes for text. Results are cached because questions are fixed."""
    key = (VOICE_ID, TTS_MODEL, text)
    with _cache_lock:
        if key in _speech_cache:
            return _speech_cache[key]
    body = json.dumps({"text": text, "model_id": TTS_MODEL}).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}/v1/text-to-speech/{VOICE_ID}?output_format=mp3_44100_128",
        data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    audio = _send(request)
    if not audio:
        raise VoiceError("ElevenLabs returned empty audio")
    with _cache_lock:
        _speech_cache[key] = audio
    return audio


def transcribe(audio, filename, content_type):
    """Return the transcript text for an uploaded audio clip."""
    boundary = "----skillmentor" + secrets.token_hex(12)
    safe_name = "".join(ch for ch in (filename or "answer.webm") if ch.isalnum() or ch in "._-") or "answer.webm"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model_id"\r\n\r\n{STT_MODEL}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="tag_audio_events"\r\n\r\nfalse\r\n'.encode(),
        (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
         f"Content-Type: {content_type}\r\n\r\n").encode(),
        audio,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    request = urllib.request.Request(
        f"{API_BASE}/v1/speech-to-text", data=b"".join(parts), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
    )
    try:
        data = json.loads(_send(request))
    except (ValueError, TypeError) as error:
        raise VoiceError("ElevenLabs returned an unreadable transcript") from error
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str):
        raise VoiceError("ElevenLabs returned no transcript")
    return text.strip()
