"""Structured event logger for session history.

Captures key events as structured JSON for dashboard display and post-analysis.
Events: session_start, session_end, game_start, game_end, signal, trade_open,
trade_close, error, auth_status, market_scan.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def log_event(event_type, data=None):
    """Log a structured event to the session event log."""
    now = datetime.now(EST)
    event = {
        "ts": time.time(),
        "time": now.strftime("%I:%M:%S %p"),
        "type": event_type,
        "data": data or {},
    }

    path = os.path.join(DATA_DIR, "events")
    _ensure_dir(path)
    date_str = now.strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")

    with open(filepath, "a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def get_recent_events(limit=50):
    """Get the most recent events from today's log."""
    now = datetime.now(EST)
    date_str = now.strftime("%Y-%m-%d")
    filepath = os.path.join(DATA_DIR, "events", f"{date_str}.jsonl")

    if not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
        events = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
        return events
    except Exception:
        return []
