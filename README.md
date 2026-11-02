# Skillmentor

**Practice technical interviews out loud with an AI interviewer that listens, asks follow-up questions and tells you exactly what to fix.**

Skillmentor is a mock interview platform for software engineers preparing for job interviews. You pick the role you're going after and your experience level, then talk through a realistic interview with "Alex", an AI interviewer. Alex asks role-specific questions, probes deeper when an answer is vague, scores each answer like a hiring panel would, and finishes with a scorecard and a hire verdict.

It is built for the part of interview prep that's hardest to do alone: answering out loud, under realistic conditions, and getting honest, specific feedback afterwards.

---

## What you can do

### Mock technical interviews
- **Choose your target:** Frontend, Backend, Full-stack, Mobile, Data Engineering, Machine Learning, DevOps/SRE, Security, or any role you type in.
- **Set your level:** Intern, Junior, Mid-level, Senior or Staff+. Question difficulty follows the level you choose.
- **Pick focus areas:** up to 3 topics (for example React and TypeScript, or Caching and System design) to weight the questions toward.
- **Adaptive follow-ups:** when an answer is vague or interesting, Alex asks a follow-up that builds on what you actually said, up to 3 per interview.

### Two session types

| | **Practice** | **Assessment** |
|---|---|---|
| Questions | 6 + follow-ups | 8 + follow-ups |
| Feedback | After every answer, with a model answer | Only at the end |
| Timing | No clock | 3 minutes per answer |
| Camera | Optional | Required |
| Result | Coaching notes | Scorecard, competency scores and a hire verdict |

### Answer the way you would in a real interview
- **Voice call:** hands-free and spoken only, like a phone screen. Alex reads each question aloud, listens, and moves on when you pause.
- **Voice + text:** see each question, then speak or type your answer and edit the transcript before submitting.
- **Text only:** used automatically when voice isn't configured on the server.

### Feedback you can act on
For each answer you get a score out of 10, what worked well, what to improve, and the points a strong answer would cover. At the end of an interview you get a report with a summary, a score per competency, strengths, gaps and concrete next steps.

### Integrity monitoring that respects privacy
In assessments (and in practice if you turn the camera on), face tracking warns you if you leave the frame, another person appears, or you look away for a while. It also notices when you switch tabs. **Face tracking runs entirely in your browser: video is never uploaded.** Only the type and duration of each event are saved, and they appear in your integrity report.

### More practice formats
- **Personal interview:** 10 classic behavioral questions ("Tell me about yourself", "Describe a proud moment") with feedback on each answer.
- **Coding challenges:** 3 algorithm problems with constraints and examples, a Python editor, and an AI review of correctness, edge cases and complexity. Code is reviewed, not executed.

### Track your progress
A dashboard of recent sessions, a full answer history you can delete, progress analytics over time, and achievements.

### Nothing gets lost
Your setup choices, unfinished answers, code drafts and the assessment clock are all stored on the server. Refreshing the page, clicking Leave, or switching devices picks up exactly where you were, and refreshing never adds time to an assessment answer.

### Try it without signing up
"Explore the demo account" on the sign-in page opens a sample workspace. The demo account is shared, so other visitors can see what you do there.

---

## How it works

```text
Browser ── same-origin cookie ──> Next.js web app ── private network ──> Flask API ──> PostgreSQL
                                                                          │
                                                                          ├── Groq (LLM): plans questions, scores answers, writes reports
                                                                          └── ElevenLabs: interviewer voice and speech-to-text
```

- **Frontend** (`frontend/`): Next.js App Router, React and SWR. The browser only ever talks to the web app's own `/api/v1/*` route, which forwards requests to the private API, so API keys and the backend stay off the public internet.
- **Backend** (`backend/`): a Flask JSON API with SQLAlchemy and Alembic migrations, PostgreSQL in production and SQLite locally.
- **AI:** Groq runs `openai/gpt-oss-120b` by default to plan each interview, evaluate answers and write the final report. If the AI provider is unavailable or rate-limited, interviews keep going on a curated question bank and simple rule-based scoring, so a session never stalls.
- **Voice:** ElevenLabs Flash speaks the interviewer's lines and Scribe transcribes your answers. Recently spoken questions are cached, so replaying a question costs nothing.
- **Face tracking:** MediaPipe's BlazeFace model runs in the browser using WebAssembly.

