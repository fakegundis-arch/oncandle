"""Trend-following strategy library.

Each strategy is a function `f(df, **params) -> dict(le, se, lx, sx)` of
boolean Series evaluated at bar close:
    le / se : open long / short (also reverses an opposite position)
    lx / sx : close long / short
Entries are *events* (the bar a condition becomes true), so after a stop-out
the system waits for a fresh signal instead of re-entering immediately.

`STRATEGIES` maps a name to (function, signal-param grid, risk grid).  Grids
are kept deliberately small (~12-24 combinations) to limit curve fitting.
"""
from __future__ import annotations

import itertools

import pandas as pd

from . import indicators as ind


def _cross_up(a, b):
    return (a > b) & (a.shift() <= b.shift())


def _cross_dn(a, b):
    return (a < b) & (a.shift() >= b.shift())


def _onset(cond):
    cond = cond.fillna(False).astype(bool)
    return cond & ~cond.shift(fill_value=False)


def _sig(le, se, lx=None, sx=None):
    f = lambda s: s.fillna(False).astype(bool) if s is not None else None
    le, se = f(le), f(se)
    return {"le": le, "se": se,
            "lx": f(lx) if lx is not None else pd.Series(False, le.index),
            "sx": f(sx) if sx is not None else pd.Series(False, le.index)}


# 1 ─ Moving-average crossover (stop-and-reverse)
def ema_cross(df, fast=20, slow=50):
    f, s = ind.ema(df.close, fast), ind.ema(df.close, slow)
    return _sig(_cross_up(f, s), _cross_dn(f, s))


# 2 ─ Donchian channel breakout (Turtle style)
def donchian(df, entry=20, exit=10):
    up, dn = ind.donchian(df, entry)
    xu, xd = ind.donchian(df, exit)
    return _sig(_cross_up(df.close, up), _cross_dn(df.close, dn),
                df.close < xd, df.close > xu)


# 3 ─ Supertrend flip
def supertrend(df, period=10, mult=3.0):
    d = ind.supertrend(df, period, mult)
    return _sig((d == 1) & (d.shift() == -1), (d == -1) & (d.shift() == 1))


# 4 ─ MACD signal-line cross, filtered by a long EMA
def macd_trend(df, fast=12, slow=26, signal=9, trend=200):
    m, s = ind.macd(df.close, fast, slow, signal)
    t = ind.ema(df.close, trend)
    return _sig(_cross_up(m, s) & (df.close > t), _cross_dn(m, s) & (df.close < t),
                _cross_dn(m, s), _cross_up(m, s))


# 5 ─ ADX / DMI directional cross with trend-strength filter
def adx_dmi(df, period=14, threshold=25):
    p, m, a = ind.adx(df, period)
    return _sig(_cross_up(p, m) & (a > threshold), _cross_dn(p, m) & (a > threshold),
                _cross_dn(p, m), _cross_up(p, m))


# 6 ─ Keltner channel breakout, exit at the mid-line
def keltner(df, period=20, k=2.0):
    mid = ind.ema(df.close, period)
    a = ind.atr(df, period)
    up, dn = mid + k * a, mid - k * a
    return _sig(_cross_up(df.close, up), _cross_dn(df.close, dn),
                df.close < mid, df.close > mid)


# 7 ─ Bollinger band breakout, exit at the mid-line
def bollinger(df, period=20, k=2.0):
    mid, up, dn = ind.bollinger(df.close, period, k)
    return _sig(_cross_up(df.close, up), _cross_dn(df.close, dn),
                df.close < mid, df.close > mid)


# 8 ─ Triple EMA alignment
def triple_ema(df, fast=10, mid=30, slow=100):
    f, m, s = (ind.ema(df.close, n) for n in (fast, mid, slow))
    return _sig(_onset((f > m) & (m > s)), _onset((f < m) & (m < s)), f < m, f > m)


