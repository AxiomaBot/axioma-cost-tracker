"""
Monthly Cost Report
Deep-dive analysis from the cost ledger.
Runs on the first Monday of each month at 09:00 Oslo time.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cost_ledger import load_ledger


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_tokens(n):
    if n is None: return "—"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}k"
    return str(n)

def month_label(year, month):
    return datetime(year, month, 1).strftime("%B %Y")

def entries_for_month(ledger, year, month):
    result = []
    for e in ledger:
        recorded = e.get("recorded_at", "")
        try:
            dt = datetime.fromisoformat(recorded)
            if dt.year == year and dt.month == month:
                result.append(e)
        except Exception:
            pass
    return sorted(result, key=lambda e: e.get("week_key", ""))

def month_cost(entries):
    return round(sum(e.get("anthropic", {}).get("cost", 0) for e in entries), 6)

def month_tokens(entries, key):
    return sum(e.get("anthropic", {}).get(key, 0) for e in entries)

def pct_delta(current, previous):
    if previous == 0:
        return "no prior month"
    pct = ((current - previous) / previous) * 100
    arrow = "↑" if pct >= 0 else "↓"
    return f"{arrow} {abs(pct):.0f}% vs last month"

def projected_monthly(entries):
    """Simple linear projection: (total so far / days elapsed) * 30"""
    if not entries:
        return None
    total = month_cost(entries)
    now = datetime.now(timezone.utc)
    day_of_month = now.day
    if day_of_month == 0:
        return None
    return round((total / day_of_month) * 30, 4)


# ── Report builder ────────────────────────────────────────────────────────────

def build_report(ledger):
    now  = datetime.now(timezone.utc)

    # Target: last full month (since this runs on the first Monday of current month)
    first_of_month = now.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    lm_year, lm_month = last_month_end.year, last_month_end.month

    # And the month before that for comparison
    prev_month_end = last_month_end.replace(day=1) - timedelta(days=1)
    pm_year, pm_month = prev_month_end.year, prev_month_end.month

    lm_entries = entries_for_month(ledger, lm_year, lm_month)
    pm_entries = entries_for_month(ledger, pm_year, pm_month)

    lm_cost = month_cost(lm_entries)
    pm_cost = month_cost(pm_entries)

    if not lm_entries:
        return f"📊 *Monthly Cost Report — {month_label(lm_year, lm_month)}*\n\n_No data recorded for this month yet._"

    # Weekly breakdown
    weekly_lines = []
    for e in lm_entries:
        w = e.get("week_key", "?")
        c = e.get("anthropic", {}).get("cost", 0)
        weekly_lines.append(f"  {w}: ${c:.4f}")

    # Token totals
    total_in    = month_tokens(lm_entries, "input_tokens")
    total_out   = month_tokens(lm_entries, "output_tokens")
    total_cr    = month_tokens(lm_entries, "cache_read_tokens")
    total_cw    = month_tokens(lm_entries, "cache_write_tokens")

    # Peak week
    if lm_entries:
        peak = max(lm_entries, key=lambda e: e.get("anthropic", {}).get("cost", 0))
        peak_label = f"{peak['week_key']} (${peak['anthropic']['cost']:.4f})"
    else:
        peak_label = "—"

    # Running total (all time)
    all_time = round(sum(e.get("anthropic", {}).get("cost", 0) for e in ledger), 4)

    lines = [
        f"📊 *Monthly Cost Report*",
        f"_{month_label(lm_year, lm_month)}_",
        "",
        "🤖 *Anthropic (Claude)*",
        f"  Total: *${lm_cost:.4f}*  ({pct_delta(lm_cost, pm_cost)})",
        f"  Tokens in: {fmt_tokens(total_in)}  |  Out: {fmt_tokens(total_out)}",
        f"  Cache read: {fmt_tokens(total_cr)}  |  Write: {fmt_tokens(total_cw)}",
        f"  Peak week: {peak_label}",
        "",
        "*Weekly breakdown:*",
        *weekly_lines,
        "",
        f"📈 *All-time Anthropic spend:* ${all_time:.4f}",
        f"  Weeks on record: {len(ledger)}",
    ]

    # Add Firecrawl and Tavily if any data exists
    fc_entries = [e for e in lm_entries if e.get("firecrawl")]
    tv_entries = [e for e in lm_entries if e.get("tavily")]

    if fc_entries:
        latest_fc = fc_entries[-1]["firecrawl"]
        lines += [
            "",
            "🔥 *Firecrawl*",
            f"  Credits remaining: {latest_fc.get('remaining', '—')} / {latest_fc.get('plan_credits', '—')}",
        ]

    if tv_entries:
        latest_tv = tv_entries[-1]["tavily"]
        lines += [
            "",
            "🌿 *Tavily*",
            f"  Plan: {latest_tv.get('plan', '—')} | Used: {latest_tv.get('plan_used', '—')} / {latest_tv.get('plan_limit', '∞')}",
        ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ledger = load_ledger()

    if not ledger:
        print("📊 *Monthly Cost Report*\n\n_No data in ledger yet. Weekly reports will build this up over time._")
    else:
        print(build_report(ledger))
