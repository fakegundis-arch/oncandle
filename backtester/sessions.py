"""Session-based M1 strategies (Asian / London / New York).

Sessions use the exchange's local clock, so daylight-saving shifts are handled:
    asian  : Tokyo   09:00-15:00 Asia/Tokyo   (00:00-06:00 UTC)
    london : London  08:00-16:30 Europe/London
    newyork: NY      09:30-16:00 America/New_York
New trades are only opened inside the session's entry window.  Every family
returns a hwr.Setup for the generic engine in hwr.py; `flatten=True` closes
any open trade at the session end (at the next bar's open).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import hwr
from . import trend_rider_v2 as v2

SESSIONS = {
    "asian": ("Asia/Tokyo", 9 * 60, 15 * 60),
    "london": ("Europe/London", 8 * 60, 16 * 60 + 30),
    "newyork": ("America/New_York", 9 * 60 + 30, 16 * 60),
}


def clock(df: pd.DataFrame, session: str):
    """Local minute-of-day, local session-day key and in-session mask."""
    tz, s0, s1 = SESSIONS[session]
    loc = df.index.tz_localize("UTC").tz_convert(tz)
    mod = np.asarray(loc.hour * 60 + loc.minute)
    day = np.asarray(loc.year * 10000 + loc.month * 100 + loc.day)   # local calendar day
    return mod, day, s0, s1


def _setup(df, long_, short_, sl_long, sl_short, tp_mult, outside, be=0.0, tp_long=None, tp_short=None):
    sig = np.where(long_, 1, np.where(short_, -1, 0))
    sl = np.where(sig == 1, sl_long, np.where(sig == -1, sl_short, 0.0))
    sl = np.nan_to_num(np.asarray(sl, np.float64))
    if tp_long is not None:
        tp = np.where(sig == 1, tp_long, np.where(sig == -1, tp_short, 0.0))
        tp = np.nan_to_num(np.asarray(tp, np.float64))
    else:
        tp = sl * tp_mult
    sig[sl <= 0] = 0
    out = np.asarray(outside, bool)
    return hwr.Setup(sig.astype(np.int64), sl, tp, out, out, 0, be, 0.1 if be else 0.0)


def _first_per_day(ev: np.ndarray, day: np.ndarray) -> np.ndarray:
    s = pd.Series(ev.astype(int))
    return ev & (s.groupby(day).cumsum().to_numpy() == 1)


def orb(df, session="london", range_min=15, sl_mode="range", tp_mult=2.0, be=0.0, entry_hours=3.0,
        flatten=True, min_sl_frac=0.0):
    """Opening range breakout: first breakout close beyond the first
    `range_min` minutes' high/low, one trade per session."""
    mod, day, s0, s1 = clock(df, session)
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    in_rng = (mod >= s0) & (mod < s0 + range_min)
    in_ent = (mod >= s0 + range_min) & (mod < min(s0 + range_min + entry_hours * 60, s1))
    hi = pd.Series(np.where(in_rng, h, np.nan)).groupby(day).transform("max").to_numpy()
    lo = pd.Series(np.where(in_rng, l, np.nan)).groupby(day).transform("min").to_numpy()
    mid = (hi + lo) / 2
    long_ = in_ent & (c > hi)
    short_ = in_ent & (c < lo)
    first = _first_per_day(long_ | short_, day)
    long_, short_ = long_ & first, short_ & first
    ref_l, ref_s = (lo, hi) if sl_mode == "range" else (mid, mid)
    sl_l, sl_s = c - ref_l, ref_s - c
    floor = min_sl_frac * (hi - lo)
    sl_l, sl_s = np.maximum(sl_l, floor), np.maximum(sl_s, floor)
    outside = ~((mod >= s0) & (mod < s1)) if flatten else np.zeros(len(df), bool)
    return _setup(df, long_, short_, sl_l, sl_s, tp_mult, outside, be)


def asian_range_breakout(df, sl_mode="range", tp_mult=1.0, be=0.0, entry_hours=3.0, flatten=True):
    """Range = 00:00-08:00 London time (covers Asia); trade its first
    breakout during the first `entry_hours` of London; exit by 16:30."""
    mod, day, s0, s1 = clock(df, "london")
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    in_rng = mod < s0
    in_ent = (mod >= s0) & (mod < s0 + entry_hours * 60)
    hi = pd.Series(np.where(in_rng, h, np.nan)).groupby(day).transform("max").to_numpy()
    lo = pd.Series(np.where(in_rng, l, np.nan)).groupby(day).transform("min").to_numpy()
    mid = (hi + lo) / 2
    long_ = in_ent & (c > hi)
    short_ = in_ent & (c < lo)
    first = _first_per_day(long_ | short_, day)
    long_, short_ = long_ & first, short_ & first
    ref_l, ref_s = (lo, hi) if sl_mode == "range" else (mid, mid)
    outside = ~((mod >= s0) & (mod < s1)) if flatten else np.zeros(len(df), bool)
    return _setup(df, long_, short_, c - ref_l, ref_s - c, tp_mult, outside, be)


