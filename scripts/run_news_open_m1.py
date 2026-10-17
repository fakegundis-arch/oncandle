#!/usr/bin/env python3
"""News bias -> NY open, all on the 1-minute chart: observe the first 1-15 M1 candles, M1 entries,
stops from M1 ATR, 1:3 target, 2+ markets must agree.

    python scripts/run_news_open_m1.py
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, indicators as ind, news_open as NO  # noqa: E402
from fetch_ny_open_ticks import trading_days  # noqa: E402
from run_news_open_v2 import MARKETS, RISK, RR, trade_r  # noqa: E402

STOPS = {"1atr": dict(stop="atr", stop_atr=1.0), "2atr": dict(stop="atr", stop_atr=2.0),
         "3atr": dict(stop="atr", stop_atr=3.0), "swing": dict(stop="swing")}
ENTRY_GRID = dict(min_score=(1, 2, 3), observe_min=(1, 3, 5, 10, 15),
                  entry=("momentum", "pullback", "breakout", "candle"), stop=tuple(STOPS),
                  mode=("news", "ignore_news", "against_news"))
EXIT_GRID = dict(be=(0.0, 1.0), hold=("16:00", "120m", "24h"))
HOLD_BARS = {"16:00": 0, "120m": 120, "24h": 24 * 60}

_CACHE = {}


def market_data(m):
    if m not in _CACHE:
        m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
        _CACHE[m] = (m1, ind.atr(m1, 14).to_numpy(), ind.ema(m1.close, 9).to_numpy(), NO.session_end_flags(m1),
                     tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close")))
    return _CACHE[m]


def trades_for(p, scores, be, hold):
    rows = []
    for m in MARKETS:
        m1, atr, ema, xout, (o, h, l, c) = market_data(m)
        cd = NO.candidates_m1(m1, m, scores, p, atr, ema)
        xo = xout if hold == "16:00" else np.zeros(len(o), np.bool_)
        cost = 2 * D.EXNESS_STANDARD_SPREAD[m]
        for r in cd.itertuples():
            R = trade_r(o, h, l, c, xo, int(r.entry_i), int(r.dir), float(r.sl), RR, be, cost, HOLD_BARS[hold])
            rows.append({"day": r.day, "market": m, "strength": r.strength, "score": r.score, "news": r.events,
                         "dir": int(r.dir), "entry_i": int(r.entry_i), "sl": float(r.sl), "cost": cost, "r": R})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    t["markets_confirming"] = t.groupby("day").market.transform("size")
    t = t[t.markets_confirming >= 2]
    return t.sort_values("strength", ascending=False).groupby("day").head(1).sort_values("day")


def stats(daily):
    out = {}
    for k, (a, b) in {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}.items():
        r = daily[(daily.index >= a) & (daily.index < b)].to_numpy()
        if len(r) == 0:
            continue
        eq = np.cumprod(np.maximum(1 + RISK * r, 0))
        loss = -r[r < 0].sum()
        out.update({f"{k}_days": len(r), f"{k}_win": (r > 0).mean(), f"{k}_avg_r": r.mean(),
                    f"{k}_pf": r[r > 0].sum() / loss if loss > 0 else np.inf,
                    f"{k}_usd": 1000 * eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
    return out


def job(args):
    ekw, scores = args
    p = NO.ParamsM1(**{k: v for k, v in ekw.items() if k != "stop"}, **STOPS[ekw["stop"]])
    rows = []
    for be, hold in itertools.product(*EXIT_GRID.values()):
        t = trades_for(p, scores, be, hold)
        if len(t):
            rows.append({**ekw, "be": be, "hold": hold, **stats(t.set_index("day").r)})
    return rows


def main():
    days = list(trading_days(date(2024, 11, 1), date(2026, 10, 15)))
    cal = pd.read_csv(ROOT / "data" / "calendar" / "ff_calendar.csv", parse_dates=["time_utc"])
    scores = NO.day_scores(cal, days)
    jobs = [(dict(zip(ENTRY_GRID, v)), scores) for v in itertools.product(*ENTRY_GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=6)):
            rows += r
            if i % 60 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    out = ROOT / "results" / "news_open" / "grid_m1.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(len(rows), "configurations ->", out)


if __name__ == "__main__":
    main()
