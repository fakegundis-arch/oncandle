"""High-win-rate strategy research: a generic bracket engine plus many
strategy families (mean reversion, small-target trend pullbacks, failed
breakouts, run fades, ...).

Each family returns a Setup: per-bar entry signal (+1/-1/0, acted on at the
next bar's open), stop distance, target distance (0 = no fixed target),
condition exits (evaluated at the close, executed at the next open) and a
maximum holding time in bars.

Fill model as elsewhere: longs pay the spread on entry, shorts on exit;
stop checked before target inside a bar (pessimistic); R = P/L / stop
distance; a trade is a WIN only if it made money after costs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import njit


@dataclass
class Setup:
    sig: np.ndarray
    sl: np.ndarray
    tp: np.ndarray
    xl: np.ndarray
    xs: np.ndarray
    max_bars: int = 0
    be_trigger: float = 0.0
    be_buffer: float = 0.0


@njit(cache=True)
def _run(o, h, l, c, sig, sl, tp, xl, xs, max_bars, cost, be_trigger, be_buffer):
    n = len(o)
    t_in = np.zeros(n, np.int64)
    t_out = np.zeros(n, np.int64)
    t_dir = np.zeros(n, np.int64)
    t_r = np.zeros(n)
    nt = 0
    pos = 0
    entry = 0.0
    risk = 0.0
    stop = 0.0
    target = 0.0
    held = 0
    ent_i = 0
    be_done = False
    pend_exit = False
    for i in range(1, n):
        if pos != 0 and pend_exit:
            px = o[i] if pos == 1 else o[i] + cost
            t_in[nt] = ent_i; t_out[nt] = i; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / risk; nt += 1
            pos = 0
            pend_exit = False
        if pos == 0 and sig[i - 1] != 0 and sl[i - 1] > 0:
            pos = sig[i - 1]
            risk = sl[i - 1]
            entry = o[i] + cost if pos == 1 else o[i]
            stop = entry - pos * risk
            target = entry + pos * tp[i - 1] if tp[i - 1] > 0 else 0.0
            held = 0
            ent_i = i
            be_done = False
        if pos == 0:
            continue
        held += 1
        bo = o[i] if pos == 1 else o[i] + cost
        bh = h[i] if pos == 1 else h[i] + cost
        bl = l[i] if pos == 1 else l[i] + cost
        px = 0.0
        done = False
        if pos == 1:
            if bl <= stop:
                px = min(bo, stop); done = True
            elif target > 0 and bh >= target:
                px = max(bo, target); done = True
        else:
            if bh >= stop:
                px = max(bo, stop); done = True
            elif target > 0 and bl <= target:
                px = min(bo, target); done = True
        if done:
            t_in[nt] = ent_i; t_out[nt] = i; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / risk; nt += 1
            pos = 0
            continue
        if be_trigger > 0 and not be_done:
            if (pos == 1 and bh >= entry + be_trigger * risk) or (pos == -1 and bl <= entry - be_trigger * risk):
                stop = entry + pos * be_buffer * risk
                be_done = True
        if (pos == 1 and xl[i]) or (pos == -1 and xs[i]) or (max_bars > 0 and held >= max_bars):
            pend_exit = True
    return t_in[:nt], t_out[:nt], t_dir[:nt], t_r[:nt]


def run(df: pd.DataFrame, s: Setup, cost: float) -> pd.DataFrame:
    f = lambda a: np.nan_to_num(np.asarray(a, np.float64))
    b = lambda a: np.asarray(a, np.bool_)
    ti, to, td, tr = _run(f(df.open), f(df.high), f(df.low), f(df.close),
                          np.asarray(s.sig, np.int64), f(s.sl), f(s.tp), b(s.xl), b(s.xs),
                          int(s.max_bars), float(cost), float(s.be_trigger), float(s.be_buffer))
    return pd.DataFrame({"entry_time": df.index[ti], "exit_time": df.index[to], "dir": td, "r": tr})


# ---------------------------------------------------------------- helpers
def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = ind.rma(d.clip(lower=0), n)
    dn = ind.rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _arr(x):
    return np.nan_to_num(np.asarray(x, np.float64))


def _sig(long_, short_):
    return np.where(np.asarray(long_.fillna(False), bool), 1,
                    np.where(np.asarray(short_.fillna(False), bool), -1, 0))


def _no(df):
    return np.zeros(len(df), bool)


# ---------------------------------------------------------------- families
def rsi_reversion(df, rsi_n=2, lo=10, trend=200, sl_atr=3.0, exit_ma=5, max_bars=20, both=True):
    """Connors-style: buy a sharp dip inside an uptrend, sell when price
    closes back above a short MA. No fixed target."""
    c = df.close
    r, a, t, m = rsi(c, rsi_n), ind.atr(df, 14), ind.ema(c, trend), ind.sma(c, exit_ma)
    long_ = (c > t) & (r < lo)
    short_ = ((c < t) & (r > 100 - lo)) if both else pd.Series(False, df.index)
    return Setup(_sig(long_, short_), _arr(sl_atr * a), np.zeros(len(df)),
                 np.asarray((c > m).fillna(False)), np.asarray((c < m).fillna(False)), max_bars)


def bb_reversion(df, n=20, k=2.0, trend=200, sl_atr=3.0, max_bars=30):
    """Close outside the Bollinger band against the trend-side, exit at mid band."""
    c = df.close
    mid, up, dn = ind.bollinger(c, n, k)
    a, t = ind.atr(df, 14), ind.ema(c, trend)
    long_ = (c < dn) & (c > t)
    short_ = (c > up) & (c < t)
    return Setup(_sig(long_, short_), _arr(sl_atr * a), np.zeros(len(df)),
                 np.asarray((c > mid).fillna(False)), np.asarray((c < mid).fillna(False)), max_bars)


def zscore_reversion(df, n=50, z=2.0, sl_atr=3.0, max_bars=30, trend=0):
    """Fade a stretch of z standard deviations from the mean; exit back at the mean."""
    c = df.close
    mu, sd = c.rolling(n).mean(), c.rolling(n).std()
    zz = (c - mu) / sd
    a = ind.atr(df, 14)
    long_, short_ = zz < -z, zz > z
    if trend:
        e = ind.ema(c, trend)
        long_ &= c > e
        short_ &= c < e
    return Setup(_sig(long_, short_), _arr(sl_atr * a), np.zeros(len(df)),
                 np.asarray((zz > 0).fillna(False)), np.asarray((zz < 0).fillna(False)), max_bars)


def pullback_small_target(df, fast=20, mid=50, slow=200, tp_atr=1.0, sl_atr=2.0, max_bars=30):
    """Trend pullback (EMA stack + pullback to EMA fast + resume) with a
    target smaller than the stop."""
    c, h, l = df.close, df.high, df.low
    f, m, s = ind.ema(c, fast), ind.ema(c, mid), ind.ema(c, slow)
    a = ind.atr(df, 14)
    long_ = (f > m) & (m > s) & (l.shift() <= f.shift()) & (c > f) & (c > h.shift())
    short_ = (f < m) & (m < s) & (h.shift() >= f.shift()) & (c < f) & (c < l.shift())
    return Setup(_sig(long_, short_), _arr(sl_atr * a), _arr(tp_atr * a), _no(df), _no(df), max_bars)


def failed_breakout(df, n=20, tp_frac=0.5, sl_atr=1.5, max_bars=30):
    """'Turtle soup': price pokes beyond the n-bar extreme and closes back
    inside -> fade it, target part of the way back across the channel."""
    c, h, l = df.close, df.high, df.low
    hi, lo = h.rolling(n).max().shift(), l.rolling(n).min().shift()
    a = ind.atr(df, 14)
    long_ = (l < lo) & (c > lo)
    short_ = (h > hi) & (c < hi)
    width = (hi - lo)
    sl_long = (c - l).clip(lower=0) + 0.2 * a
    sl_short = (h - c).clip(lower=0) + 0.2 * a
    sig = _sig(long_, short_)
    sl = np.where(sig == 1, _arr(sl_long), _arr(sl_short))
    sl = np.maximum(sl, _arr(sl_atr * a) * 0.5)
    return Setup(sig, sl, _arr(tp_frac * width), _no(df), _no(df), max_bars)


def run_fade(df, run_len=4, min_move_atr=1.5, tp_atr=0.75, sl_atr=2.0, max_bars=20):
    """Fade N same-colour candles that moved >= min_move_atr x ATR (on BTC M1
    the follow-through version lost but the fade had a raw edge)."""
    o, c = df.open, df.close
    col = np.sign(c - o).to_numpy()
    runl = np.zeros(len(col), np.int64)
    for i in range(len(col)):
        if col[i] == 0:
            continue
        runl[i] = runl[i - 1] + col[i] if i and np.sign(runl[i - 1]) == col[i] else col[i]
    runl = pd.Series(runl, df.index)
    a = ind.atr(df, 14)
    strong = (c - o.shift(run_len - 1)).abs() >= min_move_atr * a
    long_ = (runl == -run_len) & strong
    short_ = (runl == run_len) & strong
    return Setup(_sig(long_, short_), _arr(sl_atr * a), _arr(tp_atr * a), _no(df), _no(df), max_bars)


def ema_snapback(df, ema_n=20, dist_atr=2.5, trend=200, sl_atr=3.0, max_bars=20):
    """Price stretched dist_atr x ATR away from EMA(n) in the trend's favour
    direction's pullback -> bet on a snap back to the EMA."""
    c = df.close
    e, t, a = ind.ema(c, ema_n), ind.ema(c, trend), ind.atr(df, 14)
    long_ = (c < e - dist_atr * a) & (c > t)
    short_ = (c > e + dist_atr * a) & (c < t)
    return Setup(_sig(long_, short_), _arr(sl_atr * a), np.zeros(len(df)),
                 np.asarray((c >= e).fillna(False)), np.asarray((c <= e).fillna(False)), max_bars)


