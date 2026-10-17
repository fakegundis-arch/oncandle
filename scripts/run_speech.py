#!/usr/bin/env python3
"""Backtest the Trump / Fed-chair speech straddle (backtester/speech.py) on 11 markets.

    python scripts/run_speech.py        # -> results/speech/grid.csv
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import data as D, indicators as ind, speech as S  # noqa: E402
from backtester.news_open import USD_BULL_DIRECTION  # noqa: E402

MARKETS = list(USD_BULL_DIRECTION)
GRID = dict(k=(0.5, 1.0, 2.0, 3.0, 5.0), s=(0.5, 1.0, 2.0), rr=(1.0, 2.0, 3.0, 5.0), be=(0.0, 1.0),
            expiry=(5, 15, 30, 60, 120), hold=(60, 240))
SETS = {"trump": lambda e: e.who == "trump", "trump_high": lambda e: (e.who == "trump") & (e.impact == "high"),
        "fed": lambda e: e.who == "fed", "both": lambda e: e.who.notna()}
YEARS = {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}
COST_X = 3.0


def stats(t, r):
    out = {}
    for k, (a, b) in YEARS.items():
        x = r[(t >= np.datetime64(a)) & (t < np.datetime64(b))]
        x = x[np.isfinite(x)]
        out[f"{k}_n"] = len(x)
        if len(x) == 0:
            continue
        loss = -x[x < 0].sum()
        eq = 1000 * np.cumprod(np.maximum(1 + 0.10 * x, 0))
        out.update({f"{k}_win": (x > 0).mean(), f"{k}_avg": x.mean(), f"{k}_pf": x[x > 0].sum() / loss if loss > 0 else 99,
                    f"{k}_usd": eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
    return out


def main():
    cal = pd.read_csv(ROOT / "data" / "calendar" / "ff_calendar.csv", parse_dates=["time_utc"])
    ev = S.speech_events(cal)
    out = ROOT / "results" / "speech"
    out.mkdir(parents=True, exist_ok=True)
    ev.to_csv(out / "events.csv", index=False)
    per = {}
    for m in MARKETS:
        m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
        tr = ind.true_range(m1).rolling(240).mean().shift().to_numpy()
        idx = m1.index
        i = idx.searchsorted(ev.time_utc)
        ok = (i < len(idx) - 300) & (i >= 240)
        ok[ok] &= (idx[i[ok]] - ev.time_utc[ok].to_numpy()) <= pd.Timedelta("1min")
        arr = tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
        per[m] = (ev[ok].reset_index(drop=True), i[ok].astype(np.int64), tr[i[ok]], arr)
        print(m, ok.sum(), "events with data", flush=True)
    rows = []
    for kw in (dict(zip(GRID, v)) for v in itertools.product(*GRID.values())):
        res = {}
        for m, (e, i0, a, (o, h, l, c)) in per.items():
            R, _ = S.straddle(o, h, l, c, i0, a, kw["k"], kw["s"], kw["rr"], kw["be"], kw["expiry"], kw["hold"],
                              COST_X * D.EXNESS_STANDARD_SPREAD[m])
            res[m] = (e, R)
        for sname, f in SETS.items():
            frames = []
            for m, (e, R) in res.items():
                sel = f(e).to_numpy()
                frames.append(pd.DataFrame({"t": e.time_utc[sel].to_numpy(), "m": m, "r": R[sel]}))
                st = stats(e.time_utc[sel].to_numpy(), R[sel])
                rows.append({**kw, "set": sname, "pick": m, **st})
            allm = pd.concat(frames).dropna().groupby("t").r.mean()
            rows.append({**kw, "set": sname, "pick": "all", **stats(allm.index.to_numpy(), allm.to_numpy())})
    pd.DataFrame(rows).to_csv(out / "grid.csv", index=False)
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
