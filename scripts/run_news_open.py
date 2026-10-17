#!/usr/bin/env python3
"""Backtest the 'read the news, trade the NY open' strategy (and its controls).

    python scripts/run_news_open.py
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
ENTRY_GRID = dict(min_score=(1, 2, 3), observe_min=(5, 15, 30), min_move=(0.0, 0.25, 0.5),
                  entry=("momentum", "pullback"), stop=("window", "units"), mode=("news", "ignore_news", "against_news"))
EXIT_GRID = dict(rr=(1.5, 2.0, 3.0, 0.0), be=(0.0, 1.0), pick=("best", "all"))


@njit(cache=True)
def trade_r(o, h, l, c, xout, e, d, sl, rr, be, cost):
    entry = o[e] + cost if d == 1 else o[e]
    stop = entry - d * sl
    tgt = entry + d * rr * sl if rr > 0 else 0.0
    moved = False
    for j in range(e, len(o)):
        bo = o[j] if d == 1 else o[j] + cost
        bh = h[j] if d == 1 else h[j] + cost
        bl = l[j] if d == 1 else l[j] + cost
        if d == 1:
            if bl <= stop:
                return (min(bo, stop) - entry) / sl, j
            if tgt > 0 and bh >= tgt:
                return (max(bo, tgt) - entry) / sl, j
        else:
            if bh >= stop:
                return (entry - max(bo, stop)) / sl, j
            if tgt > 0 and bl <= tgt:
                return (entry - min(bo, tgt)) / sl, j
        if be > 0 and not moved:
            if (d == 1 and bh >= entry + be * sl) or (d == -1 and bl <= entry - be * sl):
                stop = entry + d * 0.1 * sl
                moved = True
        if xout[j] and j > e:                                    # 16:00 ET: close at this bar's open
            px = o[j] if d == 1 else o[j] + cost
            return d * (px - entry) / sl, j
    j = len(o) - 1
    px = c[j] if d == 1 else c[j] + cost
    return d * (px - entry) / sl, j


_CACHE = {}


def market_data(m, days):
    if m not in _CACHE:
        m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
        _CACHE[m] = (m1, NO.opening_unit(m1, days), NO.session_end_flags(m1))
    return _CACHE[m]


def job(args):
    ekw, scores, days = args
    p = NO.Params(**ekw)
    cands = []
    for m in MARKETS:
        m1, unit, xout = market_data(m, days)
        cd = NO.candidates(m1, m, scores, unit, p)
        if len(cd):
            cost = 2 * D.EXNESS_STANDARD_SPREAD[m]                  # spread + equal slippage at the open
            arrs = tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
            cd["cost"] = cost
            cd["_m"] = m
            cands.append((cd, arrs, xout))
    rows = []
    for rr, be, pick in itertools.product(*EXIT_GRID.values()):
        trades = []
        for cd, (o, h, l, c), xout in cands:
            for r in cd.itertuples():
                R, _ = trade_r(o, h, l, c, xout, int(r.entry_i), int(r.dir), float(r.sl), rr, be, float(r.cost))
                trades.append((r.day, r.market, r.strength, R))
        t = pd.DataFrame(trades, columns=["day", "market", "strength", "r"])
        if t.empty:
            continue
        if pick == "best":
            t = t.sort_values("strength", ascending=False).groupby("day").head(1)
            daily = t.set_index("day").r
        else:
            daily = t.groupby("day").r.mean()
        daily = daily.sort_index()
        row = {**ekw, "rr": rr, "be": be, "pick": pick}
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
    out.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out / "daily_usd_scores.csv")
    jobs = [(dict(zip(ENTRY_GRID, v)), scores, days) for v in itertools.product(*ENTRY_GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=4)):
            rows += r
            if i % 50 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    pd.DataFrame(rows).to_csv(out / "grid.csv", index=False)
    print(len(rows), "configurations")


if __name__ == "__main__":
    main()
