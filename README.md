# axioma-cost-tracker

Automated cost tracking and reporting for Axioma (OpenClaw AI agent).
Runs as scheduled cron jobs — weekly summary every Monday, monthly deep-dive on the first Monday of each month.

## Reports

### Weekly (every Monday, 09:00 Oslo)
- Anthropic token spend with week-over-week delta
- Running month-to-date total
- Firecrawl credit balance
- Tavily usage
- Delivered via Telegram

### Monthly (first Monday of each month, 09:00 Oslo)
- Full month total + month-over-month comparison
- Week-by-week breakdown
- Token breakdown (input/output/cache)
- Peak week
- All-time cumulative spend

## Data

Weekly snapshots are stored locally at `~/.openclaw/workspace/data/cost_ledger.jsonl`.
**Not committed to this repo** — personal financial data, kept local.

## Scripts

| File | Purpose |
|---|---|
| `scripts/cost_ledger.py` | Shared module: read/write JSONL ledger |
| `scripts/weekly_cost_report.py` | Weekly report + ledger append |
| `scripts/monthly_cost_report.py` | Monthly trend analysis from ledger |

## Setup

Scripts are invoked by OpenClaw cron jobs — see `cron/jobs.json` in the OpenClaw config directory.

To run manually:
```bash
python3 scripts/weekly_cost_report.py
python3 scripts/monthly_cost_report.py
```
