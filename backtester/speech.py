"""Speech straddle: OCO buy/sell stops at the start of a scheduled Trump or Fed-chair appearance (Forex Factory).

At the event minute's open P: buy stop at P + d, sell stop at P - d, d = k x a (a = mean M1 true range over the
previous 240 minutes).  Orders live `expiry` minutes; the first one touched is filled (plus `cost`), the other is
cancelled.  Stop = s x d from the fill, target = rr x stop, optional break-even at +1R, time exit after `hold` bars.
If one M1 bar touches both orders, both fills are simulated and the worse result is kept.  After a fill the fill bar
itself is checked for the stop (pessimistic) but not the target.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import njit

TRUMP = "President Trump Speaks"
FED = ("Powell Speaks", "Powell Testifies", "Warsh Speaks", "Warsh Testifies", "FOMC Press Conference")


def speech_events(cal: pd.DataFrame) -> pd.DataFrame:
    c = cal[cal.time_label.fillna("").str.contains(r"\d", regex=True)]
    trump = c[c.name == TRUMP].assign(who="trump")
    fed = c[c.name.str.contains("|".join(FED))].assign(who="fed")
    ev = pd.concat([trump, fed])[["time_utc", "name", "impact", "who"]]
    return ev.drop_duplicates("time_utc").sort_values("time_utc").reset_index(drop=True)


@njit(cache=True)
def _after_fill(o, h, l, c, f, d, entry, risk, rr, be, hold, cost):
    """R of a position filled inside bar f at `entry` (long d=1 / short d=-1)."""
    stop = entry - d * risk
    tgt = entry + d * rr * risk
    moved = False
    last = min(len(o), f + hold)
    for j in range(f, last):
        bo = o[j] if d == 1 else o[j] + cost
        bh = h[j] if d == 1 else h[j] + cost
        bl = l[j] if d == 1 else l[j] + cost
        if d == 1:
            if bl <= stop:
                return (min(bo, stop) - entry) / risk if j > f else (stop - entry) / risk
            if j > f and rr > 0 and bh >= tgt:
                return (max(bo, tgt) - entry) / risk
        else:
            if bh >= stop:
                return (entry - max(bo, stop)) / risk if j > f else (entry - stop) / risk
            if j > f and rr > 0 and bl <= tgt:
                return (entry - min(bo, tgt)) / risk
        if be > 0 and not moved and j > f:
            if (d == 1 and bh >= entry + be * risk) or (d == -1 and bl <= entry - be * risk):
                stop = entry + d * 0.1 * risk
                moved = True
    j = last - 1
    px = c[j] if d == 1 else c[j] + cost
    return d * (px - entry) / risk


@njit(cache=True)
def straddle(o, h, l, c, i0, a, k, s, rr, be, expiry, hold, cost):
    n = len(i0)
    R = np.full(n, np.nan)
    side = np.zeros(n, np.int64)
    for q in range(n):
        i = i0[q]
        p = o[i]
        dist = k * a[q]
        up, dn = p + dist, p - dist
        risk = s * dist
        for j in range(i, min(i + expiry, len(o))):
            hit_up = h[j] + cost >= up             # buy stop triggers on the ask
            hit_dn = l[j] <= dn                    # sell stop triggers on the bid
            if not (hit_up or hit_dn):
                continue
            rl = _after_fill(o, h, l, c, j, 1, max(up, o[j] + cost), risk, rr, be, hold, cost) if hit_up else 1e9
            rs = _after_fill(o, h, l, c, j, -1, min(dn, o[j]), risk, rr, be, hold, cost) if hit_dn else 1e9
            if rl <= rs:
                R[q] = rl
                side[q] = 1
            else:
                R[q] = rs
                side[q] = -1
            break
    return R, side
