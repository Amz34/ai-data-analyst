"""Lightweight JSONL event tracer (ops observability).

Writes one JSON object per line to <LOG_DIR>/trace-YYYYMMDD.jsonl.
Thread-safe, best-effort: never raises, never blocks the request path.
"""
import json
import threading
from datetime import datetime, timezone

from ..config import LOG_DIR

_lock = threading.Lock()


def _target():
    return LOG_DIR / ("trace-%s.jsonl" % datetime.now(timezone.utc).strftime("%Y%m%d"))


def log_event(**fields):
    """Append a trace event. Usage: log_event(event="llm_call", provider=..., ok=True, ...)"""
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": fields.pop("event", "log"),
        }
        rec.update(fields)
        line = (json.dumps(rec, default=str) + "\n").encode("utf-8")
        with _lock:
            with open(_target(), "ab") as f:
                f.write(line)
    except Exception:
        pass
