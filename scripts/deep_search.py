#!/usr/bin/env python3
"""Deep search at 10% risk per trade: session entries x stops x exits on
BTC, gold, Nasdaq and Dow (Exness spreads).  Chosen on 2025, judged on 2026.

    python scripts/deep_search.py --out results/deep
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import data as D, deep, indicators as ind  # noqa: E402

RISK = 0.10
PERIODS = {"q4_24": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"),
           "y26": ("2026-01-01", "2027-01-01")}
FLOOR_SPREADS = 10          # stop never tighter than 10x the spread


def metrics(r):
    if len(r) == 0:
        return {"n": 0}
    eq = np.cumprod(np.maximum(1 + RISK * r, 0.0))
    loss = -r[r < 0].sum()
    return {"n": len(r), "win": float((r > 0).mean()), "avg_r": float(r.mean()),
            "pf": float(r[r > 0].sum() / loss) if loss > 0 else np.inf,
            "x10": float(eq[-1]), "dd10": float((eq / np.maximum.accumulate(eq) - 1).min())}


def job(sym):
    t0 = time.time()
    m1 = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    cost = D.EXNESS_STANDARD_SPREAD[sym]
    floor = FLOOR_SPREADS * cost
    frames = {tf: deep.resample(m1, tf) for tf in ("1min", "5min", "15min")}
    atrs = {tf: ind.atr(f, 14).to_numpy() for tf, f in frames.items()}
    rows = []
    for name, tf, fn, kw in deep.entries(sym, floor * 2):
        df = frames[tf]
        L, Sh, sl_l, sl_s = fn(df, **kw)
        L, Sh = np.asarray(L, bool), np.asarray(Sh, bool)
        sig = np.where(L, 1, np.where(Sh, -1, 0)).astype(np.int64)
        if (sig != 0).sum() < 20:
            continue
        ins = deep.in_session(df, kw["ses"])[0]
        a = atrs[tf]
        o, h, l, c = (df[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
        idx = df.index
        for stop in deep.STOPS:
            if stop == "struct":
                if sl_l is None:
                    continue
                sl = np.where(sig == 1, sl_l, np.where(sig == -1, sl_s, 0.0))
            else:
                sl = stop * a
            sl = np.nan_to_num(np.maximum(np.asarray(sl, np.float64), floor))
            s2 = np.where(sl > 0, sig, 0).astype(np.int64)
            for ex_name, ex in deep.EXITS:
                tp = sl * ex.get("rr", 0.0)
                trail = np.nan_to_num(a * ex.get("trail", 0.0))
                xout = ~ins if ex.get("close") else np.zeros(len(df), bool)
                ti, to, td, tr = deep.run_engine(o, h, l, c, s2, sl, tp, trail, xout, 0, cost,
                                                 ex.get("be", 0.0), 0.1 if ex.get("be") else 0.0)
                et = idx[ti]
                row = {"market": sym, "entry": name, "tf": tf, "session": kw["ses"],
                       "stop": str(stop), "exit": ex_name}
                for p, (a0, b0) in PERIODS.items():
                    m = (et >= a0) & (et < b0)
                    row.update({f"{p}_{k}": v for k, v in metrics(tr[m]).items()})
                rows.append(row)
    print(f"done {sym}: {len(rows)} runs in {time.time() - t0:.0f}s", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "deep"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for r in ex.map(job, ["XAUUSD", "NAS100", "US30", "BTCUSD"]):
            rows += r
    pd.DataFrame(rows).to_csv(out / "deep_all.csv", index=False)
    print(len(rows), "backtests")


if __name__ == "__main__":
    main()
