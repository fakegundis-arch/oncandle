#!/usr/bin/env python3
"""Search the non-trend families in backtester/alt.py; choose on 2025 (+ Q4 2024), judge on 2026.

    python scripts/run_alt.py            # -> results/alt/{pairs,rsi2,gap}.csv, seasonality.csv
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import alt as A  # noqa: E402
from backtester.news_open import USD_BULL_DIRECTION  # noqa: E402

MARKETS = list(USD_BULL_DIRECTION)
OUT = ROOT / "results" / "alt"
PAIRS = [("XAUUSD", "XAGUSD"), ("NAS100", "US500"), ("US30", "US500"), ("NAS100", "US30"), ("EURUSD", "GBPUSD"),
         ("BTCUSD", "NAS100"), ("XAUUSD", "EURUSD"), ("USDCAD", "USOIL"), ("USDJPY", "US500"), ("XAGUSD", "EURUSD")]
BARS_PER_DAY = {"15min": 96, "1h": 24}


def pairs_job(kw):
    a, b = kw.pop("pair")
    bpd = BARS_PER_DAY[kw["rule"]]
    t = A.pairs_trades(a, b, rule=kw["rule"], L=int(kw["L_days"] * bpd), zin=kw["zin"], zstop=kw["zin"] + kw["zgap"],
                       max_bars=int(kw["hold_days"] * bpd))
    return {"pair": f"{a}/{b}", **kw, **A.stats(t)}


def rsi_job(kw):
    t = A.rsi2_trades(kw["market"], rule=kw["rule"], lo=kw["lo"], stop_atr=kw["stop_atr"], filt=kw["filt"],
                      max_bars=kw["max_bars"], both=kw["both"])
    return {**kw, **A.stats(t)}


def gap_job(kw):
    t = A.gap_trades(kw["market"], g=kw["g"], stop_atr=kw["stop_atr"], max_bars=kw["max_bars"])
    return {**kw, **A.stats(t)}


def grid(d):
    return [dict(zip(d, v)) for v in itertools.product(*d.values())]


def seasonality():
    """Pick (market, hour, side) slots on 2025 only (t-stat >= 2.5 and same sign in Q4 2024), trade them in 2026."""
    rows, trades = [], []
    for m in MARKETS:
        h = A.hour_returns(m)
        for wd_split in (False, True):
            keys = ["hour", "wd"] if wd_split else ["hour"]
            for side in ("long", "short"):
                tr = h[(h.index >= "2025-01-01") & (h.index < "2026-01-01")]
                q4 = h[h.index < "2025-01-01"]
                st = tr.groupby(keys)[side].agg(["mean", "std", "count"])
                st["t"] = st["mean"] / st["std"] * np.sqrt(st["count"])
                q4m = q4.groupby(keys)[side].mean()
                for key, r in st[(st.t >= 2.5)].iterrows():
                    if q4m.get(key, -1) <= 0:
                        continue
                    sel = (h.hour == (key[0] if wd_split else key))
                    if wd_split:
                        sel &= h.wd == key[1]
                    x = h[sel]
                    t = pd.DataFrame({"entry_time": x.index, "exit_time": x.index + pd.Timedelta("1h"),
                                      "market": m, "r": x[side].to_numpy()})
                    s = A.stats(t)
                    rows.append({"market": m, "slot": str(key), "wd_split": wd_split, "side": side,
                                 "t25": r.t, **s})
                    trades.append(t.assign(slot=f"{m} {side} {key}"))
    return pd.DataFrame(rows), (pd.concat(trades) if trades else pd.DataFrame())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "pairs": (pairs_job, grid(dict(pair=PAIRS, rule=("15min", "1h"), L_days=(1, 5, 20), zin=(1.5, 2.0, 2.5, 3.0),
                                       zgap=(1.5, 3.0), hold_days=(1, 5)))),
        "rsi2": (rsi_job, grid(dict(market=MARKETS, rule=("15min", "1h", "4h"), lo=(3.0, 5.0, 10.0, 20.0),
                                    stop_atr=(2.0, 3.0, 5.0), filt=(True, False), max_bars=(5, 10, 20), both=(True, False)))),
        "gap": (gap_job, grid(dict(market=MARKETS, g=(0.25, 0.5, 1.0, 2.0), stop_atr=(1.0, 2.0, 3.0),
                                   max_bars=(4, 16, 64)))),
    }
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    with ProcessPoolExecutor(4) as ex:
        for name, (fn, js) in jobs.items():
            if only and name not in only:
                continue
            rows = list(ex.map(fn, js, chunksize=8))
            pd.DataFrame(rows).to_csv(OUT / f"{name}.csv", index=False)
            print(name, len(rows), flush=True)
    if only and "seasonality" not in only:
        return
    s, t = seasonality()
    s.to_csv(OUT / "seasonality.csv", index=False)
    if len(t):
        t.to_csv(OUT / "seasonality_trades.csv", index=False)
    print("seasonality", len(s))


if __name__ == "__main__":
    main()
