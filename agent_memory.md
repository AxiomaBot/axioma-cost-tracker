# agent_memory.md
# Machine-readable codebase context. Not for humans.

## Purpose
Cost tracking and reporting for an OpenClaw AI agent (Axioma). Two scheduled reports delivered via Telegram: weekly summary + monthly deep-dive. Data persisted locally in JSONL ledger — not in repo.

## File Map
```
scripts/cost_ledger.py          Shared module. JSONL read/write. Functions: load_ledger(), append_week(), last_n_weeks(), current_month_entries(), week_key().
scripts/weekly_cost_report.py   Runs Monday 09:00 Oslo. Fetches Anthropic cost from session logs, Firecrawl/Tavily via API. Appends to ledger. Prints contextualised report (week-over-week delta, month-to-date).
scripts/monthly_cost_report.py  Runs first Monday of month 09:00 Oslo. Reads full ledger. Builds trend analysis for last full month vs prior month.
```

## Ledger Schema
File: `~/.openclaw/workspace/data/cost_ledger.jsonl`
One JSON object per line, one per week. Fields:
```json
{
  "week_key": "2026-W08",
  "recorded_at": "2026-02-24T09:00:00+00:00",
  "anthropic": {
    "cost": 0.4231,
    "input_tokens": 12400,
    "output_tokens": 3100,
    "cache_read_tokens": 85000,
    "cache_write_tokens": 4200
  },
  "firecrawl": { "ok": true, "remaining": 490, "plan_credits": 500, ... } | null,
  "tavily":    { "ok": true, "plan": "Free", "plan_used": 12, ... }      | null
}
```
`firecrawl` and `tavily` are null when keys are not configured or APIs are not yet active.

## Anthropic Cost Source
Session logs at `~/.openclaw/agents/main/sessions/*.jsonl`.
Each line is a JSON event. Cost is at: `entry.message.usage.cost.total`.
Weekly script filters by `entry.timestamp` (ISO8601) to last 7 days.

## Cron Jobs
Weekly: `0 9 * * 1` Europe/Oslo — runs `weekly_cost_report.py`, delivers stdout to Telegram.
Monthly: `0 9 1-7 * 1` Europe/Oslo (first Monday of month) — runs `monthly_cost_report.py`, delivers stdout to Telegram.
Both defined in `~/.openclaw/cron/jobs.json`.

## Known Gaps / TODO
1. No per-project/session cost breakdown — weekly script sums all sessions, doesn't attribute by topic or project.
2. Monthly report targets "last full month" by checking `recorded_at` date — may miss weeks recorded slightly late.
3. Cache efficiency ratio (cache_read / total_input) not yet surfaced in reports — useful signal.
4. No alerting threshold — no notification if weekly cost spikes unexpectedly.
5. Firecrawl/Tavily inactive for now — null handling in place, will auto-activate once keys are present in OpenClaw config.

## Repo
https://github.com/AxiomaBot/axioma-cost-tracker
Branch: main
