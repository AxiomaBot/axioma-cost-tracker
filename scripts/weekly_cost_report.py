"""
Weekly Cost Report
Aggregates spend across Anthropic (Claude), Firecrawl, and Tavily.
Appends results to the local cost ledger for historical tracking.
Sends contextualised summary (week-over-week delta, running monthly total).
"""

import json
import os
import glob
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cost_ledger import append_week, last_n_weeks, week_key

OPENCLAW_DIR = os.path.expanduser("~/.openclaw")
CONFIG_PATH  = os.path.join(OPENCLAW_DIR, "openclaw.json")
SESSIONS_DIR = os.path.join(OPENCLAW_DIR, "agents/main/sessions")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def get_key(config, *path, fallback_env=None):
    try:
        d = config
        for k in path:
            d = d[k]
        return d
    except (KeyError, TypeError):
        return os.environ.get(fallback_env, "") if fallback_env else ""


# ── Anthropic ─────────────────────────────────────────────────────────────────

def anthropic_cost_this_week():
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    total_cost = input_tok = output_tok = cache_read = cache_write = 0

    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.jsonl")):
        try:
            with open(path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                        usage = entry.get("message", {}).get("usage", {})
                        cost  = usage.get("cost", {})
                        total_cost  += cost.get("total", 0)
                        input_tok   += usage.get("input", 0)
                        output_tok  += usage.get("output", 0)
                        cache_read  += usage.get("cacheRead", 0)
                        cache_write += usage.get("cacheWrite", 0)
                    except Exception:
                        continue
        except Exception:
            continue

    return {
        "cost": round(total_cost, 6),
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


# ── Firecrawl ─────────────────────────────────────────────────────────────────

def firecrawl_usage(api_key):
    if not api_key:
        return {"ok": False, "inactive": True}
    url = "https://api.firecrawl.dev/v2/team/credit-usage"
    req = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            data = d.get("data", {})
            return {
                "ok": True,
                "remaining": data.get("remainingCredits"),
                "plan_credits": data.get("planCredits"),
                "period_start": data.get("billingPeriodStart"),
                "period_end": data.get("billingPeriodEnd"),
            }
    except URLError as e:
        return {"ok": False, "error": str(e)}


# ── Tavily ────────────────────────────────────────────────────────────────────

def tavily_usage(api_key):
    if not api_key:
        return {"ok": False, "inactive": True}
    url = "https://api.tavily.com/usage"
    req = Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            acct_data = d.get("account", {})
            return {
                "ok": True,
                "plan": acct_data.get("current_plan", "Unknown"),
                "plan_limit": acct_data.get("plan_limit"),
                "plan_used": acct_data.get("plan_usage", 0),
                "search": acct_data.get("search_usage", 0),
                "extract": acct_data.get("extract_usage", 0),
                "crawl": acct_data.get("crawl_usage", 0),
                "research": acct_data.get("research_usage", 0),
            }
    except URLError as e:
        return {"ok": False, "error": str(e)}


# ── Context helpers ───────────────────────────────────────────────────────────

def fmt_tokens(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}k"
    return str(n)

def week_label():
    today = datetime.now(timezone.utc)
    start = today - timedelta(days=7)
    return f"{start.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"

def delta_str(current, previous):
    if previous == 0:
        return "first week on record"
    pct = ((current - previous) / previous) * 100
    arrow = "↑" if pct >= 0 else "↓"
    return f"{arrow} {abs(pct):.0f}% vs last week"

def running_monthly_total(history: list[dict]) -> float:
    """Sum of costs for entries in the current calendar month."""
    now = datetime.now(timezone.utc)
    total = 0.0
    for e in history:
        recorded = e.get("recorded_at", "")
        try:
            dt = datetime.fromisoformat(recorded)
            if dt.year == now.year and dt.month == now.month:
                total += e.get("anthropic", {}).get("cost", 0)
        except Exception:
            pass
    return round(total, 6)


# ── Report builder ────────────────────────────────────────────────────────────

def build_report(anthropic, firecrawl, tavily, history):
    prev_cost = history[-1].get("anthropic", {}).get("cost", 0) if history else 0
    monthly   = running_monthly_total(history)

    lines = [
        "📊 *Weekly Cost Report*",
        f"_{week_label()}_",
        "",
        "🤖 *Anthropic (Claude)*",
        f"  In: {fmt_tokens(anthropic['input_tokens'])}  |  Out: {fmt_tokens(anthropic['output_tokens'])}",
        f"  Cache read: {fmt_tokens(anthropic['cache_read_tokens'])}  |  Write: {fmt_tokens(anthropic['cache_write_tokens'])}",
        f"  This week: *${anthropic['cost']:.4f}*  ({delta_str(anthropic['cost'], prev_cost)})",
        f"  Month to date: *${monthly:.4f}*",
        "",
    ]

    lines.append("🔥 *Firecrawl*")
    if firecrawl.get("inactive"):
        lines.append("  Not yet active")
    elif firecrawl["ok"]:
        period = ""
        if firecrawl.get("period_start") and firecrawl.get("period_end"):
            period = f" ({firecrawl['period_start'][:10]} → {firecrawl['period_end'][:10]})"
        lines.append(f"  Credits remaining: *{firecrawl['remaining']}* / {firecrawl['plan_credits'] or 'pay-as-you-go'}{period}")
    else:
        lines.append(f"  ⚠️ {firecrawl.get('error', 'unknown error')}")
    lines.append("")

    lines.append("🌿 *Tavily*")
    if tavily.get("inactive"):
        lines.append("  Not yet active")
    elif tavily["ok"]:
        used  = tavily["plan_used"]
        limit = tavily["plan_limit"] or "∞"
        breakdown = [f"{k}={tavily[k]}" for k in ("search", "extract", "crawl", "research") if tavily.get(k)]
        lines.append(f"  Plan: {tavily['plan']} | Used: *{used} / {limit}*")
        if breakdown:
            lines.append(f"  Breakdown: {', '.join(breakdown)}")
    else:
        lines.append(f"  ⚠️ {tavily.get('error', 'unknown error')}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config    = load_config()
    fc_key    = get_key(config, "skills", "entries", "firecrawl", "env", "FIRECRAWL_API_KEY", fallback_env="FIRECRAWL_API_KEY")
    tv_key    = get_key(config, "skills", "entries", "tavily",    "env", "TAVILY_API_KEY",    fallback_env="TAVILY_API_KEY")

    anthropic = anthropic_cost_this_week()
    firecrawl = firecrawl_usage(fc_key)
    tavily    = tavily_usage(tv_key)

    # Load history before appending (for context in report)
    history = last_n_weeks(8)

    # Persist this week
    append_week({
        "week_key":  week_key(),
        "anthropic": anthropic,
        "firecrawl": firecrawl if firecrawl.get("ok") else None,
        "tavily":    tavily    if tavily.get("ok")    else None,
    })

    print(build_report(anthropic, firecrawl, tavily, history))
