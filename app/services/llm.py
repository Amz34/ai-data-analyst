"""LLM wrapper with crashproof behaviour: primary DeepSeek + Gemini fallback
(OpenAI-compatible), automatic circuit breaker, retries with backoff + jitter,
and per-call tracing.

Contract (unchanged): chat(system, user, max_tokens=400, temperature=0.3) -> str.
Returns "" on total failure so callers fall back to rule-based answers.
"""
import os
import random
import threading
import time

import requests

from ..config import (
    CREDS_FILE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_CIRCUIT_COOLDOWN_S,
    LLM_CIRCUIT_THRESHOLD,
    LLM_FALLBACK_BASE_URL,
    LLM_FALLBACK_KEY,
    LLM_FALLBACK_MODEL,
    LLM_MODEL,
    LLM_PRIMARY_RETRIES,
    LLM_TIMEOUT,
)
from .trace import log_event

# ---------------------------------------------------------------------------
# Circuit-breaker state (per-process; uvicorn workers each keep their own copy)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_state = {
    "mode": "CLOSED",          # CLOSED | OPEN | HALF_OPEN
    "failures": 0,             # consecutive infra failures on primary
    "opened_ts": None,         # when breaker opened (epoch seconds)
    "last_error": None,
}

_INFRA_STATUS = {408, 429, 500, 502, 503, 504}


