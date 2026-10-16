"""Deep search: session-restricted entries x stop rules x exit rules.

Entry generators return long/short event arrays plus an optional
structural stop distance.  Every entry is combined with several stop rules
(structure, 1.5x ATR, 3x ATR - never tighter than `floor`) and exit rules
(fixed R:R targets, ATR trailing stop, close at session end, break-even
variants).  Signals are read at a bar's close and executed at the next open;
inside a bar the stop is assumed to fill before the target (pessimistic);
longs pay the spread on entry, shorts on exit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from . import sessions as S
from . import trend_rider_v2 as v2
from .engine import njit

AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


# ------------------------------------------------------------------ engine
@njit(cache=True)
def run_engine(o, h, l, c, sig, sl, tp, trail, xout, max_bars, cost, be_trigger, be_buffer):
    n = len(o)
    t_in = np.zeros(n, np.int64)
    t_out = np.zeros(n, np.int64)
    t_dir = np.zeros(n, np.int64)
    t_r = np.zeros(n)
    nt = 0
    pos = 0
    entry = risk = stop = target = tdist = best = 0.0
    held = 0
    ent_i = 0
    be_done = False
    pend = False
    for i in range(1, n):
        if pos != 0 and pend:
            px = o[i] if pos == 1 else o[i] + cost
            t_in[nt] = ent_i; t_out[nt] = i; t_dir[nt] = pos; t_r[nt] = pos * (px - entry) / risk; nt += 1
            pos = 0
            pend = False
        if pos == 0 and sig[i - 1] != 0 and sl[i - 1] > 0:
            pos = sig[i - 1]
            risk = sl[i - 1]
            entry = o[i] + cost if pos == 1 else o[i]
            stop = entry - pos * risk
            target = entry + pos * tp[i - 1] if tp[i - 1] > 0 else 0.0
            tdist = trail[i - 1]
            best = entry
            held = 0
            ent_i = i
            be_done = False
        if pos == 0:
            continue
        held += 1
        bo = o[i] if pos == 1 else o[i] + cost
        bh = h[i] if pos == 1 else h[i] + cost
        bl = l[i] if pos == 1 else l[i] + cost
        done = False
        px = 0.0
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
        cc = c[i] if pos == 1 else c[i] + cost
        if tdist > 0:                                   # chandelier trail on closes
            if pos == 1:
                best = max(best, cc)
                stop = max(stop, best - tdist)
            else:
                best = min(best, cc)
                stop = min(stop, best + tdist)
        if be_trigger > 0 and not be_done:
            if (pos == 1 and bh >= entry + be_trigger * risk) or (pos == -1 and bl <= entry - be_trigger * risk):
                nb = entry + pos * be_buffer * risk
                stop = max(stop, nb) if pos == 1 else min(stop, nb)
                be_done = True
        if xout[i] or (max_bars > 0 and held >= max_bars):
            pend = True
    return t_in[:nt], t_out[:nt], t_dir[:nt], t_r[:nt]


# ------------------------------------------------------------------ helpers
def resample(df, tf):
    return df if tf == "1min" else df.resample(tf).agg(AGG).dropna()


def in_session(df, ses):
    mod, day, s0, s1 = S.clock(df, ses)
    return (mod >= s0) & (mod < s1), mod, day, s0, s1


def first_per_day(ev, day):
    return ev & (pd.Series(ev.astype(int)).groupby(day).cumsum().to_numpy() == 1)


def htf_trend(df, bars_per_hour, n=50):
    """+1/-1 from an EMA of ~n hours on the current bars (slope + side)."""
    e = ind.ema(df.close, n * bars_per_hour)
    up = (df.close > e) & (e > e.shift(bars_per_hour))
    dn = (df.close < e) & (e < e.shift(bars_per_hour))
    return np.where(up, 1, np.where(dn, -1, 0))


# ------------------------------------------------------------------ entries
# each returns (long, short, struct_long, struct_short)  - struct may be None

def e_orb(df, ses, rm):
    ins, mod, day, s0, s1 = in_session(df, ses)
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    rng = (mod >= s0) & (mod < s0 + rm)
    ent = ins & (mod >= s0 + rm) & (mod < min(s0 + rm + 180, s1))
    hi = pd.Series(np.where(rng, h, np.nan)).groupby(day).transform("max").to_numpy()
    lo = pd.Series(np.where(rng, l, np.nan)).groupby(day).transform("min").to_numpy()
    L, Sh = ent & (c > hi), ent & (c < lo)
    f = first_per_day(L | Sh, day)
    return L & f, Sh & f, c - lo, hi - c


def e_asian_break(df, ses):
    """Range 00:00-08:00 London time; first break during `ses` (london/newyork)."""
    ins, mod, day, s0, s1 = in_session(df, ses)
    lmod, lday, ls0, _ = S.clock(df, "london")
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    rng = lmod < ls0
    hi = pd.Series(np.where(rng, h, np.nan)).groupby(lday).transform("max").to_numpy()
    lo = pd.Series(np.where(rng, l, np.nan)).groupby(lday).transform("min").to_numpy()
    ent = ins & (lmod >= ls0)
    L, Sh = ent & (c > hi), ent & (c < lo)
    f = first_per_day(L | Sh, lday)
    return L & f, Sh & f, c - lo, hi - c


def e_pdhl(df, ses):
    """Break of the previous UTC day's high/low inside the session."""
    ins, mod, day, s0, s1 = in_session(df, ses)
    d = df.index.normalize()
    daily = df.groupby(d).agg(h=("high", "max"), l=("low", "min"))
    pdh = pd.Series(d).map(daily.h.shift()).to_numpy()
    pdl = pd.Series(d).map(daily.l.shift()).to_numpy()
    c = df.close.to_numpy()
    L, Sh = ins & (c > pdh), ins & (c < pdl)
    f = first_per_day(L | Sh, day)
    return L & f, Sh & f, None, None


