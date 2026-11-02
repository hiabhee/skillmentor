"""Versioned JSON API. Browser traffic reaches this service through the Next BFF."""

import hashlib
import json
import re
import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, Response as HttpResponse, current_app, g, jsonify, make_response, request
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .ai_service import (
    curated_problem,
    fallback_interview_feedback,
    review_code_submission,
    review_interview_answer,
)
from . import ai_service, telemetry, tech_interview, voice_service
from .extensions import db
from .models import (AuthSession, CodingChallenge, Interview, InterviewQuestion, LoginAttempt, ProctorEvent,
                     RateLimitBucket, Response, User, utcnow)

api = Blueprint("api", __name__)

ROUND1_QUESTIONS = [
    "Tell me about yourself.",
    "What are your hobbies?",
    "Which skill do you want to develop the most?",
    "What motivates you in life?",
    "Describe a proud moment from your journey.",
    "What is one weakness you are working on?",
    "How do you handle stress?",
    "What kind of people do you prefer working with?",
    "What do you want to achieve in the next 2 years?",
    "Why should we select you?",
]
MAX_ANSWER_LENGTH = 20000
MAX_CODE_LENGTH = 100000
MAX_AUDIO_BYTES = 10 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEMO_ACCOUNT_EMAIL = "demo@skillmentor.example"
PROCTOR_KINDS = {"no_face", "multiple_faces", "looking_away", "tab_hidden", "camera_off"}
MAX_PROCTOR_EVENTS = 300
# Assessment answers get this much time after the question is asked (limit plus speech and network slack).
ASSESSMENT_ANSWER_SECONDS = 180
ASSESSMENT_GRACE_SECONDS = 90


def _visible_score_filter():
    """Exclude answers from assessments that are still in progress; their scores stay hidden until the end."""
    return or_(Interview.interview_type != "tech", Interview.mode != "assessment", Interview.status == "completed")


def _rate_limited(scope):
    """Count one request against the user's hourly budget for a paid AI action."""
    limit, window = current_app.config["AI_RATE_LIMITS"][scope]
    key = _hash(f"{scope}:{g.current_user.id}")
    now = utcnow()
    bucket = db.session.get(RateLimitBucket, key)
    if bucket is None:
        bucket = RateLimitBucket(key_hash=key, count=0, window_started_at=now)
        db.session.add(bucket)
    elif bucket.window_started_at <= now - timedelta(seconds=window):
        bucket.count, bucket.window_started_at = 0, now
    if bucket.count >= limit:
        db.session.rollback()
        return True
    bucket.count += 1
    try:
        db.session.commit()
    except IntegrityError:
        # A parallel request created the bucket first; let this one through.
        db.session.rollback()
    return False


def _rate_limit_error():
    return _error("rate_limited", "You have reached the hourly limit for this action. Try again later.", 429)


def _public_type(interview_type):
    return {"round1": "round1", "tech": "tech"}.get(interview_type, "coding")


def _scores_hidden(interview):
    return interview.interview_type == "tech" and interview.mode == "assessment" and interview.status != "completed"


def _type_label(interview):
    if interview.interview_type == "tech":
        return f"{interview.role} · {'Assessment' if interview.mode == 'assessment' else 'Practice'}"
    return "Personal interview" if interview.interview_type == "round1" else "Coding practice"


