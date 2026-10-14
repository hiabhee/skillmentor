# Skillmentor

Skillmentor is split into two deployable services:

- `frontend/` is the Next.js App Router application. The browser talks only to its same-origin `/api/v1/*` route handler.
- `backend/` is a Flask JSON API with PostgreSQL persistence, opaque server-side sessions, CSRF checks, rate limiting, and versioned routes.

```text
Browser ── same-origin cookie ──> Next.js web service ── private network ──> Flask API ──> PostgreSQL
```

## Local development

Use Node 20.9 or newer and Python 3.11 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
flask --app backend.app db upgrade
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

The frontend proxy defaults to `http://127.0.0.1:8000`. Start the API separately with:

```sh
flask --app backend.app run --port 8000
```

The backend uses `DATABASE_URL` when set and otherwise stores local data in `interview.db`. Set `SECRET_KEY` to a random value and optionally set `GROQ_API_KEY` for AI reviews. AI review falls back to a clearly labeled basic response when Groq is unavailable. The coding review is advisory and does not execute submitted code. The provider timeout is configurable with `AI_REVIEW_TIMEOUT_SECONDS`; `GROQ_MODEL` selects a supported Groq model and defaults to `openai/gpt-oss-120b`.

### Voice interviews (ElevenLabs)

Set `ELEVAN_LAB_API_KEY` (or `ELEVENLABS_API_KEY`) to turn on voice mode for personal interviews. The interviewer reads each question aloud using ElevenLabs text-to-speech. The candidate can then record a spoken answer, which ElevenLabs speech-to-text transcribes into the answer box. The candidate can edit the transcript before submitting, and the existing AI review scores it. The key stays on the Flask API, and the speech endpoint only voices the fixed interview questions. Optional settings are `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL` (default `eleven_multilingual_v2`), `ELEVENLABS_STT_MODEL` (default `scribe_v2`) and `VOICE_TIMEOUT_SECONDS`. Without a key, the interview stays text-only.

## Production configuration

`render.yaml` provisions a Next.js web service, a private Flask service, and PostgreSQL in the same region. The backend migration runs before each deployment. Add `GROQ_API_KEY` as a secret in Render if AI reviews should be enabled. Production startup rejects a missing/short session secret and SQLite database configuration.

The web service forwards only the required request headers and cookies to the private API. Session IDs are random opaque tokens stored as hashes in PostgreSQL; browser cookies are HTTP-only, secure in production, same-site, and time-limited. State-changing requests require both an allowed origin and a CSRF token. The API returns JSON errors and never serves templates or assets.

## Tests and checks

```sh
pytest -q
cd frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

The backend test suite uses an isolated SQLite database and mocks external AI calls. The migration can be smoke-tested against a clean database with `DATABASE_URL=sqlite:////tmp/skillmentor-migration.db flask --app backend.app db upgrade`.

## Legacy data

The migration adds the API session fields to the original `users`, `interviews`, `responses`, and `coding_challenges` tables when they exist, assigns old responses a stable order, and keeps those records. Point `DATABASE_URL` at the existing database before applying it to continue using that data. The Render blueprint provisions a new managed PostgreSQL database; moving an existing SQLite file to it requires an explicit data export/import.