def e_donchian_trend(df, ses, n, bph):
    ins, *_ = in_session(df, ses)
    c, h, l = df.close, df.high, df.low
    up, dn = h.rolling(n).max().shift(), l.rolling(n).min().shift()
    tr = htf_trend(df, bph)
    L = ins & (c > up).to_numpy() & (c.shift() <= up.shift()).to_numpy() & (tr == 1)
    Sh = ins & (c < dn).to_numpy() & (c.shift() >= dn.shift()).to_numpy() & (tr == -1)
    return L, Sh, (c - l.rolling(n).min()).to_numpy(), (h.rolling(n).max() - c).to_numpy()


def e_pullback(df, ses):
    ins, *_ = in_session(df, ses)
    c, h, l = df.close, df.high, df.low
    f, m, s = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    L = (f > m) & (m > s) & (l.shift() <= f.shift()) & (c > f) & (c > h.shift())
    Sh = (f < m) & (m < s) & (h.shift() >= f.shift()) & (c < f) & (c < l.shift())
    return ins & L.to_numpy(), ins & Sh.to_numpy(), (c - l.rolling(10).min()).to_numpy(), (h.rolling(10).max() - c).to_numpy()


def e_v2(df, ses, min_stop):
    ins, *_ = in_session(df, ses)
    s = v2.signals(df, v2.Params(min_stop_price=min_stop))
    sig, d = s.signal.to_numpy(), s.dist.to_numpy()
    return ins & (sig == 1), ins & (sig == -1), d, d


def e_rsi2(df, ses):
    from .hwr import rsi
    ins, *_ = in_session(df, ses)
    c = df.close
    r, e = rsi(c, 2), ind.ema(c, 200)
    return ins & ((c > e) & (r < 10)).to_numpy(), ins & ((c < e) & (r > 90)).to_numpy(), None, None


def e_drive(df, ses, minutes, follow):
    ins, mod, day, s0, s1 = in_session(df, ses)
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    opx = pd.Series(np.where(mod == s0, o, np.nan)).groupby(day).transform("max").to_numpy()
    rng = (mod >= s0) & (mod < s0 + minutes)
    hi = pd.Series(np.where(rng, h, np.nan)).groupby(day).transform("max").to_numpy()
    lo = pd.Series(np.where(rng, l, np.nan)).groupby(day).transform("min").to_numpy()
    at = mod == s0 + minutes - 1
    up, dn = at & (c - opx > 0.4 * (hi - lo)), at & (opx - c > 0.4 * (hi - lo))
    if follow:
        return up, dn, c - lo, hi - c
    return dn, up, c - lo, hi - c


def e_runfade(df, ses, run_len=4, mm=2.0):
    ins, *_ = in_session(df, ses)
    o, c = df.open, df.close
    col = np.sign((c - o).to_numpy())
    runl = np.zeros(len(col), np.int64)
    for i in range(len(col)):
        if col[i] != 0:
            runl[i] = runl[i - 1] + col[i] if i and np.sign(runl[i - 1]) == col[i] else col[i]
    a = ind.atr(df, 14).to_numpy()
    strong = np.abs((c - o.shift(run_len - 1)).to_numpy()) >= mm * a
    return ins & (runl == -run_len) & strong, ins & (runl == run_len) & strong, None, None


SES = ("asian", "london", "newyork")


def entries(market, min_stop):
    """(name, timeframe, fn, kwargs)"""
    out = []
    for ses in SES:
        for rm in (5, 15, 30, 60):
            out.append((f"ORB {rm}m", "1min", e_orb, dict(ses=ses, rm=rm)))
        out.append(("Prev-day high/low break", "5min", e_pdhl, dict(ses=ses)))
        out.append(("Donchian20 + H1 trend (M5)", "5min", e_donchian_trend, dict(ses=ses, n=20, bph=12)))
        out.append(("Donchian20 + H1 trend (M15)", "15min", e_donchian_trend, dict(ses=ses, n=20, bph=4)))
        out.append(("EMA pullback (M5)", "5min", e_pullback, dict(ses=ses)))
        out.append(("EMA pullback (M15)", "15min", e_pullback, dict(ses=ses)))
        out.append(("Trend v2 M5->M1 pullback", "1min", e_v2, dict(ses=ses, min_stop=min_stop)))
        out.append(("RSI2 reversion (M5)", "5min", e_rsi2, dict(ses=ses)))
        out.append(("RSI2 reversion (M15)", "15min", e_rsi2, dict(ses=ses)))
        for m in (15, 30):
            out.append((f"Opening drive follow {m}m", "1min", e_drive, dict(ses=ses, minutes=m, follow=True)))
            out.append((f"Opening drive fade {m}m", "1min", e_drive, dict(ses=ses, minutes=m, follow=False)))
        out.append(("Run fade (M15)", "15min", e_runfade, dict(ses=ses)))
    for ses in ("london", "newyork"):
        out.append(("Asian-range break", "1min", e_asian_break, dict(ses=ses)))
    return out


STOPS = ("struct", 1.5, 3.0)
EXITS = [("RR 1", dict(rr=1.0)), ("RR 1.5", dict(rr=1.5)), ("RR 2", dict(rr=2.0)), ("RR 3", dict(rr=3.0)),
         ("RR 5", dict(rr=5.0)), ("Trail 2 ATR", dict(trail=2.0)), ("Trail 4 ATR", dict(trail=4.0)),
         ("Session close", dict(close=True)), ("RR 2 + BE", dict(rr=2.0, be=1.0)), ("RR 3 + BE", dict(rr=3.0, be=1.0))]
