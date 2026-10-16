#!/usr/bin/env python3
"""How big can $1,000 get in 2026 - measured honestly?

For every strategy variant we collect its trades (in R multiples), then:
  1. on 2025 ONLY, find the growth-optimal fraction of equity to risk per
     trade (Kelly, by grid search on mean log growth);
  2. trade 2026 with HALF that fraction (standard safety margin), chosen
     without looking at 2026, and record what $1,000 becomes.
Ranking is by 2025 growth (what you could have known in January 2026).

    python scripts/search_growth.py --out results/growth
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, hwr, indicators as ind  # noqa: E402
from backtester import trend_rider as tr, trend_rider_v2 as v2  # noqa: E402
from backtester.engine import backtest as tf_backtest  # noqa: E402
from backtester.strategies import STRATEGIES  # noqa: E402
from search_high_winrate import load  # noqa: E402

F_GRID = np.r_[np.arange(0.0025, 0.05, 0.0025), np.arange(0.05, 0.6, 0.01)]


def kelly(r: np.ndarray) -> tuple[float, float]:
    """Growth-optimal fraction and the mean log growth per trade at it."""
    best_f, best_g = 0.0, 0.0
    for f in F_GRID:
        x = 1 + f * r
        if (x <= 0).any():
            break
        g = np.log(x).mean()
        if g > best_g:
            best_f, best_g = f, g
    return best_f, best_g


def grow(r: np.ndarray, f: float):
    eq = np.cumprod(1 + f * r) if len(r) else np.array([1.0])
    return eq[-1], (eq / np.maximum.accumulate(eq) - 1).min()


def evaluate(meta: dict, t: pd.DataFrame) -> dict | None:
    r25 = t[(t.entry_time >= "2025-01-01") & (t.entry_time < "2026-01-01")].r.to_numpy()
    r26 = t[t.entry_time >= "2026-01-01"].r.to_numpy()
    if len(r25) < 30:
        return None
    f, g = kelly(r25)
    if f == 0:
        return None
    use = min(f / 2, 0.25)
    m25, dd25 = grow(r25, use)
    m26, dd26 = grow(r26, use)
    return {**meta, "trades_2025": len(r25), "trades_2026": len(r26), "kelly_f": f, "risk_used": use,
            "x_2025": m25, "dd_2025": dd25, "x_2026": m26, "dd_2026": dd26,
            "win_2026": float((r26 > 0).mean()) if len(r26) else np.nan,
            "avgR_2025": r25.mean(), "avgR_2026": r26.mean() if len(r26) else np.nan}


def job(args):
    sym, tf = args
    df = load(sym, tf)
    cost = D.EXNESS_STANDARD_SPREAD[sym]
    rows = []
    for fam, (fn, grid) in hwr.FAMILIES.items():
        for p in grid:
            e = evaluate({"market": sym, "tf": tf, "family": fam, "params": str(p)}, hwr.run(df, fn(df, **p), cost))
            if e:
                rows.append(e)
    if tf in ("1h", "4h"):
        a = ind.atr(df, 14)
        for name, (fn, sig_grid, risk_grid) in STRATEGIES.items():
            for sp in sig_grid:
                sig = fn(df, **sp)
                for rp in risk_grid:
                    t = tf_backtest(df, sig, a, cost, **rp).trades
                    e = evaluate({"market": sym, "tf": tf, "family": "Trend: " + name, "params": str({**sp, **rp})}, t)
                    if e:
                        rows.append(e)
    return rows


def v2_jobs():
    rows = []
    for sym, stops in (("XAUUSD", (5, 10, 15)), ("NAS100", (25, 40, 60))):
        df = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
        for ms in stops:
            for rr in (2.0, 3.0, 5.0):
                for be in (0.0, 1.0):
                    P = v2.Params(min_stop_price=ms, rr=rr, be_trigger=be)
                    t = tr.backtest(df, P, D.EXNESS_STANDARD_SPREAD[sym], sig=v2.signals(df, P)).trades
                    e = evaluate({"market": sym, "tf": "1min", "family": "Trend Rider v2",
                                  "params": str(dict(min_stop=ms, rr=rr, be=be))}, t)
                    if e:
                        rows.append(e)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "growth"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(m, tf) for m in ("XAUUSD", "NAS100", "US30", "BTCUSD") for tf in ("15min", "1h", "4h")]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        futs = [ex.submit(job, j) for j in jobs] + [ex.submit(v2_jobs)]
        for f in futs:
            r = f.result()
            rows += r
            print("batch done:", len(r), flush=True)
    res = pd.DataFrame(rows).sort_values("x_2025", ascending=False)
    res.to_csv(out / "growth_all.csv", index=False)
    print(len(res), "variants with a positive 2025 edge")


if __name__ == "__main__":
    main()