# 9 ─ Ichimoku cloud breakout with TK confirmation
def ichimoku(df, tenkan=9, kijun=26, senkou=52):
    t, k, a, b = ind.ichimoku(df, tenkan, kijun, senkou)
    top = pd.concat([a, b], axis=1).max(axis=1)
    bot = pd.concat([a, b], axis=1).min(axis=1)
    return _sig(_onset((df.close > top) & (t > k)), _onset((df.close < bot) & (t < k)),
                df.close < k, df.close > k)


# 10 ─ Time-series momentum (rate of change sign)
def tsmom(df, lookback=100):
    roc = df.close / df.close.shift(lookback) - 1
    z = pd.Series(0.0, df.index)
    return _sig(_cross_up(roc, z), _cross_dn(roc, z))


# 11 ─ Parabolic SAR flip with EMA trend filter
def psar_ema(df, step=0.02, trend=200):
    d = ind.psar(df, step, 10 * step)
    t = ind.ema(df.close, trend)
    flip_up, flip_dn = (d == 1) & (d.shift() == -1), (d == -1) & (d.shift() == 1)
    return _sig(flip_up & (df.close > t), flip_dn & (df.close < t), flip_dn, flip_up)


# 12 ─ Kaufman adaptive moving average: price cross with slope confirmation
def kama_trend(df, period=10, fast=2, slow=30):
    k = ind.kama(df.close, period, fast, slow)
    rising, falling = k > k.shift(), k < k.shift()
    return _sig(_cross_up(df.close, k) & rising, _cross_dn(df.close, k) & falling)


def _grid(**kw):
    keys = list(kw)
    return [dict(zip(keys, v)) for v in itertools.product(*kw.values())]


def _pairs(keys, values):
    return [dict(zip(keys, v)) for v in values]


RISK_STOP = _grid(stop_mult=[2.0, 3.0], trail_mult=[0.0])
RISK_STOP_TRAIL = _grid(stop_mult=[2.0, 3.0], trail_mult=[0.0, 3.0])

STRATEGIES = {
    "EMA Crossover":      (ema_cross,  _pairs(["fast", "slow"], [(10, 30), (20, 50), (20, 100), (50, 200)]), RISK_STOP_TRAIL),
    "Donchian Breakout":  (donchian,   _pairs(["entry", "exit"], [(20, 10), (55, 20), (100, 50)]), RISK_STOP_TRAIL),
    "Supertrend":         (supertrend, _grid(period=[10, 20], mult=[2.0, 3.0, 4.0]), RISK_STOP),
    "MACD + EMA Filter":  (macd_trend, [dict(fast=f, slow=s, signal=g, trend=t)
                                        for f, s, g in [(12, 26, 9), (24, 52, 18)] for t in (100, 200)], RISK_STOP_TRAIL),
    "ADX/DMI":            (adx_dmi,    _grid(period=[14, 20], threshold=[20, 25]), RISK_STOP_TRAIL),
    "Keltner Breakout":   (keltner,    _grid(period=[20, 50], k=[1.5, 2.5]), RISK_STOP_TRAIL),
    "Bollinger Breakout": (bollinger,  _grid(period=[20, 50], k=[2.0, 2.5]), RISK_STOP_TRAIL),
    "Triple EMA":         (triple_ema, _pairs(["fast", "mid", "slow"], [(10, 30, 100), (20, 50, 200)]), RISK_STOP_TRAIL),
    "Ichimoku":           (ichimoku,   _pairs(["tenkan", "kijun", "senkou"], [(9, 26, 52), (20, 60, 120)]), RISK_STOP_TRAIL),
    "TS Momentum":        (tsmom,      _grid(lookback=[50, 100, 200, 300]), _grid(stop_mult=[3.0, 4.0], trail_mult=[0.0])),
    "PSAR + EMA":         (psar_ema,   _grid(step=[0.01, 0.02], trend=[100, 200]), RISK_STOP),
    "KAMA Trend":         (kama_trend, _grid(period=[10, 20], slow=[30, 50]), RISK_STOP_TRAIL),
}
