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

### Creating the `SLACK_BOT_TOKEN`

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**. Name it (e.g. "Trading Bot") and pick your workspace.
2. Open **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** and add:
   - `chat:write` — post messages
   - `chat:write.customize` — required because alerts override `username` and `icon_emoji`
   - `chat:write.public` *(optional)* — post to public channels without being invited
3. Scroll up → **Install to Workspace** → approve. Copy the **Bot User OAuth Token** (starts with `xoxb-`) — this is `SLACK_BOT_TOKEN`.
4. In Slack, invite the bot to the alert channel: `/invite @your-bot-name` in `#trading-alerts` (skip if you added `chat:write.public` and the channel is public).
5. Add it under **Settings → Secrets and variables → Actions → New repository secret** along with `SLACK_CHANNEL`.
