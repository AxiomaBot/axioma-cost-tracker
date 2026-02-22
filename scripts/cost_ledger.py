"""
cost_ledger.py — Shared ledger read/write module.
Stores weekly cost snapshots as JSONL. One entry per week.
Also provides Telegram delivery so cron scripts can post directly
without routing through an LLM agent (zero model cost).
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlencode

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


# ── Telegram delivery ─────────────────────────────────────────────────────────

OPENCLAW_CONFIG = Path(os.path.expanduser("~/.openclaw/openclaw.json"))


def _get_telegram_config() -> tuple[str, str] | tuple[None, None]:
    """Return (bot_token, chat_id) from OpenClaw config, or (None, None)."""
    try:
        with open(OPENCLAW_CONFIG) as f:
            cfg = json.load(f)
        accounts = cfg.get("channels", {}).get("telegram", {}).get("accounts", {})
        token = next(iter(accounts.values()), {}).get("botToken")
        # Derive chat_id from the first Telegram channel entry
        channels_cfg = cfg.get("channels", {}).get("telegram", {})
        chat_id = channels_cfg.get("defaultChatId") or None
        # Fallback: check agents for delivery targets
        if not chat_id:
            jobs_path = Path(os.path.expanduser("~/.openclaw/cron/jobs.json"))
            if jobs_path.exists():
                with open(jobs_path) as f:
                    jobs = json.load(f)
                for job in jobs.get("jobs", []):
                    to = job.get("delivery", {}).get("to")
                    if to:
                        chat_id = str(to)
                        break
        return token, chat_id
    except Exception:
        return None, None


def send_telegram(text: str, chat_id: str = None, parse_mode: str = "Markdown") -> bool:
    """
    Send a message directly via Telegram Bot API.
    Returns True on success. Falls back to stdout if config not available.
    """
    token, default_chat = _get_telegram_config()
    target = chat_id or default_chat

    if not token or not target:
        print("[telegram] No bot token or chat_id found — printing to stdout instead:")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": target,
        "text": text,
        "parse_mode": parse_mode,
    }).encode()

    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"[telegram] Send failed: {e}")
        print(text)
        return False
