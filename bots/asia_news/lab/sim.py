"""Fast single-trade simulator on NAS100 M1 BID bars with the protocol's fills (research engine for the v2 study).

Fills: long buys at ask = bid + ct, exits at bid; short sells at bid, exits at ask = bid + ct (ct charged at the exit
for a short, as newsbot.backtest).  ct = cost x news_mult when the entry is within `news_window` minutes of the
release, else cost.  Stop before target within a minute; the entry minute can only stop out; gaps fill at the open;
time exit at the open of the first bar at / after the exit time.  Trailing stop / break-even are updated at the close
of each bar (applied from the next bar).
"""
from __future__ import annotations

import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

import common as C

M = C.px()
TI = M.index.values.astype("datetime64[m]").astype(np.int64)      # minutes since epoch
O, H, Lo, Cl = (M[k].to_numpy() for k in ("open", "high", "low", "close"))
NB = len(TI)


def tmin(t) -> int:
    return int(np.datetime64(pd.Timestamp(t), "m").astype(np.int64))


def i_at(tm: int) -> int:
    """first bar at or after minute tm"""
    return int(np.searchsorted(TI, tm))


def fri_cap(tm: int) -> int:
    """Friday 20:00 UTC cap (minutes) for an entry at minute tm (no weekend positions)."""
    t = pd.Timestamp(np.datetime64(tm, "m"))
    fri = (t + pd.Timedelta(days=(4 - t.weekday()) % 7)).normalize() + pd.Timedelta(hours=20)
    if t >= fri:
        fri += pd.Timedelta(days=7)
    return tmin(fri)


def run_trade(i: int, fill: float, d: int, sd: float, tp_r: float, exit_tm: int, ct: float,
              trail: float = 0.0, be: float = 0.0, be_lock: float = 0.0, max_bars: int = 2000):
    """Trade entered in bar i at `fill` (already including the spread for a long).
    sd = stop distance (price), tp_r = target in R (0 / inf = none), exit_tm = time exit (minute),
    trail = trailing distance in R (0 = none; ratchets from the best bid high / low since entry),
    be = move the stop to entry + be_lock R once the trade has been be R in profit (0 = none).
    Returns (r, exit_bar, reason, exit_price)."""
    cap = fri_cap(int(TI[i]))
    exit_tm = min(exit_tm, cap)
    j_exit = i_at(exit_tm)
    if j_exit <= i:
        j_exit = i + 1
    j_end = min(j_exit, NB, i + max_bars)
    c = ct if d < 0 else 0.0
    sl0 = fill - d * sd
    tp = fill + d * tp_r * sd if tp_r and math.isfinite(tp_r) and tp_r > 0 else None
    op, hi, lo = O[i:j_end] + c, H[i:j_end] + c, Lo[i:j_end] + c
    n = len(op)
    if n == 0:
        return None
    # stop level per bar
    sl = np.full(n, sl0)
    if trail > 0 or be > 0:
        if d > 0:
            best = np.maximum.accumulate(hi)            # best bid high up to and including bar k
        else:
            best = np.minimum.accumulate(lo)
        best_prev = np.concatenate([[fill], best[:-1]])  # known at the start of bar k
        if trail > 0:
            ts = best_prev - d * trail * sd
            sl = np.maximum(sl, ts) if d > 0 else np.minimum(sl, ts)
        if be > 0:
            hit = (best_prev - fill) * d >= be * sd
            lock = fill + d * be_lock * sd
            sl = np.where(hit, np.maximum(sl, lock) if d > 0 else np.minimum(sl, lock), sl)
    k = np.arange(n)
    notfirst = k > 0
    if d > 0:
        g_stop = notfirst & (op <= sl)
        s_hit = lo <= sl
        g_tp = notfirst & (op >= tp) if tp is not None else np.zeros(n, bool)
        t_hit = notfirst & (hi >= tp) if tp is not None else np.zeros(n, bool)
    else:
        g_stop = notfirst & (op >= sl)
        s_hit = hi >= sl
        g_tp = notfirst & (op <= tp) if tp is not None else np.zeros(n, bool)
        t_hit = notfirst & (lo <= tp) if tp is not None else np.zeros(n, bool)
    anyhit = g_stop | g_tp | s_hit | t_hit
    if anyhit.any():
        j = int(np.argmax(anyhit))
        if g_stop[j]:
            px, why = op[j], "stop-gap"
        elif g_tp[j]:
            px, why = op[j], "target-gap"
        elif s_hit[j]:
            px, why = sl[j], "stop"
        else:
            px, why = tp, "target"
        return d * (px - fill) / sd, i + j, why, px
    if j_end >= NB:
        px = Cl[-1] + c
        return d * (px - fill) / sd, NB - 1, "end", px
    px = O[j_end] + c
    return d * (px - fill) / sd, j_end, "time", px


# ------------------------------------------------------------------------------------------------ event contexts
_CACHE = Path(__file__).parent / "out" / "ctx_cache.pkl"


def _atr_fast():
    """ATR(24 x H1) exactly as newsbot.strategy.atr for any time t (cached per minute key)."""
    from newsbot.strategy import atr
    return lambda t: atr(M, pd.Timestamp(t).to_pydatetime(), 60, 24)


def contexts(times, tag: str) -> list[dict]:
    """For each time (release minute) -> dict(t, tm, i0 (release bar), pre (close before), atr) or skipped if the
    market does not quote at the release minute."""
    cache = {}
    if _CACHE.exists():
        cache = pickle.loads(_CACHE.read_bytes())
    f = _atr_fast()
    out, changed = [], False
    for t in times:
        t = pd.Timestamp(t)
        tm = tmin(t)
        i0 = i_at(tm)
        if i0 >= NB:
            continue
        q0 = bool(TI[i0] == tm and tm - TI[i0 - 1] <= 5)        # market quoting at the release minute
        key = str(t)
        if key not in cache:
            cache[key] = f(t)
            changed = True
        out.append(dict(t=t, tm=tm, i0=i0, q0=q0, pre=Cl[i0 - 1], atr=cache[key]))
    if changed:
        _CACHE.parent.mkdir(exist_ok=True)
        _CACHE.write_bytes(pickle.dumps(cache))
    return out
