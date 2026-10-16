"""Tick-level New York open straddle.

At T0 - 10 s (T0 = 09:30 America/New_York) read the last quote, then place
    buy stop  at ask + dist     (triggers when ask >= level, fills at that tick's ask)
    sell stop at bid - dist     (triggers when bid <= level, fills at that tick's bid)
One-cancels-other: the first fill cancels the opposite order.  Pending
orders expire `expiry_s` seconds after T0.  Once filled:
    stop loss   = fill -/+ sl     take profit = fill +/- rr * sl
checked on every tick against the side you would close at (bid for longs,
ask for shorts), filled at the tick that crosses - so gaps/slippage at the
open are paid for.  Anything still open `max_hold_min` minutes after T0 is
closed at market.  R = P/L / sl.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Params:
    dist: float
    sl: float
    rr: float = 2.0
    expiry_s: int = 300
    max_hold_min: int = 60
    pre_s: int = 10


def ny_open_utc(d) -> pd.Timestamp:
    return pd.Timestamp(f"{d} 09:30", tz="America/New_York").tz_convert("UTC").tz_localize(None)


def load_day(market: str, d) -> tuple[np.ndarray, np.ndarray, np.ndarray, int] | None:
    """Ticks for the two UTC hours around the open as (ms_since_T0, ask, bid)."""
    t0 = ny_open_utc(d)
    parts = []
    for h in (t0.hour, t0.hour + 1):
        f = ROOT / "data" / "ticks" / market / f"{d}_{h:02d}.npy"
        if not f.exists():
            if h == t0.hour:
                return None
            continue                      # second hour optional: hold time then capped at ~30 min
        a = np.load(f)
        if len(a):
            base = (pd.Timestamp(f"{d}") + pd.Timedelta(hours=h) - t0) / pd.Timedelta("1ms")
            a = a.copy()
            a[:, 0] += base
            parts.append(a)
    if not parts:
        return None
    a = np.concatenate(parts)
    return a[:, 0], a[:, 1], a[:, 2], t0


def simulate_day(ms, ask, bid, p: Params):
    """Returns (direction, R, fill_ms, exit_ms, spread_at_fill) or None if no fill."""
    pre = np.searchsorted(ms, -p.pre_s * 1000, side="right") - 1
    if pre < 0 or ms[pre] < -120_000:              # need a live quote shortly before the open
        return None
    a0, b0 = ask[pre], bid[pre]
    lo_i, hi_i = pre + 1, np.searchsorted(ms, p.expiry_s * 1000, side="right")
    if hi_i <= lo_i:
        return None
    up = np.nonzero(ask[lo_i:hi_i] >= a0 + p.dist)[0]
    dn = np.nonzero(bid[lo_i:hi_i] <= b0 - p.dist)[0]
    iu = up[0] + lo_i if len(up) else None
    idn = dn[0] + lo_i if len(dn) else None
    if iu is None and idn is None:
        return None
    if idn is None or (iu is not None and iu <= idn):
        d, fi = 1, iu
        fill = ask[fi]
    else:
        d, fi = -1, idn
        fill = bid[fi]
    spread = ask[fi] - bid[fi]
    end = np.searchsorted(ms, p.max_hold_min * 60_000, side="right")
    close_px = bid[fi + 1:end] if d == 1 else ask[fi + 1:end]
    sl_px, tp_px = fill - d * p.sl, fill + d * p.rr * p.sl
    if d == 1:
        hit_sl, hit_tp = close_px <= sl_px, close_px >= tp_px
    else:
        hit_sl, hit_tp = close_px >= sl_px, close_px <= tp_px
    j_sl = np.argmax(hit_sl) if hit_sl.any() else None
    j_tp = np.argmax(hit_tp) if hit_tp.any() else None
    if j_sl is None and j_tp is None:
        j = len(close_px) - 1
        if j < 0:
            return None
    elif j_tp is None or (j_sl is not None and j_sl <= j_tp):
        j = j_sl
    else:
        j = j_tp
    exit_px = close_px[j]
    return d, d * (exit_px - fill) / p.sl, ms[fi], ms[fi + 1 + j], spread


def backtest(market: str, days, p: Params) -> pd.DataFrame:
    rows = []
    for d in days:
        x = load_day(market, d)
        if x is None:
            continue
        ms, ask, bid, t0 = x
        r = simulate_day(ms, ask, bid, p)
        if r is not None:
            dirn, R, fms, ems, spr = r
            rows.append({"date": pd.Timestamp(d), "dir": dirn, "r": R, "fill_s": fms / 1000,
                         "hold_min": (ems - fms) / 60000, "spread": spr})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# M1 approximation, for the full history (ticks are only cached for part of it)
def backtest_m1(m1: pd.DataFrame, days, p: Params, spread: float, slip: float) -> pd.DataFrame:
    """Same rules on 1-minute BID bars.  Reference quote = close of the 09:29
    bar (the straddle is placed at 09:29:50).  A buy stop fills at its level
    + `slip` (+ spread, as longs buy the ask); if both stops trigger inside
    the same minute the side AGAINST the bar's colour is assumed to have filled
    first, and exits are checked from that same bar, stop before target
    (pessimistic - use the tick backtest to resolve these minutes exactly)."""
    o, h, l, c = (m1[x].to_numpy() for x in ("open", "high", "low", "close"))
    idx = m1.index
    rows = []
    for d in days:
        t0 = ny_open_utc(d)
        i0 = idx.searchsorted(t0)
        if i0 == 0 or i0 >= len(idx) or idx[i0] != t0 or idx[i0 - 1] < t0 - pd.Timedelta("3min"):
            continue
        ref = c[i0 - 1]
        up_lvl, dn_lvl = ref + p.dist, ref - p.dist
        n_exp = max(1, p.expiry_s // 60)
        fill_i = d_ = None
        for i in range(i0, min(i0 + n_exp, len(o))):
            tu, td = h[i] >= up_lvl, l[i] <= dn_lvl
            if tu and td:
                # Both stops inside one minute: the order of events is unknown
                # from M1 data.  Using the bar's colour would leak where the
                # minute ended, so assume the WORST case - the side against the
                # minute's final direction filled first (a whipsaw).
                d_ = -1 if c[i] >= o[i] else 1
            elif tu:
                d_ = 1
            elif td:
                d_ = -1
            if d_:
                fill_i = i
                break
        if fill_i is None:
            continue
        if d_ == 1:
            fill = max(up_lvl, o[fill_i]) + slip + spread        # ask
        else:
            fill = min(dn_lvl, o[fill_i]) - slip                 # bid
        sl_px, tp_px = fill - d_ * p.sl, fill + d_ * p.rr * p.sl
        end = idx.searchsorted(t0 + pd.Timedelta(minutes=p.max_hold_min))
        exit_px, j = None, fill_i
        for j in range(fill_i, min(end, len(o))):
            if d_ == 1:
                if l[j] <= sl_px:
                    exit_px = min(sl_px, o[j]) if j > fill_i else sl_px; break
                if h[j] >= tp_px:
                    exit_px = tp_px; break
            else:
                if h[j] + spread >= sl_px:
                    exit_px = max(sl_px, o[j] + spread) if j > fill_i else sl_px; break
                if l[j] + spread <= tp_px:
                    exit_px = tp_px; break
        if exit_px is None:
            exit_px = c[j] if d_ == 1 else c[j] + spread
        rows.append({"date": pd.Timestamp(d), "dir": d_, "r": d_ * (exit_px - fill) / p.sl,
                     "hold_min": j - fill_i})
    return pd.DataFrame(rows)
