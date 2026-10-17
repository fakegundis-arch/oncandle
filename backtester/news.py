"""Tick-level backtests of two high-impact news setups.

A) STRADDLE: `pre_s` seconds before the release, a buy stop at ask + dist and a
   sell stop at bid - dist (one-cancels-other, expire `expiry_s` after the
   release).  The first to trigger fills at that tick's price (gaps/slippage
   included) plus `slip`; stop = fill -/+ sl, target = fill +/- rr * sl.
B) DOUBLE ENTRY: 5 s before the release, buy at the ask AND sell at the bid
   (two independent positions), each with stop sl and target rr * sl.
Exits are checked on every tick against the side you would close at (bid for
longs, ask for shorts); open trades are closed `max_hold_min` after the
release.  Results are in R (1R = one position's stop distance).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_ticks(market: str, t: pd.Timestamp):
    """(ms relative to t, ask, bid) from the cached hour file(s); None if missing."""
    hours = [t.floor("h")]
    if t.minute < 2:
        hours.insert(0, t.floor("h") - pd.Timedelta("1h"))
    parts = []
    for h in hours:
        f = ROOT / "data" / "ticks" / market / f"{h.date()}_{h.hour:02d}.npy"
        if not f.exists():
            return None
        a = np.load(f)
        if len(a):
            a = a.copy()
            a[:, 0] += (h - t) / pd.Timedelta("1ms")
            parts.append(a)
    if not parts:
        return None
    a = np.concatenate(parts)
    return a[:, 0], a[:, 1], a[:, 2]


def _exit(close_px, d, fill, sl, rr):
    """First tick that hits stop or target (stop wins ties); else last tick."""
    if len(close_px) == 0:
        return None, None
    sl_px, tp_px = fill - d * sl, fill + d * rr * sl
    hit_sl = close_px <= sl_px if d == 1 else close_px >= sl_px
    hit_tp = close_px >= tp_px if d == 1 else close_px <= tp_px
    js = np.argmax(hit_sl) if hit_sl.any() else None
    jt = np.argmax(hit_tp) if hit_tp.any() else None
    if js is None and jt is None:
        j = len(close_px) - 1
    elif jt is None or (js is not None and js <= jt):
        j = js
    else:
        j = jt
    return j, d * (close_px[j] - fill) / sl


@dataclass
class Straddle:
    dist: float
    sl: float
    rr: float = 3.0
    pre_s: int = 10
    expiry_s: int = 120
    max_hold_min: int = 25
    slip: float = 0.0


def straddle(ms, ask, bid, p: Straddle):
    i0 = np.searchsorted(ms, -p.pre_s * 1000, side="right") - 1
    if i0 < 0 or ms[i0] < -(p.pre_s + 120) * 1000:
        return None
    a0, b0 = ask[i0], bid[i0]
    hi = np.searchsorted(ms, p.expiry_s * 1000, side="right")
    up = np.nonzero(ask[i0 + 1:hi] >= a0 + p.dist)[0]
    dn = np.nonzero(bid[i0 + 1:hi] <= b0 - p.dist)[0]
    iu = up[0] + i0 + 1 if len(up) else None
    idn = dn[0] + i0 + 1 if len(dn) else None
    if iu is None and idn is None:
        return None
    if idn is None or (iu is not None and iu <= idn):
        d, fi, fill = 1, iu, ask[iu] + p.slip
    else:
        d, fi, fill = -1, idn, bid[idn] - p.slip
    end = np.searchsorted(ms, p.max_hold_min * 60_000, side="right")
    close_px = bid[fi + 1:end] if d == 1 else ask[fi + 1:end]
    j, r = _exit(close_px, d, fill, p.sl, p.rr)
    if r is None:
        return None
    return {"dir": d, "r": r, "fill_s": ms[fi] / 1000, "slippage": abs(fill - (a0 + p.dist if d == 1 else b0 - p.dist)),
            "spread_at_fill": ask[fi] - bid[fi]}


@dataclass
class Double:
    sl: float
    rr: float = 4.0
    pre_s: int = 5
    max_hold_min: int = 25


def double(ms, ask, bid, p: Double):
    i0 = np.searchsorted(ms, -p.pre_s * 1000, side="right") - 1
    if i0 < 0 or ms[i0] < -(p.pre_s + 120) * 1000:
        return None
    end = np.searchsorted(ms, p.max_hold_min * 60_000, side="right")
    _, r_long = _exit(bid[i0 + 1:end], 1, ask[i0], p.sl, p.rr)
    _, r_short = _exit(ask[i0 + 1:end], -1, bid[i0], p.sl, p.rr)
    if r_long is None or r_short is None:
        return None
    return {"r_long": r_long, "r_short": r_short, "r": r_long + r_short, "spread_at_entry": ask[i0] - bid[i0]}


def first_minute_range(ms, ask, bid):
    m = (ms >= 0) & (ms <= 60_000)
    if m.sum() < 5:
        return np.nan
    mid = (ask[m] + bid[m]) / 2
    return mid.max() - mid.min()
