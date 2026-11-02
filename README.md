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
pip install -r backend/requirements-dev.txt
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

The backend uses `DATABASE_URL` when set and otherwise stores local data in `interview.db`. Set `SECRET_KEY` to a random value and optionally set `GROQ_API_KEY` for AI reviews. AI review falls back to a clearly labeled basic response when Groq is unavailable. The coding review is advisory and does not execute submitted code. The provider timeout is configurable with `AI_REVIEW_TIMEOUT_SECONDS`; `GROQ_MODEL` selects a supported Groq model and defaults to `openai/gpt-oss-120b`. `GROQ_REASONING_EFFORT` defaults to `low` for gpt-oss models, which uses about 33% fewer tokens and half the latency per evaluation; set it to `medium` or `high` for deeper reviews, or to an empty value for models without reasoning.

### Tech interviews, voice and face tracking

Candidates choose a role, level, focus topics, practice or assessment mode, and a format: a hands-free voice call or voice plus text. Groq plans the questions, scores each answer, asks up to three follow-up questions and writes the final report. If Groq is unavailable, the API falls back to a curated question bank and heuristic scores; it does not store a fallback report, so the next visit retries the AI summary.

Set `ELEVAN_LAB_API_KEY` (or `ELEVENLABS_API_KEY`) to turn on voice. ElevenLabs speaks the interviewer's text and transcribes spoken answers. The key stays on the Flask API, and the speech endpoint only voices interviewer text stored with the session. Optional settings are `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL` (default `eleven_flash_v2_5`, the low-latency model), `ELEVENLABS_STT_MODEL` (default `scribe_v2`) and `VOICE_TIMEOUT_SECONDS`. Without a key, interviews are text-only.

Face tracking uses MediaPipe in the browser; video never leaves the device, and only event types and durations are stored. `npm ci` copies the MediaPipe WebAssembly files into `frontend/public/mediapipe/wasm` (a `postinstall` step), and the face model is committed at `frontend/public/mediapipe/blaze_face_short_range.tflite`.

Paid AI calls are limited per user and per hour (`AI_RATE_LIMITS` in `backend/config.py`; the demo account shares one budget). The provider's own limits apply too: a free Groq key allows 8,000 tokens per minute and 1,000 requests per day for the whole deployment, which is roughly five answer evaluations per minute. Use a paid Groq tier before opening the app to many concurrent users.

### Server-owned interview state

The API, not the browser, is the source of truth for everything a candidate would expect to survive a refresh or a device switch:

- **Setup choices** (role, level, focus areas, session type, format, camera, voice auto-play) are saved to the account with `PUT /api/v1/preferences` as they change, and again when an interview starts. `GET /api/v1/interview-options` returns them along with the rules the setup screen shows: question counts, session length, assessment answer time, and whether voice is configured.
- **Drafts**: unsubmitted answers and code autosave to `PUT /api/v1/interviews/<id>/draft` and come back with the interview. A draft is deleted when its answer is submitted.
- **Assessment clock**: `POST /api/v1/interviews/<id>/join` starts the answer clock once, and each question reports the server's `seconds_left`, so reloading or rejoining never adds time. Late answers are recorded for every question, including the first.
- **Voice**: a voice-only interview is only created when the server has voice configured, whatever the browser asks for.

### AI call telemetry

Every Groq and ElevenLabs call is recorded in the `ai_calls` table: its kind (`plan`, `evaluate`, `report`, `answer_review`, `code_review`, `tts`, `stt`), latency, token counts and outcome (`ok`, `error`, `fallback` when the candidate got the built-in response, or `cached` for replayed speech). Rows are saved after the response is built, so telemetry never slows or breaks an interview. Only call metadata is stored, never prompts, answers or audio.

Accounts listed in `ADMIN_EMAILS` (comma-separated) can read `GET /api/v1/admin/metrics?days=7`, which returns per-kind call counts, success, fallback and cache-hit rates, p50/p95 latency and average tokens. Other accounts get a 404. The same summary is available from the command line:

```sh
flask --app backend.app ai-metrics --days 30
```

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
