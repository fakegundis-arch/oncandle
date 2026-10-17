#!/usr/bin/env python3
"""Trade list for one news-open v2 setting, with or without the 2-market rule.

    python scripts/news_open_v2_trades.py --pick best        # one market is enough
    python scripts/news_open_v2_trades.py --pick confluence2 # needs 2+ markets
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, news_open as NO  # noqa: E402
from fetch_ny_open_ticks import trading_days  # noqa: E402
from run_news_open_v2 import MARKETS, RISK, RR, market_data, trade_r  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", default="best", choices=("best", "confluence2"))
    ap.add_argument("--be", type=float, default=1.0)
    a = ap.parse_args()
    days = list(trading_days(date(2024, 11, 1), date(2026, 10, 15)))
    cal = pd.read_csv(ROOT / "data" / "calendar" / "ff_calendar.csv", parse_dates=["time_utc"])
    scores = NO.day_scores(cal, days)
    p = NO.Params(min_score=2, observe_min=60, min_move=0.0, entry="pullback", stop="units", stop_units=1.0, rr=RR)
    rows = []
    for m in MARKETS:
        m1, unit, _, (o, h, l, c) = market_data(m, days)
        cd = NO.candidates(m1, m, scores, unit, p)
        cost = 2 * D.EXNESS_STANDARD_SPREAD[m]
        xo = np.zeros(len(o), np.bool_)
        for r in cd.itertuples():
            e, d, sl = int(r.entry_i), int(r.dir), float(r.sl)
            R = trade_r(o, h, l, c, xo, e, d, sl, RR, a.be, cost, 24 * 60)
            entry = o[e] + cost if d == 1 else o[e]
            rows.append({"day": r.day, "market": m, "strength": r.strength, "score": r.score, "news": r.events,
                         "dir": "BUY" if d == 1 else "SELL", "entry_utc": m1.index[e], "entry": entry,
                         "sl": entry - d * sl, "tp": entry + d * RR * sl, "r": R})
    t = pd.DataFrame(rows)
    t["markets_confirming"] = t.groupby("day").market.transform("size")
    if a.pick == "confluence2":
        t = t[t.markets_confirming >= 2]
    t = t.sort_values("strength", ascending=False).groupby("day").head(1).sort_values("day")
    out = ROOT / "results" / "news_open" / f"final_v2_{a.pick}_be{a.be:g}_trades.csv"
    t.to_csv(out, index=False)
    for y in (2025, 2026):
        x = t[t.day.dt.year == y]
        r = x.r.to_numpy()
        eq = 1000 * np.cumprod(np.maximum(1 + RISK * r, 0))
        loss = -r[r < 0].sum()
        print(f"{y}: {len(r)} trades, win {(r > 0).mean():.0%} (TP {(r > 2.5).mean():.0%}), "
              f"PF {r[r > 0].sum() / loss:.2f}, $1000 -> ${eq[-1]:,.0f} (peak ${eq.max():,.0f}, low ${eq.min():,.0f}), "
              f"DD {(eq / np.maximum.accumulate(eq) - 1).min():.0%}")
        s = x[x.markets_confirming == 1]
        print(f"   single-market days: {len(s)}, total {s.r.sum():+.1f}R")
    print(out)


if __name__ == "__main__":
    main()
