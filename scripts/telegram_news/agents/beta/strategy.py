"""beta: gold "news-shock momentum" bot (FinancialJuice / Walter Bloomberg posts).

Idea: a post that lands while gold has just jumped hard (|30-second move| >= 3 sigma of the pre-post 1-s volatility),
with a burst of quotes and Nasdaq also moving hard in the same seconds, marks a real cross-asset news shock.  Gold
tends to keep going in the direction of that first move for the next hour(s).  We join it (pullback limit or market
order), with a wide stop (4.5 x the 1-minute volatility), no target, and a time exit after up to 4 hours.

All prices, fills, exits and account figures come from common.py.  Only bars of seconds before the decision second are
used for the signal (decision second = post + LAT + delay); the decision second's first price is the fill.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import common as C  # noqa: E402

BASE = dict(inst='gold', other='nasdaq', L=30, z=3.0, burst=2.0, confirm=2.0, macro=True, delay=0,
            sda=4.5, tp=None, hold=14400, be=None, trail=None)
CANDIDATES = {
    # pullback limit: buy (sell) limit 0.5 x 1-min vol below (above) the last mid, live 10 min
    'gold_shock_pullback': dict(BASE, entry='limit', k=0.5, expire=600),
    # same, but the stop trails 3 R behind the best price from the start
    'gold_shock_pullback_trail': dict(BASE, entry='limit', k=0.5, expire=600, trail=3.0),
    # simplest form: market order at post + 2 s
    'gold_shock_market': dict(BASE, entry='market'),
}

BASEW = 900          # baseline: 900 bars ending 60 s before the post
_CACHE: dict = {}


class _Series:
    """derived per-instrument series built from common.load_ticks (cached)."""

    def __init__(self, tk):
        self.tk = tk
        t = tk['t']
        self.t = t
        self.mid = (tk['bid_last'] + tk['ask_last']) / 2
        dm = np.r_[0.0, np.diff(self.mid)]
        dm[1:][np.diff(t) >= C.GAP] = 0.0
        self.cs2 = np.cumsum(dm * dm)
        self.csn = np.cumsum(tk['n'].astype(np.float64))
        self.css = np.cumsum(tk['ask_last'] - tk['bid_last'])
        self.gaps = np.flatnonzero(np.diff(t) >= C.GAP)

    def before(self, ts):
        """index of the last bar with t < ts"""
        return np.searchsorted(self.t, ts) - 1

    def bar_at(self, ts):
        i = np.searchsorted(self.t, ts)
        i2 = np.minimum(i, len(self.t) - 1)
        return np.where((i < len(self.t)) & (self.t[i2] - ts <= 10), i2, -1)


def _series(inst, data_dir):
    key = (inst, os.path.abspath(data_dir))
    if key not in _CACHE:
        _CACHE[key] = _Series(C.load_ticks(inst, data_dir))
    return _CACHE[key]


def _events(data_dir):
    p = C.load_posts(data_dir)
    macro = p.text.str.contains('$MACRO', regex=False)
    g = pd.DataFrame(dict(ts=p.ts, macro=macro)).groupby('ts')
    return pd.DataFrame(dict(macro=g.macro.any())).reset_index()


def _features(S, ts, L, delay):
    """features known before the decision second ts + LAT + delay (vectorised over posts)."""
    kP = np.maximum(S.before(ts - 60), BASEW)
    sig = np.sqrt((S.cs2[kP] - S.cs2[kP - BASEW]) / BASEW)
    nbase = (S.csn[kP] - S.csn[kP - BASEW]) / BASEW
    spbase = (S.css[kP] - S.css[kP - BASEW]) / BASEW
    sig = np.maximum(sig, 0.05 * spbase)
    tspan = S.t[kP] - S.t[kP - BASEW]
    kpost = S.before(ts)
    kD = S.before(ts + C.LAT + delay)
    ref = S.mid[S.before(ts - L)]
    pnow = S.mid[kD]
    z = (pnow - ref) / (sig * np.sqrt(L + 1 + C.LAT + delay))
    burst = (S.csn[kD] - S.csn[kpost]) / np.maximum(kD - kpost, 1) / np.maximum(nbase, 1e-9)
    gi = np.searchsorted(S.gaps, kpost) - 1                      # last pause before the post
    open_s = ts - S.t[np.where(gi >= 0, S.gaps[np.maximum(gi, 0)] + 1, 0)]
    # time of day of the last pause start (the daily break) -> skip posts in the hour before it
    last_pause_tod = np.where(gi >= 0, S.t[S.gaps[np.maximum(gi, 0)]] % 86400, -10**6)
    tod = ts % 86400
    before_break = ((last_pause_tod - tod) % 86400) < 3600
    return dict(sig=sig, s60=sig * np.sqrt(60), z=z, burst=burst, tspan=tspan, open_s=open_s, kD=kD,
                before_break=before_break, pnow=pnow)


def signals(params, data_dir, start_ts, end_ts):
    """posts that qualify, with direction and stop distance: DataFrame(post_ts, dir, s60, ref_mid)"""
    ev = _events(data_dir)
    ev = ev[(ev.ts >= start_ts - 4 * 3600) & (ev.ts < end_ts)].reset_index(drop=True)
    ts = ev.ts.to_numpy()
    S = _series(params['inst'], data_dir)
    So = _series(params['other'], data_dir)
    f = _features(S, ts, params['L'], params['delay'])
    fo = _features(So, ts, params['L'], params['delay'])
    ok = (f['tspan'] < 1500) & (f['open_s'] > 1200) & ~f['before_break'] & (S.bar_at(ts + C.LAT + params['delay']) >= 0)
    ok &= np.abs(f['z']) >= params['z']
    if params.get('burst'):
        ok &= f['burst'] >= params['burst']
    if params.get('confirm'):
        ok &= np.abs(fo['z']) >= params['confirm']
    if not params.get('macro', True):
        ok &= ~ev.macro.to_numpy()
    idx = np.flatnonzero(ok)
    return pd.DataFrame(dict(post_ts=ts[idx], dir=np.sign(f['z'][idx]).astype(int), s60=f['s60'][idx],
                             mid=f['pnow'][idx]))


def backtest(params, data_dir, start, end, stress=False):
    a = int(pd.Timestamp(start, tz='UTC').timestamp())
    b = int(pd.Timestamp(end, tz='UTC').timestamp())
    sg = signals(params, data_dir, a, b)
    tk = C.load_ticks(params['inst'], data_dir)
    lat = C.LAT_STRESS if stress else C.LAT
    rows = []
    for x in sg.itertuples(index=False):
        d = int(x.dir)
        if params['entry'] == 'market':
            e = C.market_entry(tk, int(x.post_ts), d, delay=params['delay'], stress=stress)
            if e is None:
                continue
            j, fill = e
        else:
            i0 = C.bar_at(tk, int(x.post_ts) + lat + params['delay'])
            if i0 is None:
                continue
            px = float(x.mid) - d * params['k'] * float(x.s60)
            pe = C.pending_entry(tk, i0, [('limit', d, px)], params['expire'], stress=stress)
            if pe is None:
                continue
            j, legs = pe
            fill = legs[0][1]
        k, r, sd = C.exit_trade(tk, j, fill, d, params['sda'] * float(x.s60), tp_r=params['tp'],
                                max_hold_s=params['hold'], be_at_r=params['be'], trail_r=params['trail'], stress=stress)
        entry_ts = int(tk['t'][j])
        if not (a <= entry_ts < b):
            continue
        rows.append(dict(inst=params['inst'], post_ts=int(x.post_ts), entry_ts=entry_ts,
                         exit_ts=int(tk['t'][min(k, len(tk['t']) - 1)]), dir=d, r=r, sd=sd))
    cols = ['inst', 'post_ts', 'entry_ts', 'exit_ts', 'dir', 'r', 'sd']
    return pd.DataFrame(rows, columns=cols)


if __name__ == '__main__':
    D = sys.argv[1] if len(sys.argv) > 1 else '/home/user/news_lab_data'
    for nm, p in CANDIDATES.items():
        tr = backtest(p, D, '2026-01-01', '2026-07-01')
        print(nm, C.metrics(tr, '2026-01-01', '2026-07-01'))
