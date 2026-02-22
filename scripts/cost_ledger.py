"""
cost_ledger.py — Shared ledger read/write module.
Stores weekly cost snapshots as JSONL. One entry per week.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

LEDGER_PATH = Path(os.path.expanduser("~/.openclaw/workspace/data/cost_ledger.jsonl"))


def ensure_ledger():
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        LEDGER_PATH.touch()


def week_key(dt: datetime = None) -> str:
    """ISO week string: e.g. '2026-W08'"""
    d = (dt or datetime.now(timezone.utc))
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def load_ledger() -> list[dict]:
    ensure_ledger()
    entries = []
    with open(LEDGER_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def append_week(entry: dict):
    """
    Append or update a week entry in the ledger.
    If an entry for the same week_key already exists, it is overwritten (idempotent re-runs).
    """
    ensure_ledger()
    key = entry.get("week_key") or week_key()
    entry["week_key"] = key
    entry.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())

    existing = load_ledger()
    updated = [e for e in existing if e.get("week_key") != key]
    updated.append(entry)

    with open(LEDGER_PATH, "w") as f:
        for e in updated:
            f.write(json.dumps(e) + "\n")


def get_week(key: str) -> dict | None:
    for e in load_ledger():
        if e.get("week_key") == key:
            return e
    return None


def last_n_weeks(n: int) -> list[dict]:
    """Return the last n entries, sorted oldest-first."""
    entries = load_ledger()
    entries.sort(key=lambda e: e.get("week_key", ""))
    return entries[-n:]


def current_month_entries() -> list[dict]:
    """All entries whose week_key falls in the current calendar month."""
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y")
    # Weeks that overlap with this month — approximate by checking recorded_at date
    result = []
    for e in load_ledger():
        recorded = e.get("recorded_at", "")
        try:
            dt = datetime.fromisoformat(recorded)
            if dt.year == now.year and dt.month == now.month:
                result.append(e)
        except Exception:
            pass
    result.sort(key=lambda e: e.get("week_key", ""))
    return result
