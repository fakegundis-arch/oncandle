#!/usr/bin/env python3
"""Round 2: fine grid on gold, Asian session (the most robust family of the deep search)."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, deep, indicators as ind  # noqa: E402
from deep_search import PERIODS, metrics  # noqa: E402

m1 = D.load_csv(ROOT / "data" / "XAUUSD_M1.csv").drop(columns="spread", errors="ignore")
cost = D.EXNESS_STANDARD_SPREAD["XAUUSD"]
EXITS = [("RR 1", dict(rr=1.0)), ("RR 1.5", dict(rr=1.5)), ("RR 2", dict(rr=2.0)), ("RR 3", dict(rr=3.0)),
         ("RR 1.5 + BE", dict(rr=1.5, be=1.0)), ("RR 2 + BE", dict(rr=2.0, be=1.0)), ("RR 3 + BE", dict(rr=3.0, be=1.0)),
         ("Trail 1.5 ATR", dict(trail=1.5)), ("Trail 2 ATR", dict(trail=2.0)), ("Trail 3 ATR", dict(trail=3.0)),
         ("Session close", dict(close=True)), ("RR 2 + session close", dict(rr=2.0, close=True)),
         ("RR 3 + BE + session close", dict(rr=3.0, be=1.0, close=True))]
rows = []
for tf, bph in (("5min", 12), ("15min", 4)):
    df = deep.resample(m1, tf)
    a = ind.atr(df, 14).to_numpy()
    o, h, l, c = (df[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    ins = deep.in_session(df, "asian")[0]
    cands = []
    for n, th in itertools.product((10, 20, 30, 40, 55), (0, 20, 50, 100)):
        cc, hh, ll = df.close, df.high, df.low
        up, dn = hh.rolling(n).max().shift(), ll.rolling(n).min().shift()
        L = (cc > up) & (cc.shift() <= up.shift())
        S_ = (cc < dn) & (cc.shift() >= dn.shift())
        if th:
            tr = deep.htf_trend(df, bph, th)
            L, S_ = L.to_numpy() & (tr == 1), S_.to_numpy() & (tr == -1)
        cands.append((f"Donchian{n} trend{th}h", ins & np.asarray(L, bool), ins & np.asarray(S_, bool)))
    L, S_, _, _ = deep.e_pdhl(df, "asian")
    cands.append(("Prev-day H/L break", np.asarray(L, bool), np.asarray(S_, bool)))
    for name, L, S_ in cands:
        sig = np.where(L, 1, np.where(S_, -1, 0)).astype(np.int64)
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            sl = np.nan_to_num(np.maximum(k * a, 10 * cost))
            for ex_name, ex in EXITS:
                ti, to, td, tr_ = deep.run_engine(o, h, l, c, sig, sl, sl * ex.get("rr", 0.0),
                                                  np.nan_to_num(a * ex.get("trail", 0.0)),
                                                  ~ins if ex.get("close") else np.zeros(len(df), bool), 0, cost,
                                                  ex.get("be", 0.0), 0.1 if ex.get("be") else 0.0)
                et = df.index[ti]
                row = {"tf": tf, "entry": name, "stop_atr": k, "exit": ex_name}
                for p, (a0, b0) in PERIODS.items():
                    m = (et >= a0) & (et < b0)
                    row.update({f"{p}_{kk}": v for kk, v in metrics(tr_[m]).items()})
                rows.append(row)
    print("done", tf, flush=True)
pd.DataFrame(rows).to_csv(ROOT / "results" / "deep" / "gold_asian_grid.csv", index=False)
print(len(rows), "runs")
