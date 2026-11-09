"""Versions 1 and 2 rebuilt with HONEST metrics timing (lead, Nov 9 2026), as baselines for version 3.

A Binance 5-minute metrics row with create_time ct describes [ct, ct+300) and is known at ct + 360 s.  Version 1: the
open interest of that row fell >= 0.7 % against the previous row and the price moved >= 0.3 % over [ct, ct+300) ->
follow the move at ct + 360 (+ latency), stop 5 x vol, target 2R, out after 5 min, one at a time.  Version 2: open
interest -0.5 %, move 0.3 %, net taker volume over the window agrees with the move -> follow, stop 8 x vol, target
1.5R, break-even at +1R then a 1R trail, out after 5 min, one at a time.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc_common as bc  # noqa: E402

CANDIDATES = {
    "v1_honest": dict(x=0.7, y=0.3, flow=False, stop=5.0, tp=2.0, hold=300, be=np.nan, tr=np.nan, maxpos=1),
    "v2_honest": dict(x=0.5, y=0.3, flow=True, stop=8.0, tp=1.5, hold=300, be=1.0, tr=1.0, maxpos=1),
}


def signals(mk, p):
    m = mk.metrics
    ts, oi = m.ts.to_numpy(np.int64), m.sum_open_interest.to_numpy(float)
    r = np.arange(1, len(ts))
    ok = ts[r] - ts[r - 1] == 300
    doi = (oi[r] / oi[r - 1] - 1) * 100
    w0, w1, sig = ts[r] - mk.t0, ts[r] + 300 - mk.t0, ts[r] + 360
    ok &= (w0 >= 0) & (sig - mk.t0 < mk.n) & np.isfinite(doi)
    w0, w1, isg = np.clip(w0, 0, mk.n - 1), np.clip(w1, 0, mk.n - 1), np.clip(sig - mk.t0, 0, mk.n - 1)
    dp = (mk.c[w1] / mk.c[w0] - 1) * 100
    d = np.sign(dp).astype(np.int64)
    cond = ok & (doi <= -p["x"]) & (np.abs(dp) >= p["y"]) & np.isfinite(mk.vol[isg]) & (mk.vol[isg] > 0)
    if p["flow"]:
        net = (mk.CB[w1 + 1] - mk.CB[w0 + 1]) - (mk.CS[w1 + 1] - mk.CS[w0 + 1])
        cond &= d * net > 0
    return sig[cond], d[cond]


def backtest(params, data_dir, start, end, stress=False):
    p = params
    mk = bc.Market(data_dir, str((pd.Timestamp(start) - pd.Timedelta(days=32)).date()), end)
    s, d = signals(mk, p)
    a, b = bc.ts_of(start), bc.ts_of(end)
    keep = (s >= a - 3600) & (s < b)
    s, d = s[keep], d[keep]
    t = bc.trades(mk, s, d, stop_dist=p["stop"] * mk.vol[s - mk.t0], tp_r=p["tp"], hold=p["hold"], be_at=p["be"],
                  trail=p["tr"], stress=stress)
    t = t[(t.entry_ts >= a) & (t.entry_ts < b)].sort_values(["entry_ts", "sig_ts"]).reset_index(drop=True)
    return t[["sig_ts", "dir", "entry_ts", "exit_ts", "r", "sd", "entry_px"]]
