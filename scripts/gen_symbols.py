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
from typing import Optional

import pandas as pd
import yfinance as yf

# Defaults to the sibling trend-following repo's output; override with the
# TREND_OUTPUT env var.
TREND_OUTPUT = Path(
    os.environ.get(
        "TREND_OUTPUT",
        Path(__file__).resolve().parents[2] / "trend-following" / "output",
    )
)
OUT = Path(__file__).resolve().parents[1] / "config" / "symbols.json"

# Core AI / semiconductor-complex names: get RELIABLE short/mid bounce bands
# (n>=3, >=80% success) PLUS a long-term structural anchor.
CORE_AI = [
    "AXTI", "AEHR", "RGTI", "NOK", "ARM", "NBIS", "AAOI", "MU", "ALAB", "MRVL",
    "BE", "INTC", "SNDK", "WDC", "QCOM", "COHR", "TSEM", "LITE", "STX", "CAMT",
    "CRWV", "ANET", "VRT", "DELL", "ASML", "CRDO", "JBL", "GEV", "NVDA", "AVGO",
]

# Everything else (megacaps, indices, crypto, software/cybersecurity): only the
# long-term structural support is alerted on — no short/mid bounce noise.
NON_AI = [
    "DDOG", "CRWD", "PANW", "ORCL", "PLTR", "TSLA", "COIN", "META", "GOOGL",
    "MSFT", "NFLX", "AMZN", "GLD", "SPY", "QQQ", "AAPL", "BTC-USD", "ETH-USD",
]

ALL_TICKERS = CORE_AI + NON_AI
_CORE_AI_SET = set(CORE_AI)

MIN_RESOLVED = 3
MIN_SUCCESS = 0.80
DEDUP_PCT = 0.015          # lines within 1.5% of each other = same support
KEEP_MID = 2               # short/mid bounce levels kept per symbol
TF_RANK = {"1d": 3, "4h": 2, "1h": 1}

THRESHOLD_PCT = 4.0        # alert when price is within this % of a line
COOLDOWN_HOURS = 24


def reliable(info: dict) -> list[dict]:
    """Only statistically-reliable bounce bands (n>=3, >=80% success).

    No fallback: a wonky/thin short-term band is NOT added. A name with no
    reliable short band gets only its long-term anchor.
    """
    return [c for c in info.get("all_qualified", [])
            if c["n_resolved"] >= MIN_RESOLVED and c["success_rate"] >= MIN_SUCCESS
            and c.get("ema_value_now")]


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


def _daily_closes(ticker: str) -> Optional[pd.Series]:
    """Full daily close history (auto_adjust=False), or None on failure."""
    try:
        df = yf.download(ticker, period="max", interval="1d",
                         auto_adjust=False, progress=False, threads=False)
        if df.empty:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna()
    except Exception:
        return None


def long_term_anchor(ticker: str) -> Optional[tuple[str, str, float]]:
    """The deep structural support: 1w/SMA200 (the '200-week' floor) when >=200
    weeks of history exist, else 1d/EMA200 when >=200 daily bars, else None."""
    close = _daily_closes(ticker)
    if close is None:
        return None
    weekly = close.resample("1W").last().dropna()
    if len(weekly) >= 200:
        return ("1w", "SMA200", float(weekly.rolling(200).mean().iloc[-1]))
    if len(close) >= 200:
        return ("1d", "EMA200", float(close.ewm(span=200, adjust=False).mean().iloc[-1]))
    return None


def build_entry(ticker: str) -> tuple[Optional[dict], str]:
    """Build a symbol's alert levels.

    - Core AI/semi names: up to KEEP_MID *reliable* short/mid bounce bands
      (4h/1d) plus the long-term anchor.
    - Non-AI names: the long-term anchor ONLY (no short/mid bounce noise).
    All deduped by price level.
    """
    is_ai = ticker in _CORE_AI_SET
    f = TREND_OUTPUT / f"{ticker}.json"
    info = json.loads(f.read_text()) if f.exists() else {"all_qualified": []}

    chosen: list[tuple[str, str, float]] = []
    if is_ai:
        for c in dedup(reliable(info))[:KEEP_MID]:
            chosen.append((c["timeframe"], f"EMA{c['ema']}", c["ema_value_now"]))

    anchor = long_term_anchor(ticker)
    if anchor and not any(abs(anchor[2] - kl) / kl <= DEDUP_PCT for _, _, kl in chosen):
        chosen.append(anchor)

    if not chosen:
        return None, f"{ticker}: no reliable level (no respected support / too new), skipped"

    indicators = [{"bar": b, "indicator": i} for b, i, _ in chosen]
    kind = "AI" if is_ai else "non-AI(LT-only)"
    tag = ", ".join(f"{b}/{i}@{v:.2f}" for b, i, v in chosen)
    return {"symbol": ticker, "indicators": indicators}, f"{ticker} [{kind}]: {tag}"


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Generate/extend config/symbols.json from trend-following output.")
    ap.add_argument("--tickers", nargs="*", help="explicit ticker list (default: built-in WATCHLIST)")
    ap.add_argument("--merge", action="store_true",
                    help="preserve existing symbols.json entries; only add/replace the given tickers")
    args = ap.parse_args()

    tickers = args.tickers if args.tickers else ALL_TICKERS

    new_entries: dict[str, dict] = {}
    notes = []
    for t in tickers:
        entry, note = build_entry(t)
        notes.append(note)
        if entry:
            new_entries[t] = entry

    if args.merge and OUT.exists():
        existing = json.loads(OUT.read_text())
        settings = existing.get("settings", {})
        # keep existing symbols in order, overwrite any re-processed ones, then append new
        by_sym = {s["symbol"]: s for s in existing.get("symbols", [])}
        for sym, entry in new_entries.items():
            by_sym[sym] = entry
        symbols = list(by_sym.values())
    else:
        settings = {
            "threshold_percentage": THRESHOLD_PCT,
            "cooldown_hours": COOLDOWN_HOURS,
            "slack_channel": "#trading-alerts",
        }
        symbols = list(new_entries.values())

    config = {"settings": settings, "symbols": symbols}
    OUT.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Wrote {OUT} — {len(symbols)} symbols total, "
          f"{sum(len(s['indicators']) for s in symbols)} indicators "
          f"({'merge' if args.merge else 'full'} mode, processed {len(tickers)})")
    print("\n".join(notes))


if __name__ == "__main__":
    main()