FAMILIES = {
    "RSI(2) dip-buy in trend": (rsi_reversion, [
        dict(lo=lo, sl_atr=s, exit_ma=m, max_bars=mb)
        for lo in (5, 10, 20) for s in (2.0, 3.0, 5.0) for m in (3, 5) for mb in (10, 30)]),
    "Bollinger fade (with trend)": (bb_reversion, [
        dict(n=n, k=k, sl_atr=s, max_bars=mb)
        for n in (20, 50) for k in (2.0, 2.5, 3.0) for s in (2.0, 3.0, 5.0) for mb in (20, 60)]),
    "Z-score reversion": (zscore_reversion, [
        dict(n=n, z=z, sl_atr=s, trend=t, max_bars=mb)
        for n in (20, 50, 100) for z in (2.0, 2.5, 3.0) for s in (3.0, 5.0) for t in (0, 200) for mb in (30,)]),
    "Trend pullback, small target": (pullback_small_target, [
        dict(tp_atr=tp, sl_atr=s, max_bars=mb)
        for tp in (0.5, 0.75, 1.0) for s in (1.5, 2.0, 3.0) for mb in (20, 60)]),
    "Failed breakout (turtle soup)": (failed_breakout, [
        dict(n=n, tp_frac=f, max_bars=mb)
        for n in (20, 50) for f in (0.25, 0.5) for mb in (20, 60)]),
    "Fade candle runs": (run_fade, [
        dict(run_len=rl, min_move_atr=mm, tp_atr=tp, sl_atr=s)
        for rl in (4, 5, 6) for mm in (1.5, 2.5) for tp in (0.5, 1.0) for s in (2.0, 3.0)]),
    "EMA snap-back (with trend)": (ema_snapback, [
        dict(dist_atr=d, sl_atr=s, max_bars=mb)
        for d in (2.0, 3.0, 4.0) for s in (2.0, 3.0, 5.0) for mb in (10, 30)]),
}
