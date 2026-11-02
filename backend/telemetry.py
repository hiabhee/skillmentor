"""Record latency, token use and outcome for every AI and voice provider call.

Calls are buffered on the request and saved after the response is built, in their own commit,
so telemetry never slows a provider call or breaks a candidate's interview.
"""

import logging
import math
from datetime import timedelta

from flask import g, has_app_context

from .extensions import db
from .models import AICall, utcnow

logger = logging.getLogger(__name__)

STATUSES = {"ok", "error", "fallback", "cached"}


def record(kind, provider, status, latency_ms=None, prompt_tokens=None, completion_tokens=None, error=None):
    """Buffer one call for this request. Outside a request (scripts, CLI) nothing is stored."""
    if not has_app_context() or status not in STATUSES:
        return
    buffered = g.setdefault("ai_calls", [])
    buffered.append(AICall(
        kind=kind[:40], provider=provider[:20], status=status,
        latency_ms=None if latency_ms is None else max(0, round(latency_ms)),
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        error=(error or "")[:80] or None,
    ))


def flush(response):
    """after_request hook: persist buffered calls without committing anything the route left pending."""
    calls = g.pop("ai_calls", None)
    if not calls:
        return response
    try:
        # A route that returned without committing meant to discard its changes; keep it that way.
        db.session.rollback()
        db.session.add_all(calls)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("Could not save AI call telemetry", exc_info=True)
    return response


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    index = max(0, math.ceil(pct / 100 * len(sorted_values)) - 1)
    return sorted_values[index]


def _mean(values):
    return round(sum(values) / len(values)) if values else None


def summarize(days=7):
    """Per-kind call volume, success, fallback and cache rates, latency percentiles and token use."""
    since = utcnow() - timedelta(days=days)
    rows = db.session.execute(
        db.select(AICall.kind, AICall.provider, AICall.status, AICall.latency_ms,
                  AICall.prompt_tokens, AICall.completion_tokens).where(AICall.created_at >= since)
    ).all()
    groups = {}
    for row in rows:
        groups.setdefault(row.kind, []).append(row)

    kinds = []
    for kind in sorted(groups):
        items = groups[kind]
        counts = {status: sum(1 for item in items if item.status == status) for status in STATUSES}
        attempted = counts["ok"] + counts["error"]
        latencies = sorted(item.latency_ms for item in items if item.status == "ok" and item.latency_ms is not None)
        completion = [item.completion_tokens for item in items if item.status == "ok" and item.completion_tokens is not None]
        prompt = [item.prompt_tokens for item in items if item.status == "ok" and item.prompt_tokens is not None]
        served = attempted + counts["cached"]
        kinds.append({
            "kind": kind,
            "provider": items[0].provider,
            "calls": len(items),
            "ok": counts["ok"],
            "errors": counts["error"],
            "fallbacks": counts["fallback"],
            "cached": counts["cached"],
            "success_rate": round(counts["ok"] / attempted, 4) if attempted else None,
            "cache_hit_rate": round(counts["cached"] / served, 4) if counts["cached"] and served else None,
            "latency_ms": {"p50": _percentile(latencies, 50), "p95": _percentile(latencies, 95),
                           "max": latencies[-1] if latencies else None},
            "avg_prompt_tokens": _mean(prompt),
            "avg_completion_tokens": _mean(completion),
        })
    return {"window_days": days, "since": since.isoformat() + "Z", "total_calls": len(rows), "kinds": kinds}
