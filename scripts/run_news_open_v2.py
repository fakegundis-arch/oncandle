#!/usr/bin/env python3
"""News bias -> NY open, rebuilt: fixed 1:3 target, medium + high USD news,
patient breakout entry, longer holds, multi-market confluence.

    python scripts/run_news_open_v2.py
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
from backtester import data as D, news_open as NO  # noqa: E402
from backtester.engine import njit  # noqa: E402
from fetch_ny_open_ticks import trading_days  # noqa: E402

MARKETS = list(NO.USD_BULL_DIRECTION)
RISK = 0.10
RR = 3.0
STOPS = {"window": dict(stop="window"), "half_window": dict(stop="half_window"),
         "0.5u": dict(stop="units", stop_units=0.5), "1u": dict(stop="units", stop_units=1.0)}
ENTRY_GRID = dict(min_score=(1, 2, 3), observe_min=(15, 30, 60), min_move=(0.0, 0.25),
                  entry=("momentum", "pullback", "breakout"), stop=tuple(STOPS),
                  mode=("news", "ignore_news", "against_news"))
EXIT_GRID = dict(be=(0.0, 1.0), hold=("16:00", "24h"), pick=("best", "all", "confluence2"))


@njit(cache=True)
def trade_r(o, h, l, c, xout, e, d, sl, rr, be, cost, max_bars):
    entry = o[e] + cost if d == 1 else o[e]
    stop = entry - d * sl
    tgt = entry + d * rr * sl
    moved = False
    last = min(len(o), e + max_bars) if max_bars > 0 else len(o)
    for j in range(e, last):
        bo = o[j] if d == 1 else o[j] + cost
        bh = h[j] if d == 1 else h[j] + cost
        bl = l[j] if d == 1 else l[j] + cost
        if d == 1:
            if bl <= stop:
                return (min(bo, stop) - entry) / sl
            if bh >= tgt:
                return (max(bo, tgt) - entry) / sl
        else:
            if bh >= stop:
                return (entry - max(bo, stop)) / sl
            if bl <= tgt:
                return (entry - min(bo, tgt)) / sl
        if be > 0 and not moved:
            if (d == 1 and bh >= entry + be * sl) or (d == -1 and bl <= entry - be * sl):
                stop = entry + d * 0.1 * sl
                moved = True
        if xout[j] and j > e:
            px = o[j] if d == 1 else o[j] + cost
            return d * (px - entry) / sl
    j = last - 1
    px = c[j] if d == 1 else c[j] + cost
    return d * (px - entry) / sl


_CACHE = {}


def market_data(m, days):
    if m not in _CACHE:
        m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
        _CACHE[m] = (m1, NO.opening_unit(m1, days), NO.session_end_flags(m1),
                     tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close")))
    return _CACHE[m]


def job(args):
    ekw, scores, days = args
    kw = {k: v for k, v in ekw.items() if k != "stop"}
    p = NO.Params(**kw, **STOPS[ekw["stop"]], rr=RR)
    cands = []
    for m in MARKETS:
        m1, unit, xout, arrs = market_data(m, days)
        cd = NO.candidates(m1, m, scores, unit, p)
        if len(cd):
            cands.append((cd, arrs, xout, 2 * D.EXNESS_STANDARD_SPREAD[m]))
    rows, trade_log = [], None
    no_exit = None
    for be, hold, pick in itertools.product(*EXIT_GRID.values()):
        trades = []
        for cd, (o, h, l, c), xout, cost in cands:
            if hold == "24h":
                if no_exit is None or len(no_exit) != len(o):
                    no_exit = np.zeros(len(o), np.bool_)
                xo, mb = no_exit, 24 * 60
            else:
                xo, mb = xout, 0
            for r in cd.itertuples():
                R = trade_r(o, h, l, c, xo, int(r.entry_i), int(r.dir), float(r.sl), RR, be, cost, mb)
                trades.append((r.day, r.market, r.dir, r.strength, R))
        t = pd.DataFrame(trades, columns=["day", "market", "dir", "strength", "r"])
        if t.empty:
            continue
        if pick == "confluence2":
            t = t[t.groupby("day").market.transform("size") >= 2]
            t = t.sort_values("strength", ascending=False).groupby("day").head(1)
            daily = t.set_index("day").r
        elif pick == "best":
            t = t.sort_values("strength", ascending=False).groupby("day").head(1)
            daily = t.set_index("day").r
        else:
            daily = t.groupby("day").r.mean()
        daily = daily.sort_index()
        row = {**ekw, "be": be, "hold": hold, "pick": pick}
        for k, (a, b) in {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}.items():
            r = daily[(daily.index >= a) & (daily.index < b)].to_numpy()
            if len(r) == 0:
                continue
            eq = np.cumprod(np.maximum(1 + RISK * r, 0))
            loss = -r[r < 0].sum()
            row.update({f"{k}_days": len(r), f"{k}_win": (r > 0).mean(), f"{k}_avg_r": r.mean(),
                        f"{k}_pf": r[r > 0].sum() / loss if loss > 0 else np.inf,
                        f"{k}_usd": 1000 * eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
        rows.append(row)
    return rows


def main():
    days = list(trading_days(date(2024, 11, 1), date(2026, 10, 15)))
    cal = pd.read_csv(ROOT / "data" / "calendar" / "ff_calendar.csv", parse_dates=["time_utc"])
    scores = NO.day_scores(cal, days)
    out = ROOT / "results" / "news_open"
    jobs = [(dict(zip(ENTRY_GRID, v)), scores, days) for v in itertools.product(*ENTRY_GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=6)):
            rows += r
            if i % 100 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    pd.DataFrame(rows).to_csv(out / "grid_v2_rr3.csv", index=False)
    print(len(rows), "configurations")


if __name__ == "__main__":
    main()
