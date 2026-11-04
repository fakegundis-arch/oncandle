#!/usr/bin/env python3
"""Backtest the locked versions on the build period (Jan-Jun 2026) through the research toolkit
scripts/asia_news_lab.py, with the protocol's pass rules - the bot's own make_trades, so these are the numbers the
live bot would have produced.

    cd /home/user/oncandle && PYTHONDONTWRITEBYTECODE=1 python <this folder>/run_backtest.py [--locked LOCKED.json]
                                                                  [--repo /home/user/oncandle] [--trades out.csv]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from newsbot.backtest import make_trades  # noqa: E402


def combined(t: pd.DataFrame, a: str, b: str, risk: float) -> dict:
    t = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    gl, gw = -r[r < 0].sum(), r[r > 0].sum()
    return dict(n=len(r), R=float(r.sum()), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()), usd=float(1000 * eq[-1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--locked", default=str(HERE / "LOCKED.json"))
    ap.add_argument("--repo", default=str(HERE.parents[1]))
    ap.add_argument("--trades", default="")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.repo) / "scripts"))
    import asia_news_lab as L

    V = json.loads(Path(a.locked).read_text())["versions"]
    cal = L.calendar_train()
    res, alltr, pair = {}, [], {k: [] for k in ("base", "x2", "late")}
    for name, cfg in V.items():
        sym = cfg["symbol"]
        m1 = L.prices_train(sym)
        t1 = make_trades(cfg, cal, m1, L.COST[sym])
        t2 = make_trades(cfg, cal, m1, 2 * L.COST[sym])
        t3 = make_trades(cfg, cal, m1, L.COST[sym], entry_delay=int(cfg["entry_delay"]) + 2)
        t1, t2, t3 = (t[(t.entry_time >= L.TRAIN[0]) & (t.entry_time < L.TRAIN[1])] for t in (t1, t2, t3))
        m, m2, m3 = L.evaluate_train(t1), L.evaluate_train(t2), L.evaluate_train(t3)
        chk = L.passes_train(m, m2, m3)
        res[name] = (m, m2, m3, chk)
        alltr.append(t1.assign(version=name, symbol=sym))
        if name.startswith("pair_"):
            pair["base"].append(t1); pair["x2"].append(t2); pair["late"].append(t3)
    print(f"{'version':9s} {'n':>3s} {'R':>7s} {'PF':>6s} {'win':>5s} {'maxDD':>7s} {'$1000->':>8s} {'JanMar R':>8s} "
          f"{'AprJun R':>8s} {'PF 2x':>6s} {'PF late':>7s}  pass")
    for name, (m, m2, m3, chk) in res.items():
        print(f"{name:9s} {m['n']:3d} {m['R']:7.2f} {m['pf']:6.2f} {m['win']:5.2f} {m['dd']:7.1%} {m['usd']:8.0f} "
              f"{m['jan-mar_R']:8.2f} {m['apr-jun_R']:8.2f} {m2['pf']:6.2f} {m3['pf']:7.2f}  "
              f"{'PASS' if chk['all'] else 'fail: ' + ', '.join(k for k, v in chk.items() if not v and k != 'all')}")
    if pair["base"]:
        P = {k: pd.concat(v) for k, v in pair.items()}
        m = combined(P["base"], *L.TRAIN, L.RISK)
        q1, q2 = combined(P["base"], *L.TRAIN_Q["jan-mar"], L.RISK), combined(P["base"], *L.TRAIN_Q["apr-jun"], L.RISK)
        m2, m3 = combined(P["x2"], *L.TRAIN, L.RISK), combined(P["late"], *L.TRAIN, L.RISK)
        chk = L.passes_train({**m, "jan-mar_R": q1["R"], "apr-jun_R": q2["R"]}, m2, m3)
        print(f"{'PAIR all':9s} {m['n']:3d} {m['R']:7.2f} {m['pf']:6.2f} {'':5s} {m['dd']:7.1%} {m['usd']:8.0f} "
              f"{q1['R']:8.2f} {q2['R']:8.2f} {m2['pf']:6.2f} {m3['pf']:7.2f}  "
              f"{'PASS' if chk['all'] else 'fail: ' + ', '.join(k for k, v in chk.items() if not v and k != 'all')}"
              "   (AUDUSD + NZDUSD + USDJPY in time order)")
    if a.trades:
        pd.concat(alltr).sort_values("entry_time").to_csv(a.trades, index=False)
        print("trades ->", a.trades)


if __name__ == "__main__":
    main()