def _load_key(env_name):
    """Key resolution: process env first, then the host credentials file."""
    val = os.getenv(env_name, "") or ""
    if val:
        return val.strip()
    try:
        with open(CREDS_FILE, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == env_name:
                    return v.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


_PRIMARY_KEY = _load_key("DEEPSEEK_API_KEY") or LLM_API_KEY
_FALLBACK_KEY = _load_key("GOOGLE_API_KEY") or LLM_FALLBACK_KEY


def _primary_url():
    base = LLM_BASE_URL.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def _fallback_url():
    base = LLM_FALLBACK_BASE_URL.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def _attempt(url, api_key, model, system, user, max_tokens, temperature, timeout_s=None):
    """One POST. Returns (ok, content, err, is_infra)."""
    timeout = timeout_s if timeout_s else float(LLM_TIMEOUT or 60)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        r = requests.post(
            url,
            json=payload,
            headers={"Authorization": "Bearer %s" % api_key},
            timeout=timeout,
        )
        if r.status_code == 200:
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            content = (content or "").strip()
            if content:
                return True, content, None, False
            return False, None, "empty_content", False
        err = "http_%s" % r.status_code
        return False, None, err, r.status_code in _INFRA_STATUS
    except requests.RequestException as e:
        return False, None, "conn_error: %s" % type(e).__name__, True
    except Exception as e:  # noqa: BLE001 - keep the wrapper total-failure-safe
        return False, None, "error: %s" % type(e).__name__, False


def _backoff(attempt):
    return min(2 ** attempt, 4) + random.uniform(0, 0.5)


def _now_open_ts():
    with _lock:
        _state["mode"] = "OPEN"
        _state["opened_ts"] = time.time()
        _state["last_error"] = "primary_unhealthy"


def _record_failure(err):
    with _lock:
        _state["failures"] += 1
        _state["last_error"] = err
        if _state["failures"] >= LLM_CIRCUIT_THRESHOLD:
            _state["mode"] = "OPEN"
            _state["opened_ts"] = time.time()
            log_event(event="breaker", action="open", failures=_state["failures"],
                      cooldown_s=LLM_CIRCUIT_COOLDOWN_S)
            return True
        log_event(event="breaker", action="failure_counted", failures=_state["failures"])
        return False


def _record_success():
    with _lock:
        if _state["mode"] == "HALF_OPEN":
            log_event(event="breaker", action="close")
        _state["mode"] = "CLOSED"
        _state["failures"] = 0


def get_llm_state():
    """Snapshot for /api/healthz."""
    with _lock:
        mode = _state["mode"]
        opened_ts = _state["opened_ts"]
        if mode == "OPEN" and opened_ts:
            left = max(0, int(LLM_CIRCUIT_COOLDOWN_S - (time.time() - opened_ts)))
        else:
            left = 0
        return {
            "state": mode,
            "primary": {"model": LLM_MODEL, "provider": "deepseek",
                        "key_configured": bool(_PRIMARY_KEY)},
            "fallback": {"model": LLM_FALLBACK_MODEL, "provider": "gemini",
                         "key_configured": bool(_FALLBACK_KEY)},
            "consecutive_failures": _state["failures"],
            "cooldown_left_s": left,
            "last_error": _state["last_error"],
        }


def chat(system: str, user: str, max_tokens: int = 400, temperature: float = 0.3) -> str:
    """Ask the LLM. DeepSeek primary; Gemini fallback; returns "" only if both fail."""
    t0 = time.time()
    if not _PRIMARY_KEY and not _FALLBACK_KEY:
        log_event(event="llm_call", provider="none", ok=False, err="no_keys")
        return ""

    def try_primary():
        """Retries on infra errors only; returns (True, content) or (False, err)."""
        for attempt in range(LLM_PRIMARY_RETRIES + 1):
            ok, content, err, infra = _attempt(
                _primary_url(), _PRIMARY_KEY, LLM_MODEL, system, user,
                max_tokens, temperature,
            )
            if ok:
                return True, content
            if attempt < LLM_PRIMARY_RETRIES and infra:
                time.sleep(_backoff(attempt))
        return False, err or "primary_failed"

    def try_fallback():
        # Gemini thinks before answering; give it headroom on the token budget.
        fb_tokens = max(800, max_tokens * 2)
        # Cap fallback latency: never let one call hang 60s when the primary is down.
        fb_timeout = min(float(LLM_TIMEOUT or 60), 20.0)
        ok, content, err, _ = _attempt(
            _fallback_url(), _FALLBACK_KEY, LLM_FALLBACK_MODEL, system, user,
            fb_tokens, temperature, timeout_s=fb_timeout,
        )
        if ok:
            return True, content
        return False, err or "fallback_failed"

    with _lock:
        mode = _state["mode"]
        opened_ts = _state["opened_ts"]
        in_cooldown = mode == "OPEN" and opened_ts and (
            time.time() - opened_ts) < LLM_CIRCUIT_COOLDOWN_S
    # From HALF_OPEN (probe allowed): treat as cooldown-elapsed primary probe below.
    probe_primary = mode in ("CLOSED", "HALF_OPEN") or not in_cooldown

    if _PRIMARY_KEY and probe_primary:
        ok, content = try_primary()
        if ok:
            _record_success()
            log_event(event="llm_call", provider="deepseek", model=LLM_MODEL, ok=True,
                      latency_ms=round((time.time() - t0) * 1000, 1))
            return content
        err = content if isinstance(content, str) else "primary_failed"
        with _lock:
            prev_mode = _state["mode"]
            if prev_mode in ("CLOSED", "HALF_OPEN"):
                _state["failures"] += 1
                _state["last_error"] = err
                if _state["failures"] >= LLM_CIRCUIT_THRESHOLD:
                    _now_open_ts()
                    log_event(event="breaker", action="open", failures=_state["failures"],
                              cooldown_s=LLM_CIRCUIT_COOLDOWN_S)
        # Primary down for this call -> try fallback right away (good UX).
        if _FALLBACK_KEY:
            ok, content = try_fallback()
            if ok:
                log_event(event="llm_call", provider="gemini", model=LLM_FALLBACK_MODEL,
                          ok=True, fallback_after=err,
                          latency_ms=round((time.time() - t0) * 1000, 1))
                return content
            log_event(event="llm_call", provider="gemini", ok=False, err=content,
                      primary_err=err, latency_ms=round((time.time() - t0) * 1000, 1))
            return ""
        log_event(event="llm_call", provider="deepseek", ok=False, err=err,
                  latency_ms=round((time.time() - t0) * 1000, 1))
        return ""

    # Breaker OPEN (in cooldown) -> fallback only.
    if _FALLBACK_KEY:
        ok, content = try_fallback()
        if ok:
            log_event(event="llm_call", provider="gemini", model=LLM_FALLBACK_MODEL,
                      ok=True, breaker_route=True,
                      latency_ms=round((time.time() - t0) * 1000, 1))
            return content
        log_event(event="llm_call", provider="gemini", ok=False, err=content,
                  breaker_route=True, latency_ms=round((time.time() - t0) * 1000, 1))
        return ""
    return ""
