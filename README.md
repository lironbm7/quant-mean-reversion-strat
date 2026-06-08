# Quantitative Mean Reversion Strategy

Statistical mean reversion scanner that identifies high-probability entry points by measuring price proximity to historically significant support levels. Alerts via Slack.

<img width="606" alt="image" src="https://github.com/user-attachments/assets/37c09d17-2870-4fd8-8978-3cd7e533daeb" />

## How It Works

### Monitor

Scheduled scanner (GitHub Actions cron) that computes moving averages across multiple timeframes and fires Slack alerts when price enters a statistically validated proximity zone.

### Discovery

Backtests 3+ years of historical data to determine which indicators a stock actually respects. Example output:
```
CRM (Confidence: 94.6%)
   Recommended threshold: 8.0%
   Best indicator: EMA50 (1w) | Success rate: 92.9% | Avg bounce: 16.1%

   1. EMA50 (1w): 92.9% success, 16.1% avg bounce, 14 tests
   2. EMA200 (1w): 93.3% success, 14.3% avg bounce, 15 tests
   3. SMA50 (1w): 81.8% success, 17.2% avg bounce, 11 tests
```

## Configuration

All configuration lives in **GitHub Secrets** (Settings > Secrets and variables > Actions) so the repo stays public without exposing strategies.

| Secret | Example |
|---|---|
| `SLACK_BOT_TOKEN` | `xoxb-...` |
| `SLACK_CHANNEL` | `#trading-alerts` |
| `SYMBOLS_CONFIG` | Full JSON config (symbols, indicators, thresholds) |
| `THRESHOLD_PERCENTAGE` | `10.0` |
| `COOLDOWN_HOURS` | `24` |

### Indicators (any EMA/SMA period)

Each indicator is a string: `EMA<n>`, `SMA<n>` (any period 1–9999), or `VWAP`.
You are **not** limited to 50/100/200 — a stock that actually respects its
`EMA40` or `4h/EMA120` is configured directly:

```json
{
  "settings": { "threshold_percentage": 4.0, "cooldown_hours": 24 },
  "symbols": [
    { "symbol": "AAOI", "indicators": [
        { "bar": "1d", "indicator": "EMA45" },
        { "bar": "4h", "indicator": "EMA160" }
    ]},
    { "symbol": "TSM", "indicators": [
        { "bar": "1d", "indicator": "EMA80" },
        { "bar": "4h", "indicator": "EMA120" }
    ]}
  ]
}
```

An alert fires when price comes within `threshold_percentage` of a configured
line. `bar` is any of `1m,5m,15m,30m,1h,4h,1d,1w,1mo` (`4h` is resampled from
1h). `config/symbols.json` is gitignored — for CI, paste the same JSON into the
`SYMBOLS_CONFIG` secret.

**Generating it from the trend-following research:** `python scripts/gen_symbols.py`
pulls each ticker's reliable EMA bands from the sibling `trend-following` repo's
output and **dedups overlapping lines by price level** — two lines within 1.5%
of each other (e.g. `4h/EMA100` and `1d/EMA20`, which carry near-identical
lookback memory) collapse to one, keeping the higher timeframe.

### Creating the `SLACK_BOT_TOKEN`

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**. Name it (e.g. "Trading Bot") and pick your workspace.
2. Open **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** and add:
   - `chat:write` — post messages
   - `chat:write.customize` — required because alerts override `username` and `icon_emoji`
   - `chat:write.public` *(optional)* — post to public channels without being invited
3. Scroll up → **Install to Workspace** → approve. Copy the **Bot User OAuth Token** (starts with `xoxb-`) — this is `SLACK_BOT_TOKEN`.
4. In Slack, invite the bot to the alert channel: `/invite @your-bot-name` in `#trading-alerts` (skip if you added `chat:write.public` and the channel is public).
5. Add it under **Settings → Secrets and variables → Actions → New repository secret** along with `SLACK_CHANNEL`.
