"""Gold MACD lab: signals on `tf` bars, every trade simulated minute by minute on M1.

Baseline (OnCandleTrend.mq5, MACD + EMA filter preset): XAUUSD H4. Long when MACD(12,26,9) crosses above its signal
line with close > EMA(100); short mirrors. Exit at the next bar's open after the opposite MACD cross (a cross in the
other direction that also passes the EMA filter reverses the position). Stop 3 x ATR(14). No target, no trail.

Extensions: other MACD settings / timeframes / trend EMA, zero-line filter, ADX filter, daily-trend filter,
fixed RR target, break-even, ATR trailing stop, exit on EMA cross instead of MACD cross, no reversal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import njit


@dataclass
class P:
    tf: str = "4h"
    fast: int = 12
    slow: int = 26
    signal: int = 9
    trend: int = 100
    zero_line: bool = False     # long only if MACD > 0, short only if MACD < 0
    adx_min: float = 0.0
    d1_trend: int = 0           # >0: require yesterday's close vs EMA(n days) agreement
    stop_atr: float = 3.0
    rr: float = 0.0             # >0: fixed target at rr x stop
    be: float = 0.0             # move stop to +0.1R at +be R
    trail_atr: float = 0.0      # chandelier trail at this x ATR from the best price
    exit_mode: str = "macd"     # "macd" (opposite cross) | "ema" (close through trend EMA) | "none"
    reverse: bool = True
    cost: float = 0.20


_C: dict = {}


def data(root):
    if "m1" not in _C:
        from . import data as D
        _C["m1"] = D.load_csv(root / "data" / "XAUUSD_M1.csv").drop(columns="spread", errors="ignore")
    return _C["m1"]


def bars(m1, tf):
    k = ("b", tf)
    if k not in _C:
        _C[k] = m1.resample(tf).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return _C[k]


def signals(df: pd.DataFrame, p: P):
    c = df.close
    m, s = ind.macd(c, p.fast, p.slow, p.signal)
    up = (m > s) & (m.shift() <= s.shift())
    dn = (m < s) & (m.shift() >= s.shift())
    t = ind.ema(c, p.trend)
    le, se = up & (c > t), dn & (c < t)
    if p.zero_line:
        le &= m > 0
        se &= m < 0
    if p.adx_min > 0:
        adx = ind.adx(df, 14)[2]
        le &= adx >= p.adx_min
        se &= adx >= p.adx_min
    if p.d1_trend > 0:
        day = df.index.normalize()
        dc = c.groupby(day).last()
        de = ind.ema(dc, p.d1_trend)
        upd = pd.Series(day).map(dc.shift() > de.shift()).fillna(False).to_numpy(bool)
        dnd = pd.Series(day).map(dc.shift() < de.shift()).fillna(False).to_numpy(bool)
        le &= upd
        se &= dnd
    if p.exit_mode == "macd":
        lx, sx = dn, up
    elif p.exit_mode == "ema":
        lx, sx = c < t, c > t
    else:
        lx = sx = pd.Series(False, df.index)
    return (le.fillna(False).to_numpy(), se.fillna(False).to_numpy(), lx.fillna(False).to_numpy(),
            sx.fillna(False).to_numpy(), ind.atr(df, 14).to_numpy())


@njit(cache=True)
def _run(o, h, l, c, act, a_le, a_se, a_lx, a_sx, a_atr, stop_atr, rr, be, trail, reverse, cost):
    """act: M1 indices where a new `tf` bar opens (decisions from the previous bar apply there)."""
    n_t = len(act)
    t_in = np.zeros(n_t + 1, np.int64)
    t_out = np.zeros(n_t + 1, np.int64)
    t_dir = np.zeros(n_t + 1, np.int64)
    t_r = np.zeros(n_t + 1)
    nt = 0
    pos = 0
    entry = R = stop = tgt = best = 0.0
    moved = False
    ent_i = 0
    for q in range(1, n_t):
        j0 = act[q]
        j1 = act[q + 1] if q + 1 < n_t else len(o)
        # decisions from bar q-1 (closed) executed at open of bar q
        want = 2
        if pos == 1:
            if a_se[q - 1] and reverse:
                want = -1
            elif a_lx[q - 1] or a_se[q - 1]:
                want = 0
        elif pos == -1:
            if a_le[q - 1] and reverse:
                want = 1
            elif a_sx[q - 1] or a_le[q - 1]:
                want = 0
        else:
            if a_le[q - 1] and not a_se[q - 1]:
                want = 1
            elif a_se[q - 1] and not a_le[q - 1]:
                want = -1
        if want != 2 and want != pos:
            if pos != 0:
                px = o[j0] if pos == 1 else o[j0] + cost
                t_in[nt] = ent_i; t_out[nt] = j0; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / R; nt += 1
                pos = 0
            if want != 0 and a_atr[q - 1] > 0:
                pos = want
                entry = o[j0] + cost if pos == 1 else o[j0]
                R = stop_atr * a_atr[q - 1]
                stop = entry - pos * R
                tgt = entry + pos * rr * R
                best = entry
                moved = False
                ent_i = j0
        # minute-by-minute inside bar q
        if pos != 0:
            for j in range(j0, j1):
                bo = o[j] if pos == 1 else o[j] + cost
                bh = h[j] if pos == 1 else h[j] + cost
                bl = l[j] if pos == 1 else l[j] + cost
                done = False
                px = 0.0
                if pos == 1:
                    if bl <= stop:
                        px = min(bo, stop); done = True
                    elif rr > 0 and bh >= tgt:
                        px = max(bo, tgt); done = True
                    else:
                        best = max(best, bh)
                else:
                    if bh >= stop:
                        px = max(bo, stop); done = True
                    elif rr > 0 and bl <= tgt:
                        px = min(bo, tgt); done = True
                    else:
                        best = min(best, bl)
                if done:
                    t_in[nt] = ent_i; t_out[nt] = j; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / R; nt += 1
                    pos = 0
                    break
                if be > 0 and not moved and pos * (best - entry) >= be * R:
                    stop = entry + pos * 0.1 * R
                    moved = True
                if trail > 0:
                    ts = best - pos * trail * a_atr[q - 1]
                    if (pos == 1 and ts > stop) or (pos == -1 and ts < stop):
                        stop = ts
    if pos != 0:
        px = c[len(c) - 1] if pos == 1 else c[len(c) - 1] + cost
        t_in[nt] = ent_i; t_out[nt] = len(c) - 1; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / R; nt += 1
    return t_in[:nt], t_out[:nt], t_dir[:nt], t_r[:nt]


def backtest(m1: pd.DataFrame, p: P) -> pd.DataFrame:
    df = bars(m1, p.tf)
    le, se, lx, sx, atr = signals(df, p)
    mi = m1.index
    act = mi.searchsorted(df.index)
    o, h, l, c = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    ti, tx, td, tr = _run(o, h, l, c, act.astype(np.int64), le, se, lx, sx, np.nan_to_num(atr), p.stop_atr, p.rr, p.be,
                          p.trail_atr, p.reverse, p.cost)
    return pd.DataFrame({"entry_time": mi[ti], "exit_time": mi[tx], "dir": td, "r": tr})