def _error(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _json_body():
    if not request.is_json:
        return None
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else None


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user_payload(user):
    return {"id": user.id, "email": user.email, "name": user.full_name or user.name,
            "bio": user.bio or "", "created_at": user.created_at.isoformat() + "Z"}


def _set_auth_cookies(response, raw_token, csrf_token):
    secure = bool(current_app.config["SESSION_COOKIE_SECURE"])
    common = {"secure": secure, "samesite": "Lax", "path": "/", "max_age": current_app.config["SESSION_TTL_SECONDS"]}
    response.set_cookie(current_app.config["SESSION_COOKIE_NAME"], raw_token, httponly=True, **common)
    response.set_cookie(current_app.config["CSRF_COOKIE_NAME"], csrf_token, httponly=False, **common)
    return response


def _clear_auth_cookies(response):
    for name in (current_app.config["SESSION_COOKIE_NAME"], current_app.config["CSRF_COOKIE_NAME"]):
        response.delete_cookie(name, path="/", secure=current_app.config["SESSION_COOKIE_SECURE"], samesite="Lax")
    return response


@api.before_request
def enforce_browser_boundary():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin", "").rstrip("/")
        allowed = current_app.config["WEB_ORIGINS"]
        if origin not in allowed:
            return _error("origin_not_allowed", "This request origin is not allowed.", 403)


def require_user(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        raw = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"], "")
        auth = db.session.get(AuthSession, _hash(raw)) if raw else None
        if not auth or auth.revoked_at or auth.expires_at <= utcnow():
            return _error("unauthorized", "Please sign in to continue.", 401)
        user = db.session.get(User, auth.user_id)
        if not user:
            return _error("unauthorized", "Please sign in to continue.", 401)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            cookie = request.cookies.get(current_app.config["CSRF_COOKIE_NAME"], "")
            if (not supplied or not supplied.isascii() or not cookie.isascii()
                    or not secrets.compare_digest(supplied, cookie)
                    or not secrets.compare_digest(_hash(supplied), auth.csrf_hash)):
                return _error("csrf_failed", "Refresh the page and try again.", 403)
        g.current_user = user
        g.auth_session = auth
        return fn(*args, **kwargs)
    return wrapped


def _session_response(user):
    raw_token, csrf_token = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    now = utcnow()
    AuthSession.query.filter(or_(AuthSession.expires_at <= now,
                                 AuthSession.revoked_at <= now - timedelta(days=30))).delete(synchronize_session=False)
    LoginAttempt.query.filter(LoginAttempt.window_started_at <= now - timedelta(days=1)).delete(synchronize_session=False)
    RateLimitBucket.query.filter(RateLimitBucket.window_started_at <= now - timedelta(days=1)).delete(synchronize_session=False)
    auth = AuthSession(
        token_hash=_hash(raw_token), user_id=user.id, csrf_hash=_hash(csrf_token),
        expires_at=now + timedelta(seconds=current_app.config["SESSION_TTL_SECONDS"]),
    )
    db.session.add(auth)
    db.session.commit()
    response = make_response(jsonify({"user": _user_payload(user), "csrf_token": csrf_token}))
    return _set_auth_cookies(response, raw_token, csrf_token)


def _ensure_demo_account():
    user = User.query.filter_by(email=DEMO_ACCOUNT_EMAIL).first()
    if user and Interview.query.filter_by(user_id=user.id).first():
        return user

    if not user:
        user = User(
            email=DEMO_ACCOUNT_EMAIL,
            password=generate_password_hash(secrets.token_urlsafe(40)),
            name="Jordan Lee",
            full_name="Jordan Lee",
            bio="Product engineer practicing clear interview stories and thoughtful coding solutions.",
        )
        db.session.add(user)
        db.session.flush()

    now = utcnow()
    personal_answer_sets = [
        (
            24,
            [
                "I’m a product engineer with five years of experience building tools for operations teams. Most recently, I led a redesign of our onboarding flow that helped new customers reach their first useful result sooner.",
                "I spend weekends hiking and taking street photos. Both help me slow down, notice details, and come back to work with a clearer head.",
                "I’m working on delegating earlier. I used to keep too much work on my own plate, so now I agree on clear outcomes and check in before a project gets blocked.",
                "I’m motivated by solving a real user problem and seeing the result in someone’s day-to-day work. I like pairing that with a team that cares about craft.",
                "I’m proud of helping our support team cut repeat tickets by 28%. I interviewed agents, found the confusing steps, and worked with design and engineering to simplify them.",
                "I can spend too long polishing a solution. I now timebox exploration, share an early version, and use feedback to decide where more detail matters.",
                "I handle stress by writing down the next concrete action, checking priorities with the team, and taking a short walk before I make a high impact decision.",
                "I work best with people who are direct and kind. I appreciate teammates who share context, challenge an idea with evidence, and help close the loop.",
                "In two years I want to be leading a small product engineering effort, with stronger skills in technical planning and coaching newer teammates.",
                "I combine user empathy with hands-on engineering. I can take a fuzzy problem, turn it into a small plan, and follow through while keeping partners informed.",
            ],
            [6.5, 7.0, 7.5, 7.5, 8.5, 7.0, 7.5, 8.0, 8.0, 8.5],
        ),
        (
            12,
            [
                "I’m a software engineer who enjoys turning complicated workflows into simple products. On my current team I own features from discovery through launch and measurement.",
                "I like cooking for friends and learning new recipes. It’s a fun way to practice patience and adjust when the first attempt doesn’t work.",
                "I want to get better at communicating technical tradeoffs to nontechnical partners. I’ve started writing short decision notes before planning meetings.",
                "I’m energized by steady progress on a problem that matters. Seeing a teammate or customer use something we built is a strong signal that the work helped.",
                "I’m proud of a reliability project where we reduced failed imports by 35%. I mapped the failure cases, added better retries, and worked with support to validate the change.",
                "I sometimes assume others have the same context I do. I’ve been improving by sharing the why behind a decision and asking people to reflect back what they heard.",
                "When things get busy, I write a short plan, identify the one task that unblocks the team, and communicate any changes in scope early.",
                "I value people who are curious, accountable, and comfortable changing their minds when new information appears.",
                "I’d like to grow into a senior role where I can shape technical direction and make it easier for a team to deliver dependable features.",
                "I bring a balance of practical execution and thoughtful collaboration. I follow through, ask useful questions, and look for a measurable outcome.",
            ],
            [7.0, 7.5, 7.5, 8.0, 8.5, 7.0, 8.0, 8.0, 8.5, 8.5],
        ),
    ]

    for session_index, (days_ago, answers, scores) in enumerate(personal_answer_sets):
        interview = Interview(
            user_id=user.id,
            interview_type="round1",
            difficulty="personal",
            status="completed",
            created_at=now - timedelta(days=days_ago),
        )
        db.session.add(interview)
        db.session.flush()
        for position, (question, answer, score) in enumerate(zip(ROUND1_QUESTIONS, answers, scores)):
            feedback = {
                "summary": "A clear example with a useful outcome. Make your personal contribution and impact easy to spot.",
                "strengths": ["You gave a specific, believable response.", "The example shows how you approach the work."],
                "improvements": ["Lead with the result, then add only the context needed to understand it."],
                "score": score,
                "automated": True,
            }
            db.session.add(Response(
                user_id=user.id,
                interview_id=interview.id,
                question=question,
                answer=answer,
                feedback=json.dumps(feedback, ensure_ascii=False),
                score=score,
                question_position=position,
                created_at=now - timedelta(days=max(0, days_ago - position), minutes=session_index),
            ))

    coding_sessions = [(9, [7.0, 8.0, 8.5]), (5, [7.5, 8.5, 9.0]), (2, [8.0, 8.5, 9.0])]

    def add_coding_session(days_ago, scores, status="completed"):
        interview = Interview(
            user_id=user.id,
            interview_type="round2_ai",
            difficulty="hard",
            status=status,
            created_at=now - timedelta(days=days_ago),
        )
        db.session.add(interview)
        db.session.flush()
        problems = []
        for position in range(3):
            problem = dict(curated_problem(position))
            problem["source"] = "Curated practice"
            problems.append(problem)
            db.session.add(CodingChallenge(
                interview_id=interview.id,
                position=position,
                challenge_json=json.dumps(problem, ensure_ascii=False),
                created_at=now - timedelta(days=days_ago),
            ))
        for position, score in enumerate(scores):
            problem = problems[position]
            feedback = {
                "summary": "The solution handles the core case. Explain the time and space tradeoffs before you finish.",
                "strengths": ["The approach is easy to follow.", "You considered the main edge cases."],
                "improvements": ["State the complexity and test one boundary case out loud."],
                "score": score,
                "automated": True,
            }
            db.session.add(Response(
                user_id=user.id,
                interview_id=interview.id,
                question=problem["title"],
                answer=problem["solution_code"],
                feedback=json.dumps(feedback, ensure_ascii=False),
                score=score,
                question_position=position,
                created_at=now - timedelta(days=max(0, days_ago - position), hours=2),
            ))

    for days_ago, scores in coding_sessions:
        add_coding_session(days_ago, scores)
    add_coding_session(1, [7.5], status="in_progress")

    db.session.commit()
    return user


@api.get("/health/live")
def live():
    return jsonify({"status": "ok"})


@api.get("/health/ready")
def ready():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ready", "database": "ok"})
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Readiness check failed")
        return _error("not_ready", "A required service is unavailable.", 503)


@api.post("/auth/register")
def register():
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    name = data.get("name", "")
    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        return _error("invalid_name", "Name must be between 1 and 120 characters.", 400)
    if not isinstance(email, str) or len(email) > 320 or not EMAIL_RE.fullmatch(email.strip()):
        return _error("invalid_email", "Enter a valid email address.", 400)
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        return _error("invalid_password", "Password must be 12 to 128 characters long.", 400)
    normalized_email = email.strip().lower()
    if normalized_email == DEMO_ACCOUNT_EMAIL:
        return _error("reserved_email", "That email address is reserved for the demo workspace.", 409)
    user = User(email=normalized_email, password=generate_password_hash(password), name=name.strip(), full_name=name.strip())
    db.session.add(user)
    try:
        db.session.flush()
        return _session_response(user)
    except IntegrityError:
        db.session.rollback()
        return _error("email_exists", "An account with this email already exists.", 409)


@api.post("/auth/demo")
def demo_login():
    user = _ensure_demo_account()
    return _session_response(user)


@api.post("/auth/login")
def login():
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str) or len(email) > 320 or len(password) > 128:
        return _error("invalid_credentials", "Email or password is incorrect.", 401)
    identity = _hash(email.strip().lower())
    now = utcnow()
    attempt = db.session.get(LoginAttempt, identity)
    if attempt and attempt.blocked_until and attempt.blocked_until > now:
        return _error("rate_limited", "Too many sign-in attempts. Try again later.", 429)
    user = User.query.filter(func.lower(User.email) == email.strip().lower()).first()
    candidate_hash = user.password if user and user.password != "google_oauth" else _DUMMY_PASSWORD_HASH
    password_matches = check_password_hash(candidate_hash, password or "")
    valid = bool(user and user.password != "google_oauth" and password_matches)
    if not valid:
        for retry in range(4):
            if not attempt or now - attempt.window_started_at > timedelta(seconds=current_app.config["LOGIN_WINDOW_SECONDS"]):
                attempt = LoginAttempt(identity_hash=identity, attempts=0, window_started_at=now)
                db.session.add(attempt)
            attempt.attempts += 1
            if attempt.attempts >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
                attempt.blocked_until = now + timedelta(seconds=current_app.config["LOGIN_WINDOW_SECONDS"])
            try:
                db.session.commit()
                break
            except IntegrityError:
                db.session.rollback()
                attempt = db.session.get(LoginAttempt, identity)
                if retry == 3:
                    raise
        return _error("invalid_credentials", "Email or password is incorrect.", 401)
    if attempt:
        db.session.delete(attempt)
        db.session.commit()
    return _session_response(user)


@api.get("/auth/me")
@require_user
def me():
    return jsonify({"user": _user_payload(g.current_user)})


@api.post("/auth/logout")
@require_user
def logout():
    g.auth_session.revoked_at = utcnow()
    db.session.commit()
    response = make_response(jsonify({"ok": True}))
    return _clear_auth_cookies(response)


def _record_fallback(kind):
    # Without a provider every review falls back by design; count only real provider failures.
    if ai_service.AI_ENABLED:
        telemetry.record(kind, "groq", "fallback")


@api.get("/admin/metrics")
@require_user
def admin_metrics():
    """AI and voice call metrics for operators listed in ADMIN_EMAILS; hidden from everyone else."""
    if g.current_user.email.lower() not in current_app.config["ADMIN_EMAILS"]:
        return _error("not_found", "Resource not found.", 404)
    try:
        days = int(request.args.get("days", 7))
    except ValueError:
        return _error("invalid_days", "days must be a whole number from 1 to 90.", 400)
    if not 1 <= days <= 90:
        return _error("invalid_days", "days must be a whole number from 1 to 90.", 400)
    return jsonify(telemetry.summarize(days))


@api.get("/capabilities")
@require_user
def capabilities():
    from .ai_service import AI_ENABLED
    return jsonify({"voice": voice_service.VOICE_ENABLED, "ai": AI_ENABLED})


@api.get("/dashboard")
@require_user
def dashboard():
    user_id = g.current_user.id
    total = Interview.query.filter_by(user_id=user_id).count()
    response_count = Response.query.filter_by(user_id=user_id).count()
    average = db.session.query(func.avg(Response.score)).join(Interview, Interview.id == Response.interview_id).filter(
        Response.user_id == user_id, Response.score.isnot(None), _visible_score_filter()).scalar()
    latest = Interview.query.filter_by(user_id=user_id).order_by(Interview.created_at.desc(), Interview.id.desc()).limit(5).all()
    recent = []
    for item in latest:
        count = Response.query.filter_by(interview_id=item.id).count()
        avg = db.session.query(func.avg(Response.score)).filter(Response.interview_id == item.id, Response.score.isnot(None)).scalar()
        recent.append({"id": item.id, "type": _public_type(item.interview_type), "label": _type_label(item),
                       "mode": item.mode, "difficulty": item.difficulty,
                       "status": item.status, "created_at": item.created_at.isoformat() + "Z",
                       "responses": count, "average": round(float(avg), 1) if avg is not None and not _scores_hidden(item) else None})
    return jsonify({"summary": {"sessions": total, "responses": response_count,
                                "average_score": round(float(average), 1) if average is not None else None},
                    "recent": recent})


def _public_challenge(problem):
    return {key: problem[key] for key in ("title", "description", "difficulty", "topic", "constraints", "examples", "starter_code")}


@api.post("/interviews")
@require_user
def create_interview():
    data = _json_body() or {}
    kind = data.get("type")
    if kind == "tech":
        return _create_tech_interview(data)
    if kind not in {"round1", "coding"}:
        return _error("invalid_interview_type", "Choose a tech interview or coding practice.", 400)
    interview = Interview(user_id=g.current_user.id,
                          interview_type="round1" if kind == "round1" else "round2_ai",
                          difficulty="personal" if kind == "round1" else "hard")
    db.session.add(interview)
    db.session.flush()
    if kind == "coding":
        for position in range(3):
            problem = dict(curated_problem(position))
            problem["source"] = "Curated practice"
            db.session.add(CodingChallenge(interview_id=interview.id, position=position,
                                           challenge_json=json.dumps(problem, ensure_ascii=False)))
    db.session.commit()
    first = {"question": ROUND1_QUESTIONS[0]} if kind == "round1" else {"challenge": _public_challenge(curated_problem(0)), "position": 0, "total": 3}
    return jsonify({"interview": {"id": interview.id, "type": kind, "status": interview.status}, **first}), 201


def _create_tech_interview(data):
    role_key, level, mode = data.get("role"), data.get("level"), data.get("mode")
    custom_role = data.get("custom_role", "")
    focus = data.get("focus", "")
    voice_only, proctored = data.get("voice_only", False), data.get("proctored", False)
    if role_key not in tech_interview.ROLES and role_key != "custom":
        return _error("invalid_role", "Choose the role you are interviewing for.", 400)
    if role_key == "custom" and (not isinstance(custom_role, str) or not 2 <= len(custom_role.strip()) <= tech_interview.MAX_CUSTOM_ROLE_LENGTH):
        return _error("invalid_role", "Enter a role title between 2 and 60 characters.", 400)
    if level not in tech_interview.LEVELS:
        return _error("invalid_level", "Choose your experience level.", 400)
    if mode not in tech_interview.MODES:
        return _error("invalid_mode", "Choose practice or assessment.", 400)
    if not isinstance(focus, str) or len(focus) > tech_interview.MAX_FOCUS_LENGTH:
        return _error("invalid_focus", "Focus areas must be at most 200 characters.", 400)
    if not isinstance(voice_only, bool) or not isinstance(proctored, bool):
        return _error("invalid_options", "Interview options are invalid.", 400)
    if _rate_limited("interview"):
        return _rate_limit_error()
    role = tech_interview.role_title(role_key, custom_role.strip() if isinstance(custom_role, str) else "")
    focus = " ".join(focus.split())
    plan, _generated = tech_interview.plan_interview(role, level, focus, mode, role_key)
    interview = Interview(user_id=g.current_user.id, interview_type="tech", difficulty=level, role=role, level=level,
                          mode=mode, voice_only=voice_only, proctored=proctored or mode == "assessment",
                          focus=focus or None, plan_json=json.dumps(plan, ensure_ascii=False))
    db.session.add(interview)
    db.session.flush()
    first = plan[0]
    greeting = (f"Hi, I'm Alex, and I'll be your interviewer for this {role} {'assessment' if mode == 'assessment' else 'practice session'}. "
                f"We'll go through {len(plan)} questions. Take a moment before each answer if you need it. Let's begin.")
    db.session.add(InterviewQuestion(interview_id=interview.id, position=0, question=first["question"],
                                     category=first["category"], intro=greeting, is_follow_up=False))
    db.session.commit()
    return jsonify({"interview": {"id": interview.id, "type": "tech", "status": interview.status}}), 201


def _tech_state(interview):
    plan = json.loads(interview.plan_json or "[]")
    questions = InterviewQuestion.query.filter_by(interview_id=interview.id).order_by(InterviewQuestion.position).all()
    responses = {item.question_position: item for item in Response.query.filter_by(interview_id=interview.id).all()}
    return plan, questions, responses


def _integrity(interview):
    rows = db.session.query(ProctorEvent.kind, func.count(ProctorEvent.id), func.coalesce(func.sum(ProctorEvent.duration_ms), 0)).filter(
        ProctorEvent.interview_id == interview.id).group_by(ProctorEvent.kind).all()
    events = {kind: {"count": count, "seconds": round(int(total) / 1000)} for kind, count, total in rows}
    warnings = sum(item["count"] for item in events.values())
    return {"monitored": bool(interview.proctored), "warnings": warnings, "events": events,
            "status": "clean" if warnings == 0 else "minor" if warnings <= 3 else "flagged"}


def _tech_payload(interview):
    plan, questions, responses = _tech_state(interview)
    reveal = interview.mode == "practice" or interview.status == "completed"
    main_total = len(plan)
    turns, main_seen, current = [], 0, None
    for item in questions:
        if not item.is_follow_up:
            main_seen += 1
        answered = responses.get(item.position)
        if answered is None:
            current = {"position": item.position, "question": item.question, "category": item.category,
                       "category_label": tech_interview.CATEGORIES.get(item.category, item.category),
                       "intro": item.intro, "is_follow_up": item.is_follow_up, "number": main_seen, "total": main_total}
            continue
        feedback = json.loads(answered.feedback) if answered.feedback else None
        turns.append({"id": answered.id, "position": item.position, "question": item.question, "category": item.category,
                      "category_label": tech_interview.CATEGORIES.get(item.category, item.category),
                      "is_follow_up": item.is_follow_up, "answer": answered.answer,
                      "feedback": json.dumps(feedback, ensure_ascii=False) if reveal and feedback else None,
                      "score": answered.score if reveal else None})
    return {"role": interview.role, "level": interview.level, "level_label": tech_interview.LEVELS.get(interview.level, interview.level),
            "mode": interview.mode, "voice_only": interview.voice_only, "proctored": interview.proctored,
            "focus": interview.focus or "", "current_question": current if interview.status != "completed" else None,
            "answered_main": sum(1 for turn in turns if not turn["is_follow_up"]), "total_main": main_total,
            "turns": turns, "report": json.loads(interview.report_json) if interview.report_json else None,
            "integrity": _integrity(interview)}


def _get_owned_interview(interview_id):
    return Interview.query.filter_by(id=interview_id, user_id=g.current_user.id).first()


@api.get("/interviews/<int:interview_id>")
@require_user
def get_interview(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview:
        return _error("not_found", "Interview not found.", 404)
    responses = Response.query.filter_by(interview_id=interview.id, user_id=g.current_user.id).order_by(Response.question_position.asc(), Response.created_at.asc()).all()
    avg = db.session.query(func.avg(Response.score)).filter(Response.interview_id == interview.id, Response.score.isnot(None)).scalar()
    result = {"id": interview.id, "type": _public_type(interview.interview_type),
              "status": interview.status, "difficulty": interview.difficulty,
              "created_at": interview.created_at.isoformat() + "Z",
              "average_score": round(float(avg), 1) if avg is not None else None,
              "voice_enabled": voice_service.VOICE_ENABLED and interview.interview_type in {"round1", "tech"},
              "responses": [{"id": item.id, "position": item.question_position, "question": item.question,
                             "answer": item.answer, "feedback": item.feedback, "score": item.score,
                             "created_at": item.created_at.isoformat() + "Z"} for item in responses]}
    if interview.interview_type == "tech":
        result.update(_tech_payload(interview))
        if interview.mode == "assessment" and interview.status != "completed":
            for item in result["responses"]:
                item["feedback"], item["score"] = None, None
            result["average_score"] = None
    elif interview.interview_type == "round1":
        done_positions = {item.question_position for item in responses}
        position = next((candidate for candidate in range(len(ROUND1_QUESTIONS)) if candidate not in done_positions), len(ROUND1_QUESTIONS))
        if position < len(ROUND1_QUESTIONS):
            result["next_question"] = {"position": position, "total": len(ROUND1_QUESTIONS), "question": ROUND1_QUESTIONS[position]}
    else:
        challenges = CodingChallenge.query.filter_by(interview_id=interview.id).order_by(CodingChallenge.position).all()
        done_positions = {item.question_position for item in responses}
        next_position = next((challenge.position for challenge in challenges if challenge.position not in done_positions), None)
        result["next_challenge"] = None
        if next_position is not None:
            challenge = challenges[next_position]
            result["next_challenge"] = {"position": challenge.position, "total": len(challenges),
                                        "challenge": _public_challenge(json.loads(challenge.challenge_json))}
    return jsonify({"interview": result})


@api.post("/interviews/<int:interview_id>/answers")
@require_user
def submit_interview_answer(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type != "round1":
        return _error("not_found", "Interview not found.", 404)
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    answer = data.get("answer", "")
    skip = data.get("skip", False)
    if not isinstance(skip, bool) or not isinstance(answer, str):
        return _error("invalid_answer", "Answer must be text.", 400)
    answer = answer.strip()
    if len(answer) > MAX_ANSWER_LENGTH:
        return _error("answer_too_long", "Answer must be at most 20,000 characters.", 413)
    if not answer and not skip:
        return _error("answer_required", "Write an answer or skip this question.", 400)
    existing_positions = {item.question_position for item in Response.query.filter_by(interview_id=interview.id, user_id=g.current_user.id).all()}
    position = next((candidate for candidate in range(len(ROUND1_QUESTIONS)) if candidate not in existing_positions), len(ROUND1_QUESTIONS))
    if position >= len(ROUND1_QUESTIONS) or interview.status == "completed":
        return _error("interview_completed", "This interview is already complete.", 409)
    if _rate_limited("answer"):
        return _rate_limit_error()
    question = ROUND1_QUESTIONS[position]
    stored_answer = answer if answer else "(skipped)"
    try:
        feedback = review_interview_answer(question, stored_answer)
    except Exception:
        current_app.logger.warning("AI answer review failed; using the fallback", exc_info=True)
        _record_fallback("answer_review")
        feedback = fallback_interview_feedback(stored_answer)
    feedback_text = json.dumps(feedback, ensure_ascii=False)
    response = Response(user_id=g.current_user.id, interview_id=interview.id, question=question,
                        answer=stored_answer, feedback=feedback_text, score=feedback["score"], question_position=position)
    db.session.add(response)
    if position + 1 == len(ROUND1_QUESTIONS):
        interview.status = "completed"
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("answer_conflict", "Another answer was saved. Refresh this interview before continuing.", 409)
    items = Response.query.filter_by(interview_id=interview.id).all()
    average = round(sum(float(item.score or 0) for item in items) / max(1, len(items)), 1)
    completed = position + 1 == len(ROUND1_QUESTIONS)
    return jsonify({"feedback": feedback, "completed": completed, "average_score": average,
                    "qualified": completed and average >= 7,
                    "next_question": None if completed else {"position": position + 1, "total": len(ROUND1_QUESTIONS), "question": ROUND1_QUESTIONS[position + 1]}})


@api.get("/interviews/<int:interview_id>/questions/<int:position>/audio")
@require_user
def question_audio(interview_id, position):
    interview = _get_owned_interview(interview_id)
    text_to_speak = None
    if interview and interview.interview_type == "round1" and 0 <= position < len(ROUND1_QUESTIONS):
        text_to_speak = ROUND1_QUESTIONS[position]
    elif interview and interview.interview_type == "tech":
        # Only interviewer-authored text stored with the session is ever voiced.
        item = InterviewQuestion.query.filter_by(interview_id=interview.id, position=position).first()
        if item:
            text_to_speak = f"{item.intro} {item.question}" if item.intro else item.question
    if not text_to_speak:
        return _error("not_found", "Question not found.", 404)
    if not voice_service.VOICE_ENABLED:
        return _error("voice_unavailable", "Voice mode is not configured.", 503)
    try:
        audio = voice_service.synthesize(text_to_speak)
    except voice_service.VoiceError:
        current_app.logger.exception("Question speech synthesis failed")
        return _error("voice_unavailable", "The interviewer voice is unavailable. Read the question instead.", 503)
    return HttpResponse(audio, mimetype="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@api.post("/interviews/<int:interview_id>/transcriptions")
@require_user
def transcribe_answer(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type not in {"round1", "tech"}:
        return _error("not_found", "Interview not found.", 404)
    if interview.status == "completed":
        return _error("interview_completed", "This interview is already complete.", 409)
    if not voice_service.VOICE_ENABLED:
        return _error("voice_unavailable", "Voice mode is not configured.", 503)
    request.max_content_length = MAX_AUDIO_BYTES + 64 * 1024
    upload = request.files.get("audio")
    if upload is None:
        return _error("audio_required", "Record an answer before sending it.", 400)
    content_type = (upload.mimetype or "").split(";")[0].strip().lower()
    if content_type not in voice_service.ALLOWED_AUDIO_TYPES:
        return _error("unsupported_audio", "This audio format is not supported.", 415)
    audio = upload.read(MAX_AUDIO_BYTES + 1)
    if not audio:
        return _error("audio_required", "The recording was empty. Try again.", 400)
    if len(audio) > MAX_AUDIO_BYTES:
        return _error("audio_too_large", "Recordings must be at most 10 MB.", 413)
    if _rate_limited("transcription"):
        return _rate_limit_error()
    try:
        transcript = voice_service.transcribe(audio, upload.filename, content_type)
    except voice_service.VoiceError:
        current_app.logger.exception("Answer transcription failed")
        return _error("transcription_failed", "We couldn't transcribe that recording. Try again or type your answer.", 502)
    return jsonify({"transcript": transcript[:MAX_ANSWER_LENGTH]})


@api.post("/interviews/<int:interview_id>/turns")
@require_user
def submit_tech_turn(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type != "tech":
        return _error("not_found", "Interview not found.", 404)
    if interview.status == "completed":
        return _error("interview_completed", "This interview is already complete.", 409)
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    answer, skip, position = data.get("answer", ""), data.get("skip", False), data.get("position")
    if not isinstance(answer, str) or not isinstance(skip, bool):
        return _error("invalid_answer", "Answer must be text.", 400)
    answer = answer.strip()
    if len(answer) > MAX_ANSWER_LENGTH:
        return _error("answer_too_long", "Answer must be at most 20,000 characters.", 413)
    if not answer and not skip:
        return _error("answer_required", "Answer the question or skip it.", 400)
    plan, questions, responses = _tech_state(interview)
    current = next((item for item in questions if item.position not in responses), None)
    if current is None:
        return _error("interview_completed", "This interview is already complete.", 409)
    if position is not None and position != current.position:
        return _error("out_of_order", "This question was already answered. Refresh to continue.", 409)
    if _rate_limited("answer"):
        return _rate_limit_error()
    stored_answer = answer or "(skipped)"
    follow_ups_used = sum(1 for item in questions if item.is_follow_up)
    main_asked = sum(1 for item in questions if not item.is_follow_up)
    follow_up_allowed = not current.is_follow_up and follow_ups_used < tech_interview.MAX_FOLLOW_UPS
    feedback = tech_interview.evaluate_turn(role=interview.role, level=interview.level, mode=interview.mode,
                                            question=current.question, category=current.category, answer=stored_answer,
                                            is_follow_up=current.is_follow_up, follow_up_allowed=follow_up_allowed,
                                            position=current.position)
    reaction, follow_up = feedback.pop("reaction"), feedback.pop("follow_up")
    db.session.add(Response(user_id=g.current_user.id, interview_id=interview.id, question=current.question,
                            answer=stored_answer, feedback=json.dumps(feedback, ensure_ascii=False),
                            score=feedback["score"], question_position=current.position))
    if interview.mode == "assessment" and current.position > 0 and current.created_at:
        overtime = (utcnow() - current.created_at).total_seconds() - ASSESSMENT_ANSWER_SECONDS - ASSESSMENT_GRACE_SECONDS
        if overtime > 0:
            db.session.add(ProctorEvent(interview_id=interview.id, kind="late_answer",
                                        duration_ms=min(int(overtime * 1000), 3_600_000), question_position=current.position))
    next_item = None
    if follow_up:
        next_item = InterviewQuestion(interview_id=interview.id, position=current.position + 1, question=follow_up,
                                      category=current.category, intro=reaction, is_follow_up=True)
    elif main_asked < len(plan):
        upcoming = plan[main_asked]
        next_item = InterviewQuestion(interview_id=interview.id, position=current.position + 1, question=upcoming["question"],
                                      category=upcoming["category"], intro=f"{reaction} Next question.", is_follow_up=False)
    else:
        interview.status = "completed"
    if next_item:
        db.session.add(next_item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("answer_conflict", "Another answer was saved. Refresh this interview before continuing.", 409)
    reveal = interview.mode == "practice"
    return jsonify({"feedback": feedback if reveal else None, "reaction": reaction,
                    "completed": interview.status == "completed",
                    "closing": "That's the end of our interview. Thank you, I'm putting your report together now." if interview.status == "completed" else None})


@api.post("/interviews/<int:interview_id>/report")
@require_user
def create_tech_report(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type != "tech":
        return _error("not_found", "Interview not found.", 404)
    if interview.status != "completed":
        return _error("interview_in_progress", "Finish the interview to see your report.", 409)
    if interview.report_json:
        return jsonify({"report": json.loads(interview.report_json)})
    _plan, questions, responses = _tech_state(interview)
    turns = [{"question": item.question, "category": item.category, "answer": responses[item.position].answer,
              "score": responses[item.position].score} for item in questions if item.position in responses]
    report = tech_interview.build_report(role=interview.role, level=interview.level, mode=interview.mode,
                                         turns=turns, integrity=_integrity(interview))
    # Keep only an AI report, so a transient provider failure is retried on the next visit.
    if report["automated"]:
        interview.report_json = json.dumps(report, ensure_ascii=False)
        db.session.commit()
    return jsonify({"report": report})


@api.post("/interviews/<int:interview_id>/proctor-events")
@require_user
def record_proctor_events(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type != "tech":
        return _error("not_found", "Interview not found.", 404)
    if interview.status == "completed":
        return jsonify({"recorded": 0})
    data = _json_body()
    events = data.get("events") if data else None
    if not isinstance(events, list) or len(events) > 50:
        return _error("invalid_events", "Send up to 50 events.", 400)
    stored = ProctorEvent.query.filter_by(interview_id=interview.id).count()
    recorded = 0
    for event in events:
        if stored + recorded >= MAX_PROCTOR_EVENTS:
            break
        if not isinstance(event, dict) or event.get("kind") not in PROCTOR_KINDS:
            return _error("invalid_events", "Unknown event type.", 400)
        duration, position = event.get("duration_ms", 0), event.get("position")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 0 <= duration <= 3_600_000:
            return _error("invalid_events", "Event duration is invalid.", 400)
        if position is not None and (not isinstance(position, int) or isinstance(position, bool) or not 0 <= position < 100):
            return _error("invalid_events", "Event position is invalid.", 400)
        db.session.add(ProctorEvent(interview_id=interview.id, kind=event["kind"], duration_ms=duration, question_position=position))
        recorded += 1
    db.session.commit()
    return jsonify({"recorded": recorded})


@api.post("/interviews/<int:interview_id>/submissions")
@require_user
def submit_code(interview_id):
    interview = _get_owned_interview(interview_id)
    if not interview or interview.interview_type != "round2_ai":
        return _error("not_found", "Coding practice session not found.", 404)
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    code = data.get("code", "")
    position = data.get("position")
    if not isinstance(code, str) or not code.strip():
        return _error("code_required", "Write a solution before submitting.", 400)
    if len(code) > MAX_CODE_LENGTH:
        return _error("code_too_long", "Submission must be at most 100,000 characters.", 413)
    if not isinstance(position, int) or isinstance(position, bool) or not 0 <= position < 3:
        return _error("invalid_position", "Challenge position is invalid.", 400)
    challenge = CodingChallenge.query.filter_by(interview_id=interview.id, position=position).first()
    if not challenge:
        return _error("not_found", "Challenge not found.", 404)
    if Response.query.filter_by(interview_id=interview.id, user_id=g.current_user.id, question_position=position).first():
        return _error("submission_exists", "This challenge has already been submitted.", 409)
    completed_positions = {item.question_position for item in Response.query.filter_by(interview_id=interview.id, user_id=g.current_user.id).all()}
    expected_position = next((candidate for candidate in range(3) if candidate not in completed_positions), None)
    if position != expected_position:
        return _error("out_of_order", "Submit challenges in order. Refresh the session to continue.", 409)
    if _rate_limited("answer"):
        return _rate_limit_error()
    problem = json.loads(challenge.challenge_json)
    try:
        evaluation = review_code_submission(problem, code)
    except Exception:
        current_app.logger.warning("AI code review failed; saving without a review", exc_info=True)
        _record_fallback("code_review")
        evaluation = {"is_correct": None, "score": None,
                      "summary": "Your code was saved, but automated review is unavailable. Your submission remains in history.",
                      "strengths": [], "improvements": [], "show_solution": False, "automated": False}
    score = evaluation["score"]
    if evaluation.get("show_solution"):
        evaluation["reference_solution"] = problem["solution_code"]
    response = Response(user_id=g.current_user.id, interview_id=interview.id, question=problem["title"],
                        answer=code, feedback=json.dumps(evaluation, ensure_ascii=False), score=score,
                        question_position=position)
    db.session.add(response)
    if position == 2:
        interview.status = "completed"
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("submission_conflict", "Another submission was saved for this challenge.", 409)
    next_challenge = None
    if position < 2:
        following = CodingChallenge.query.filter_by(interview_id=interview.id, position=position + 1).first()
        next_challenge = {"position": following.position, "total": 3,
                          "challenge": _public_challenge(json.loads(following.challenge_json))} if following else None
    return jsonify({"evaluation": evaluation, "completed": position == 2, "next_challenge": next_challenge})


@api.get("/history")
@require_user
def history():
    rows = db.session.query(Response, Interview).join(Interview, Interview.id == Response.interview_id).filter(
        Response.user_id == g.current_user.id).order_by(Response.created_at.desc(), Response.id.desc()).limit(300).all()
    return jsonify({"responses": [{"id": response.id, "interview_id": interview.id,
                                   "type": _public_type(interview.interview_type), "label": _type_label(interview),
                                   "question": response.question, "answer": response.answer,
                                   "feedback": None if _scores_hidden(interview) else response.feedback,
                                   "score": None if _scores_hidden(interview) else response.score,
                                   "created_at": response.created_at.isoformat() + "Z"}
                                  for response, interview in rows]})


@api.delete("/history/<int:response_id>")
@require_user
def delete_history_item(response_id):
    item = Response.query.filter_by(id=response_id, user_id=g.current_user.id).first()
    if not item:
        return _error("not_found", "History item not found.", 404)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


@api.delete("/history")
@require_user
def clear_history():
    Response.query.filter_by(user_id=g.current_user.id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True})


@api.get("/analytics")
@require_user
def analytics():
    user_id = g.current_user.id
    visible = (Response.user_id == user_id, Response.score.isnot(None), _visible_score_filter())
    average = db.session.query(func.avg(Response.score)).join(Interview, Interview.id == Response.interview_id).filter(*visible).scalar()
    per_type = db.session.query(Interview.interview_type, func.avg(Response.score), func.count(Response.id)).join(
        Response, Response.interview_id == Interview.id).filter(*visible).group_by(Interview.interview_type).all()
    daily = db.session.query(func.date(Response.created_at), func.avg(Response.score), func.count(Response.id)).join(
        Interview, Interview.id == Response.interview_id).filter(*visible).group_by(func.date(Response.created_at)).order_by(func.date(Response.created_at)).all()
    return jsonify({"average_score": round(float(average), 1) if average is not None else None,
                    "by_type": [{"type": {"round1": "Personal interview", "tech": "Tech interview"}.get(kind, "Coding practice"),
                                 "average": round(float(score), 1), "responses": count} for kind, score, count in per_type],
                    "daily": [{"date": str(day), "average": round(float(score), 1), "responses": count}
                              for day, score, count in daily]})


@api.put("/profile")
@require_user
def update_profile():
    data = _json_body()
    if data is None:
        return _error("invalid_json", "Send a JSON request body.", 400)
    name = data.get("name", g.current_user.full_name or g.current_user.name)
    bio = data.get("bio", g.current_user.bio or "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 160:
        return _error("invalid_name", "Name must be between 1 and 160 characters.", 400)
    if not isinstance(bio, str) or len(bio) > 1000:
        return _error("invalid_bio", "Bio must be at most 1,000 characters.", 400)
    g.current_user.name = name.strip()
    g.current_user.full_name = name.strip()
    g.current_user.bio = bio.strip()
    db.session.commit()
    return jsonify({"user": _user_payload(g.current_user)})


@api.get("/achievements")
@require_user
def achievements():
    user_id = g.current_user.id
    sessions = Interview.query.filter_by(user_id=user_id).count()
    completed = Interview.query.filter_by(user_id=user_id, status="completed").count()
    scores = [float(value) for (value,) in db.session.query(Response.score).join(Interview, Interview.id == Response.interview_id).filter(
        Response.user_id == user_id, Response.score.isnot(None), _visible_score_filter()).all()]
    return jsonify({"achievements": [
        {"id": "first_session", "title": "First practice", "description": "Complete your first practice session.", "unlocked": completed >= 1},
        {"id": "five_sessions", "title": "Consistent practice", "description": "Complete five practice sessions.", "unlocked": completed >= 5},
        {"id": "strong_answer", "title": "Strong response", "description": "Earn a score of 8 or higher.", "unlocked": any(score >= 8 for score in scores)},
        {"id": "practice_started", "title": "Getting started", "description": "Create your first practice session.", "unlocked": sessions >= 1},
    ]})


_DUMMY_PASSWORD_HASH = generate_password_hash("skillmentor-invalid-user-dummy-password")
