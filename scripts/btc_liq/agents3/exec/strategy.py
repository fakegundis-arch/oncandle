"""exec researcher - version 3 (honest metrics timing: a 5-min row is used only from create_time + 360 s).

Signal family: Binance BTCUSDT open interest fell by at least `doi` over the last `w` five-minute rows (the row with
create_time ct describes [ct, ct+300) and is known at ct + 360 s = btc_common Market.metrics.known_ts) while the
Binance price moved by at least `mv` over the same window [ct+300-300w, ct+300).  At the known time the bot trades
side * sign(move) on Exness: side = +1 follows the move, side = -1 fades it.  Entry: market (kind 0) or a limit order
`off` x vol away in the trade's favour (kind 1: for a fade that is further into the flush) living `life` s.
Stop: `stop` x vol (stype "v") or `stop` x the window's move in $ (stype "m").  Target `tp` R (nan = none), timer
`hold` s, break-even after `be` R, trailing `tr` R.  All fills, exits and money come from btc_common.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

CANDIDATES: dict = {}
REJECTED: dict = {}      # best settings found that did NOT pass the luck check (for information only)


def signals(mk: bc.Market, p: dict):
    """-> decision ts, trade direction, vol at decision, window move in $ (one per qualifying row, time order)."""
    m = mk.metrics
    ts = m.ts.to_numpy(np.int64)
    full = np.arange(ts[0], ts[-1] + 1, 300, dtype=np.int64)
    oi = pd.Series(m.sum_open_interest.to_numpy(float), index=ts).reindex(full)
    known = pd.Series(m.known_ts.to_numpy(np.int64), index=ts).reindex(full)   # ct + 360 (btc_common rule)
    w = int(p.get("w", 1))
    doi = (oi / oi.shift(w) - 1).to_numpy()                                    # NaN if either row is missing
    have = ~known.isna().to_numpy()
    known = known.fillna(-1).to_numpy(np.int64)
    end = full + 300 - mk.t0                                                   # end of the newest row's window
    ok = have & ~np.isnan(doi) & (end - 300 * w >= 0) & (known - mk.t0 >= 1) & (known - mk.t0 < mk.n)
    e = np.clip(end, 300 * w, mk.n - 1)
    mv = mk.c[e] / mk.c[e - 300 * w] - 1                                       # Binance seconds < known_ts
    sel = ok & (doi <= -p["doi"]) & (np.abs(mv) >= p["mv"])
    if p.get("net", 0):
        net = (mk.CB[e] - mk.CB[e - 300 * w]) - (mk.CS[e] - mk.CS[e - 300 * w])
        sel &= np.sign(net) == np.sign(mv)
    dec = known[sel]
    d = (p.get("side", 1) * np.sign(mv[sel])).astype(np.int64)
    vol = mk.vol[dec - mk.t0]
    move = np.abs(mv[sel]) * mk.c[dec - mk.t0 - 1]
    good = ~np.isnan(vol)
    return dec[good], d[good], vol[good], move[good]


def backtest(params, data_dir, start, end, stress=False) -> pd.DataFrame:
    p = params
    look = (pd.Timestamp(start) - pd.Timedelta(days=32)).strftime("%Y-%m-%d")
    mk = bc.Market(data_dir, look, end)
    dec, d, vol, move = signals(mk, p)
    sd = p["stop"] * (vol if p.get("stype", "v") == "v" else move)
    t = bc.trades(mk, dec, d, kind=p.get("kind", 0), offset=p.get("off", 0.0) * vol, life=p.get("life", 180),
                  stop_dist=sd, tp_r=p.get("tp", np.nan), hold=p.get("hold", 0), be_at=p.get("be", np.nan),
                  trail=p.get("tr", np.nan), stress=stress)
    a, b = bc.ts_of(start), bc.ts_of(end)
    t = t[(t.entry_ts >= a) & (t.entry_ts < b)].sort_values(["entry_ts", "sig_ts"]).reset_index(drop=True)
    return t[["sig_ts", "dir", "entry_ts", "exit_ts", "r", "sd", "entry_px"]]
