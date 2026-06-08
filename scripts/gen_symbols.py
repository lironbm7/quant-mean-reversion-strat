"""Generate config/symbols.json from the trend-following research output.

For each watchlist ticker, pull the reliable EMA bands the trend-following
pipeline found (the dense scan grid resolves the *actual* respected period,
e.g. EMA40 / EMA120 — not just 50/100/200), then:

  1. keep bands with real evidence (>= MIN_RESOLVED bounces, >= MIN_SUCCESS),
  2. DEDUP by the current EMA *price level* — two lines within DEDUP_PCT of
     each other are the same support, so 4h/EMA100 and 1d/EMA20 (which carry
     near-identical lookback memory) collapse to one; keep the higher
     timeframe, then higher score,
  3. emit the top KEEP_PER_SYMBOL as alert indicators.

No data is refetched — every level comes from each ticker's all_qualified
entry (ema_value_now) in the trend-following output JSON.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Defaults to the sibling trend-following repo's output; override with the
# TREND_OUTPUT env var.
TREND_OUTPUT = Path(
    os.environ.get(
        "TREND_OUTPUT",
        Path(__file__).resolve().parents[2] / "trend-following" / "output",
    )
)
OUT = Path(__file__).resolve().parents[1] / "config" / "symbols.json"

WATCHLIST = [
    "TE", "AXTI", "AEHR", "RGTI", "NOK", "ARM", "NBIS", "AAOI", "MU", "ALAB",
    "MRVL", "BE", "INTC", "SNDK", "WDC", "QCOM", "COHR", "APLD", "TSEM",
    "LITE", "STX", "CAMT", "CDNS", "CRWV", "ANET", "VRT", "DELL", "TSM",
    "ASML", "CRDO", "JBL", "GEV",
]

MIN_RESOLVED = 3
MIN_SUCCESS = 0.80
DEDUP_PCT = 0.015          # lines within 1.5% of each other = same support
KEEP_PER_SYMBOL = 3
TF_RANK = {"1d": 3, "4h": 2, "1h": 1}

THRESHOLD_PCT = 4.0        # alert when price is within this % of a line
COOLDOWN_HOURS = 24


def reliable(info: dict) -> list[dict]:
    out = [c for c in info.get("all_qualified", [])
           if c["n_resolved"] >= MIN_RESOLVED and c["success_rate"] >= MIN_SUCCESS
           and c.get("ema_value_now")]
    if out:
        return out
    # fallback: no high-evidence band — take the best-scoring qualified lines
    # so every watchlist symbol still gets an alert level.
    return sorted((c for c in info.get("all_qualified", []) if c.get("ema_value_now")),
                  key=lambda c: -c["score"])[:2]


def dedup(cands: list[dict]) -> list[dict]:
    # best first: higher timeframe, then higher score
    cands = sorted(cands, key=lambda c: (TF_RANK.get(c["timeframe"], 0), c["score"]),
                   reverse=True)
    kept: list[dict] = []
    for c in cands:
        lvl = c["ema_value_now"]
        if any(abs(lvl - k["ema_value_now"]) / k["ema_value_now"] <= DEDUP_PCT for k in kept):
            continue
        kept.append(c)
    return kept


def main() -> None:
    symbols = []
    notes = []
    for t in WATCHLIST:
        f = TREND_OUTPUT / f"{t}.json"
        if not f.exists():
            notes.append(f"{t}: no trend-following output, skipped")
            continue
        info = json.loads(f.read_text())
        kept = dedup(reliable(info))[:KEEP_PER_SYMBOL]
        if not kept:
            notes.append(f"{t}: no qualified EMA band, skipped")
            continue
        indicators = [{"bar": c["timeframe"], "indicator": f"EMA{c['ema']}"} for c in kept]
        symbols.append({"symbol": t, "indicators": indicators})
        tag = ", ".join(f"{c['timeframe']}/EMA{c['ema']}@{c['ema_value_now']:.2f}" for c in kept)
        notes.append(f"{t}: {tag}")

    config = {
        "settings": {
            "threshold_percentage": THRESHOLD_PCT,
            "cooldown_hours": COOLDOWN_HOURS,
            "slack_channel": "#trading-alerts",
        },
        "symbols": symbols,
    }
    OUT.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Wrote {OUT} — {len(symbols)} symbols, "
          f"{sum(len(s['indicators']) for s in symbols)} indicators")
    print("\n".join(notes))


if __name__ == "__main__":
    main()