### Performance
Answer evaluation runs at low reasoning effort. On a benchmark of real interview answers this gave a median evaluation time of about **1 second** and used **33% fewer tokens** than medium effort, which keeps a live voice interview feeling responsive. Every AI and voice call records its latency, token use and outcome, so you can measure this in production (see [AI call telemetry](#ai-call-telemetry)).

---

## Run it locally

You need **Python 3.10+** and **Node 20.9+**.

### 1. Backend (terminal 1)

From the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
flask --app backend.app db upgrade
flask --app backend.app run --port 8000
```

### 2. Frontend (terminal 2)

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. The frontend sends API requests to `http://127.0.0.1:8000` by default; set `BACKEND_URL` to change this. If you use a port other than 3000 or 3001 for the frontend, add its address to `WEB_ORIGINS`.

> When pasting commands into zsh, leave out any `#` comments: by default zsh passes them to the command as arguments.

### 3. Configure (optional)

Put settings in a `.env` file in the project root; Flask loads it automatically. The app runs without any keys, using text-only interviews and the built-in question bank.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Session signing secret. Required in production (32+ characters). |
| `DATABASE_URL` | Database URL. Defaults to `interview.db` (SQLite) in the project root. |
| `GROQ_API_KEY` | Turns on AI question planning, answer scoring and reports. |
| `GROQ_MODEL` | Groq model to use (default `openai/gpt-oss-120b`). |
| `GROQ_REASONING_EFFORT` | `low` (default for gpt-oss), `medium` or `high`. Leave it empty for models without reasoning. |
| `AI_REVIEW_TIMEOUT_SECONDS` | Timeout for each AI call (default 25). |
| `ELEVAN_LAB_API_KEY` or `ELEVENLABS_API_KEY` | Turns on voice: the spoken interviewer and speech-to-text. |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_STT_MODEL`, `VOICE_TIMEOUT_SECONDS` | Optional voice tuning. Defaults are `eleven_flash_v2_5` for speech and `scribe_v2` for transcription. |
| `WEB_ORIGINS` | Comma-separated frontend addresses allowed to call the API. |
| `ADMIN_EMAILS` | Comma-separated accounts allowed to read the AI metrics endpoint. |

---

## Tests and checks

```sh
python -m pytest -q backend/tests
cd frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

The backend tests use an isolated SQLite database and mock every external AI and voice call, so they run offline. To smoke-test the migrations against a clean database, run `DATABASE_URL=sqlite:////tmp/skillmentor-migration.db flask --app backend.app db upgrade`.

---

## Deploying

`render.yaml` is a Render blueprint that creates a Next.js web service, a private Flask service and a managed PostgreSQL database in the same region. Database migrations run before each deploy. Add `GROQ_API_KEY`, `ELEVAN_LAB_API_KEY` and `ADMIN_EMAILS` as secrets in Render.

In production the app refuses to start with a missing or short `SECRET_KEY`, or with a SQLite database.

**Capacity:** AI calls are limited per user per hour (`AI_RATE_LIMITS` in `backend/config.py`; the demo account shares one budget). A free Groq key is also limited across the whole deployment: 8,000 tokens per minute and 1,000 requests per day, or roughly five answer evaluations per minute. Use a paid Groq tier before opening the app to many people at once.

---

## Reference

### Security
- Sessions are random opaque tokens, stored only as hashes. Cookies are HTTP-only, same-site, time-limited, and secure in production.
- Every state-changing request needs an allowed origin and a CSRF token.
- Sign-in attempts are rate-limited, and the API returns JSON errors only.
- Candidate answers are treated as untrusted input in every AI prompt.
- The voice endpoint will only speak interviewer text stored with the session, so it can't be used to voice arbitrary text.

### Server-owned interview state
The API, not the browser, is the source of truth for anything a candidate expects to survive a refresh or a device switch:

- **Setup choices** (role, level, focus areas, session type, format, camera, voice auto-play) are saved to the account through `PUT /api/v1/preferences` as they change, and again when an interview starts. `GET /api/v1/interview-options` returns them along with the rules the setup screen shows: question counts, session length, assessment answer time, and whether voice is configured.
- **Drafts:** unsubmitted answers and code autosave to `PUT /api/v1/interviews/<id>/draft` and come back with the interview. A draft is deleted when its answer is submitted.
- **Assessment clock:** `POST /api/v1/interviews/<id>/join` starts the answer clock once, and each question reports the server's `seconds_left`, so reloading or rejoining never adds time. Late answers are recorded for every question, including the first.
- **Voice:** a voice-only interview is only created when the server has voice configured, whatever the browser asks for.

### AI call telemetry
Every Groq and ElevenLabs call is recorded in the `ai_calls` table with:
- **Kind:** `plan`, `evaluate`, `report`, `answer_review`, `code_review`, `tts` or `stt`.
- **Latency and token counts.**
- **Outcome:** `ok`, `error`, `fallback` (the candidate got the built-in response) or `cached` (replayed speech).

Rows are saved after the response is built, so telemetry never slows down or breaks an interview. Only call metadata is stored, never prompts, answers or audio.

Accounts listed in `ADMIN_EMAILS` can read `GET /api/v1/admin/metrics?days=7`. It returns, for each kind: call counts, success, fallback and cache-hit rates, median and 95th-percentile latency, and average tokens. Other accounts get a 404. The same summary is available from the command line:

```sh
flask --app backend.app ai-metrics --days 30
```

### Legacy data
The migrations upgrade a database from the earlier version of the app in place. They add the new columns to the existing `users`, `interviews`, `responses` and `coding_challenges` tables, give old responses a stable order, and keep every record. Point `DATABASE_URL` at that database before running `db upgrade`. The Render blueprint creates a new, empty PostgreSQL database, so moving an existing SQLite file there needs an explicit export and import.

### Project layout

```text
backend/            Flask API
  routes.py           HTTP endpoints
  tech_interview.py   Interview planning, answer evaluation, reports and fallbacks
  ai_service.py       Groq client and answer/code review
  voice_service.py    ElevenLabs speech and transcription
  telemetry.py        AI call metrics
  models.py           Database models
  migrations/         Alembic migrations
  tests/              pytest suite
frontend/           Next.js web app
  app/                Pages and the /api/v1 proxy route
  components/tech/    Live interview room, voice call, face tracking, report
  lib/                API client, draft autosave, shared types
render.yaml         Render deployment blueprint
```
