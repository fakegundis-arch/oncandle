"""Version-3 candidate(s) from researcher "flow".

Idea: a fast one-sided price burst on Binance (>= X x vol in W seconds) that carries a LARGE single aggressive print
(the biggest aggressive trade in the burst direction over the last 60 s is >= 30 % of the biggest aggressive trade
of the last hour) and during which open interest ROSE (new positions, not forced closes) -> follow it for up to 2 h.
The open-interest change of the 5-min bucket that holds the burst is only used once it is known (bucket start + 360 s,
btc_common known_ts), and the order is sent at that moment.
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

CANDIDATES = {
    # chosen by the Jan-Apr search (best Jan-Apr final balance meeting the rules), then checked on May-Jun
    "flow_bigprint_oiup_30s": dict(W=30, X=8, refr=900, oi_up=0.0005, big_rel=0.3, stop=10, tp=3.0, hold=7200, maxpos=2),
    # broader / calmer variant from the middle of the plateau: 60-s bursts, wider stop, no target
    "flow_bigprint_oiup_60s": dict(W=60, X=8, refr=900, oi_up=0.0015, big_rel=0.3, stop=20, tp=float("nan"), hold=7200,
                                   maxpos=2),
}


@nb.njit(cache=True)
def _bursts(c, vol, W, X, refr, lo, hi):
    out_s, out_d = [], []
    last = -10 ** 9
    for s in range(max(lo, W + 1), hi):
        v = vol[s]
        if not (v > 0):
            continue
        m = c[s - 1] - c[s - 1 - W]
        if abs(m) >= X * v and s - last >= refr:
            out_s.append(s)
            out_d.append(1 if m > 0 else -1)
            last = s
    return np.array(out_s, np.int64), np.array(out_d, np.int64)


@nb.njit(cache=True)
def _rmax(a, s, W):
    out = np.empty(len(s))
    for k in range(len(s)):
        lo = max(s[k] - W, 0)
        out[k] = a[lo:s[k]].max() if s[k] > lo else 0.0
    return out


def signals(mk, p, start, end):
    """-> decision times (unix s) and directions, decisions in [start - 1 day, end)."""
    lo = max(bc.ts_of(start) - 86400 - mk.t0, 3601)
    hi = bc.ts_of(end) - mk.t0
    s, d = _bursts(mk.c, mk.vol, p["W"], p["X"], p["refr"], lo, hi)
    if len(s) == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    # largest aggressive print in the burst direction over the last 60 s vs the largest of the last hour (seconds < s)
    mb = mk.raw["mb"].astype(np.float64)
    ms = mk.raw["ms"].astype(np.float64)
    b60 = np.where(d > 0, _rmax(mb, s, 60), _rmax(ms, s, 60))
    h = _rmax(np.maximum(mb, ms), s, 3600)
    rel = b60 / np.maximum(h, 1e-9)
    # open-interest change of the 5-min bucket holding second s-1, known at bucket start + 360 s
    m = mk.metrics
    mts = m.ts.to_numpy(np.int64)
    oi = m.sum_open_interest.to_numpy(float)
    doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
    doi[~np.r_[False, np.diff(mts) == 300]] = np.nan
    known = m.known_ts.to_numpy(np.int64)
    ct = ((s - 1 + mk.t0) // 300) * 300
    k = np.clip(np.searchsorted(mts, ct), 0, max(len(mts) - 1, 0))
    has = (len(mts) > 0) & (mts[k] == ct)
    d0 = np.where(has, doi[k], np.nan)
    sig = np.where(has, known[k], 0)                     # decision when that bucket becomes known (ct + 360)
    ok = has & (d0 >= p["oi_up"]) & (rel > p["big_rel"]) & (sig > s + mk.t0) & (sig < bc.ts_of(end))
    return sig[ok].astype(np.int64), d[ok].astype(np.int64)


def backtest(params, data_dir, start, end, stress=False):
    p = params
    mk = bc.Market(data_dir, str((pd.Timestamp(start) - pd.Timedelta(days=32)).date()), end)
    sig, d = signals(mk, p, start, end)
    cols = ["sig_ts", "dir", "entry_ts", "exit_ts", "r", "sd", "entry_px"]
    if len(sig) == 0:
        return pd.DataFrame(columns=cols)
    vol = mk.vol[sig - mk.t0]
    t = bc.trades(mk, sig, d, stop_dist=p["stop"] * vol, tp_r=p.get("tp", np.nan), hold=p["hold"],
                  be_at=p.get("be", np.nan), trail=p.get("trail", np.nan), stress=stress)
    a, b = bc.ts_of(start), bc.ts_of(end)
    t = t[(t.entry_ts >= a) & (t.entry_ts < b)]
    return t[cols].sort_values(["entry_ts", "sig_ts"]).reset_index(drop=True)