def session_mean_fade(df, session="asian", z=2.5, sl_k=1.5, warmup=30, std_win=60):
    """Fade a stretch of z rolling std-devs from the session's running mean
    price; target = back to the mean, stop = sl_k x that distance; flat at
    session end.  Several trades per session allowed (one at a time)."""
    mod, day, s0, s1 = clock(df, session)
    c = df.close
    ins = (mod >= s0) & (mod < s1)
    cs = pd.Series(np.where(ins, c, 0.0))
    n = pd.Series(ins.astype(float))
    mean = (cs.groupby(day).cumsum() / n.groupby(day).cumsum()).to_numpy()
    sd = c.rolling(std_win).std().to_numpy()
    dev = c.to_numpy() - mean
    zz = dev / sd
    ok = ins & (mod >= s0 + warmup) & (mod < s1 - 15)
    long_, short_ = ok & (zz < -z), ok & (zz > z)
    dist = np.abs(dev)
    return _setup(df, long_, short_, sl_k * dist, sl_k * dist, 0, ~ins, 0.0, tp_long=dist, tp_short=dist)


def opening_drive(df, session="newyork", minutes=30, k=0.5, mode="follow", tp_mult=2.0, flatten=True):
    """At open + `minutes`, if the move since the open exceeds k x the average
    session range of the previous 20 sessions, follow (or fade) it."""
    mod, day, s0, s1 = clock(df, session)
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))
    ins = (mod >= s0) & (mod < s1)
    srange = pd.DataFrame({"d": day, "h": np.where(ins, h, np.nan), "l": np.where(ins, l, np.nan)}) \
        .groupby("d").agg(h=("h", "max"), l=("l", "min"))
    avg = (srange.h - srange.l).rolling(20).mean().shift()          # previous sessions only
    avg_d = pd.Series(day).map(avg).to_numpy()
    open_px = pd.Series(np.where(mod == s0, o, np.nan)).groupby(day).transform("max").to_numpy()
    in_rng = (mod >= s0) & (mod < s0 + minutes)
    hi = pd.Series(np.where(in_rng, h, np.nan)).groupby(day).transform("max").to_numpy()
    lo = pd.Series(np.where(in_rng, l, np.nan)).groupby(day).transform("min").to_numpy()
    at = mod == s0 + minutes - 1                                      # bar that closes the drive
    move = c - open_px
    up, dn = at & (move > k * avg_d), at & (move < -k * avg_d)
    if mode == "follow":
        long_, short_ = up, dn
        sl_l, sl_s = c - lo, hi - c
    else:
        long_, short_ = dn, up
        sl_l, sl_s = (c - lo) + 0.25 * np.abs(move), (hi - c) + 0.25 * np.abs(move)
    outside = ~ins if flatten else np.zeros(len(df), bool)
    return _setup(df, long_, short_, sl_l, sl_s, tp_mult, outside)


def trend_v2_session(df, session="london", min_stop=10.0, rr=3.0, be=1.0, flatten=False):
    """Trend Rider v2 entries, but only inside the session."""
    mod, day, s0, s1 = clock(df, session)
    P = v2.Params(min_stop_price=min_stop, rr=rr, be_trigger=be)
    s = v2.signals(df, P)
    ins = (mod >= s0) & (mod < s1)
    sig = np.where(ins, s.signal.to_numpy(), 0)
    dist = s.dist.to_numpy()
    outside = ~ins if flatten else np.zeros(len(df), bool)
    long_, short_ = sig == 1, sig == -1
    return _setup(df, long_, short_, dist, dist, rr, outside, be)


MIN_STOP = {"XAUUSD": 10.0, "NAS100": 40.0, "US30": 60.0, "BTCUSD": 400.0}


def families(market: str):
    S = ("asian", "london", "newyork")
    out = []
    for ses in S:
        for rm in (5, 15, 30, 60):
            for slm in ("range", "mid"):
                for tp in (1.0, 2.0, 3.0):
                    for be in (0.0, 1.0):
                        out.append(("Opening range breakout", orb,
                                    dict(session=ses, range_min=rm, sl_mode=slm, tp_mult=tp, be=be)))
        for z in (2.0, 2.5, 3.0):
            for k in (1.0, 1.5, 2.0):
                out.append(("Session-mean fade", session_mean_fade, dict(session=ses, z=z, sl_k=k)))
        for m in (15, 30):
            for k in (0.3, 0.5):
                for mode in ("follow", "fade"):
                    for tp in (1.0, 2.0):
                        out.append(("Opening drive", opening_drive,
                                    dict(session=ses, minutes=m, k=k, mode=mode, tp_mult=tp)))
        for rr in (2.0, 3.0):
            for fl in (False, True):
                out.append(("Trend Rider v2 (session only)", trend_v2_session,
                            dict(session=ses, min_stop=MIN_STOP[market], rr=rr, flatten=fl)))
    for slm in ("range", "mid"):
        for tp in (1.0, 2.0, 3.0):
            for be in (0.0, 1.0):
                out.append(("Asian range -> London breakout", asian_range_breakout,
                            dict(sl_mode=slm, tp_mult=tp, be=be)))
    return out
